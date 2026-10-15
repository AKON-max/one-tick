# ============================================================
# 计划任务拆分服务
#
# 把计划文档（含目标/说明）总结成平铺的、可打勾的任务清单。
# 幂等流程：
# ① 已在拆分中（2 分钟内）→ 直接返回 alreadyRunning，避免重复触发
# ② AI 判断文档改动是否实质影响任务 → 大意没变则不拆，仅更新哈希
# ③ 真正拆分：AI 拆解 → 按归一化标题对账（更新/新增）→ 删除不再出现且未完成的任务
# ============================================================

import hashlib
import json
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.model_pool import UsageContext, completions_with_fallback
from app.models.study import Plan, PlanTask

# ---- 文档来源（拆分/过期判断依据：文档 + 目标 + 说明）----


def plan_task_source(plan: Plan) -> str:
    return "\n\n".join([p for p in (plan.document, plan.goal, plan.description) if p])


def plan_task_source_hash(plan: Plan) -> str:
    return hashlib.sha256(plan_task_source(plan).encode("utf-8")).hexdigest()


# ---- Prompt----

SPLIT_SYSTEM_PROMPT = """你是学习计划拆解助手，把用户的学习计划文档拆成可执行、可打勾的任务清单。

要求：
- 平铺成一条条任务，不要按周/天分组，不要输出 Day/Week 编号。
- 每个任务具体、可量化、有明确的完成标准。
- 保留用户文档里已经写清楚的学习目标与安排，不要遗漏。
- 任务数量适中（一般不超过 30 个）。

必须只输出 JSON，且严格遵循以下结构（字段名不可改变，category/priority 只能取括号内的值）：
{
  "tasks": [
    {
      "title": "任务标题",
      "description": "任务描述（可省略）",
      "category": "study | project | review | exercise",
      "priority": "high | normal | low"
    }
  ]
}"""

CHECK_TASKS_PROMPT = """你是学习计划任务同步判断器。对比"当前文档"与"当前任务清单"，判断文档的变化是否会让现有任务需要更新（新增/删除/修改）。
- 如果文档只是措辞调整、格式调整、错别字修改、补充说明等，不改变学习目标/内容/范围/节奏/产出 → needsUpdate=false
- 如果文档的学习目标、学习内容、范围、节奏或产出发生实质变化，需要重新生成任务 → needsUpdate=true
只返回 JSON：{"needsUpdate": true 或 false, "reason": "一句简短原因"}"""

# ---- 工具 ----

CATEGORIES = ("study", "project", "review", "exercise")
PRIORITIES = ("high", "normal", "low")


def _normalize_title(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())


def _extract_json_text(text: str) -> str:
    """提取模型输出中的 JSON 主体（兼容可能的 markdown 代码围栏）"""
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    return (m.group(1) if m else text).strip()


def _validate_split_object(parsed) -> list[dict] | None:
    """校验并规范化 AI 拆解结果；任何一项不合法返回 None（触发重试）"""
    if not isinstance(parsed, dict):
        return None
    raw_tasks = parsed.get("tasks")
    if not isinstance(raw_tasks, list):
        return None
    tasks: list[dict] = []
    for item in raw_tasks:
        if not isinstance(item, dict):
            return None
        title = str(item.get("title") or "").strip()
        if not title or len(title) > 160:
            return None
        task: dict = {"title": title}
        desc = item.get("description")
        if isinstance(desc, str) and desc.strip():
            if len(desc.strip()) > 600:
                return None
            task["description"] = desc.strip()
        category = item.get("category", "study")
        task["category"] = category if category in CATEGORIES else "study"
        priority = item.get("priority", "normal")
        task["priority"] = priority if priority in PRIORITIES else "normal"
        tasks.append(task)
    return tasks


# ---- AI 调用 ----

def _tasks_need_update(source: str, titles: list[str], user_id: str) -> bool:
    """AI 判断文档改动是否实质影响任务清单；解析失败时保守处理为需要更新"""
    resp, _model = completions_with_fallback(
        "low",
        lambda entry, client: client.chat.completions.create(
            model=entry.modelName,
            temperature=0,
            max_tokens=300,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": CHECK_TASKS_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"document": source, "tasks": titles}, ensure_ascii=False
                    ),
                },
            ],
        ),
        UsageContext(user_id, "split", enforce=True),
    )
    text = resp.choices[0].message.content
    if not text:
        return True
    try:
        parsed = json.loads(_extract_json_text(text))
        return parsed.get("needsUpdate") is not False
    except Exception:  # noqa: BLE001
        return True


def _ai_split_tasks(source: str, user_id: str) -> list[dict] | None:
    """AI 拆解文档为任务列表；连续 2 次解析失败返回 None（不改动现有任务）"""
    for attempt in range(2):
        resp, _model = completions_with_fallback(
            "low",
            lambda entry, client: client.chat.completions.create(
                model=entry.modelName,
                temperature=0.3,
                max_tokens=8192,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SPLIT_SYSTEM_PROMPT},
                    {"role": "user", "content": source},
                ],
            ),
            UsageContext(user_id, "split", enforce=True),
        )
        text = resp.choices[0].message.content
        if not text:
            continue
        try:
            tasks = _validate_split_object(json.loads(_extract_json_text(text)))
            if tasks is not None:
                return tasks
        except Exception:  # noqa: BLE001
            pass
        print(f"[split] 第 {attempt + 1} 次 JSON 解析失败，重试")
    return None


# ---- 主入口 ----

def _splitting_recent(ts) -> bool:
    """tasksSplittingAt 是否在 2 分钟内的进行中状态"""
    if ts is None:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds() < 120


def _clear_splitting_flag(db: Session, plan_id: str) -> None:
    """无论成功失败都清除拆分中标记（显式 UPDATE，避免 ORM 过期对象刷新的干扰）"""
    from sqlalchemy import update as sa_update

    try:
        db.execute(
            sa_update(Plan).where(Plan.id == plan_id).values(tasksSplittingAt=None)
        )
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


def split_plan_tasks(db: Session, plan: Plan, user_id: str) -> dict:
    """拆分计划任务（幂等）。返回结构：
    { success, alreadyRunning, changed, reason?, created, updated, deleted }
    """
    source = plan_task_source(plan)
    if not source.strip():
        raise ValueError("计划还没有可拆分的内容")

    # 已在后台拆分中（2 分钟内视为进行中）→ 跳过，避免重复触发
    if _splitting_recent(plan.tasksSplittingAt):
        return {
            "success": True,
            "alreadyRunning": True,
            "changed": False,
            "created": 0,
            "updated": 0,
            "deleted": 0,
        }

    try:
        # 1. 先让 AI 判断文档改动是否实质影响任务：大意没变就不进入"刷新中"、不重新拆分
        titles = db.execute(
            select(PlanTask.title).where(PlanTask.planId == plan.id)
        ).scalars().all()
        if not _tasks_need_update(source, list(titles), user_id):
            # 大意没变：只把文档哈希更新为"已评估"，抽屉不再提示过期
            plan.tasksSourceHash = plan_task_source_hash(plan)
            db.commit()
            return {
                "success": True,
                "alreadyRunning": False,
                "changed": False,
                "reason": "no-change",
                "created": 0,
                "updated": 0,
                "deleted": 0,
            }

        # 2. 确实需要更新：先标记"刷新中"（抽屉据此显示进度条），再完整拆分
        plan.tasksSplittingAt = datetime.now(timezone.utc)
        db.commit()

        # 3. AI 拆解（内部已重试 1 次）
        tasks = _ai_split_tasks(source, user_id)
        if tasks is None:
            raise ValueError("AI 拆分结果解析失败，请重试")
        # AI 没拆出内容时不改动现有任务，避免误清空
        if not tasks:
            return {
                "success": True,
                "alreadyRunning": False,
                "changed": False,
                "created": 0,
                "updated": 0,
                "deleted": 0,
            }

        # 4. 对账：按归一化标题匹配 → 更新已有 / 新增；删除不再出现且未完成的任务
        existing = db.execute(
            select(PlanTask).where(PlanTask.planId == plan.id)
        ).scalars().all()
        by_title = {_normalize_title(t.title): t for t in existing}

        used_ids: set[str] = set()
        created = 0
        updated = 0
        for task in tasks:
            match = by_title.get(_normalize_title(task["title"]))
            if match is not None and match.id not in used_ids:
                used_ids.add(match.id)
                match.title = task["title"]
                match.description = task.get("description")
                match.category = task.get("category", "study")
                match.priority = task.get("priority", "normal")
                updated += 1
            else:
                db.add(
                    PlanTask(
                        planId=plan.id,
                        userId=user_id,
                        title=task["title"],
                        description=task.get("description"),
                        category=task.get("category", "study"),
                        priority=task.get("priority", "normal"),
                    )
                )
                created += 1

        # 删除不再出现、且未完成的任务；已完成的历史保留（不丢进度）
        deleted = 0
        for t in existing:
            if t.id not in used_ids and t.status != "done":
                db.delete(t)
                deleted += 1

        # 记录本次拆分所用的文档哈希，供抽屉判断任务是否过期（文档再改动即 stale）
        plan.tasksSourceHash = plan_task_source_hash(plan)
        db.commit()
        print(f"[split] 任务已刷新 plan={plan.id} created={created} updated={updated} deleted={deleted}")
        return {
            "success": True,
            "alreadyRunning": False,
            "changed": True,
            "created": created,
            "updated": updated,
            "deleted": deleted,
        }
    finally:
        # 无论成功失败都清除拆分中标记，抽屉轮询据此结束"刷新中"
        _clear_splitting_flag(db, plan.id)
