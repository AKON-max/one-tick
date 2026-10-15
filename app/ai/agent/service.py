# ============================================================
# Agent 计划生成 & 运行管理服务
#
# 核心能力：
# ① generate_plan_for_plan — 为已有计划生成 PlanDraft 并拆分成 PlanTask
#    （LLM 结构化输出 + fallback_draft 规则兜底，MAX_TASKS=40）
# ② 运行管理 — create/decide/cancel/list/get/serialize AgentRun
# ③ plan_draft_to_markdown — 计划草案 → 详细文档
# ============================================================

import json
import re
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.ai.agent.types import AgentContextSnapshot, PlanDraft
from app.ai.model_pool import UsageContext, completions_with_fallback
from app.db.session import SessionLocal
from app.models.agent import AgentApproval, AgentRun, AgentStep, UserMemory
from app.models.study import Checkin, Plan, PlanTask

MAX_TASKS = 40


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================
# 计划草案 → Markdown 文档
# ============================================================

TASK_CATEGORY_LABEL = {
    "study": "学习",
    "project": "项目",
    "review": "复习",
    "exercise": "练习",
}

TASK_PRIORITY_LABEL = {
    "high": "高",
    "normal": "中",
    "low": "低",
}


def _task_tags(task: dict) -> list[str]:
    tags = [TASK_CATEGORY_LABEL.get(task.get("category") or "", "")]
    priority = task.get("priority")
    if priority:
        tags.append(f"优先级：{TASK_PRIORITY_LABEL.get(priority, priority)}")
    return [t for t in tags if t]


def _render_learning_guide(tasks: list[dict]) -> list[str]:
    lines: list[str] = ["## 学习指导", ""]
    for task in tasks:
        week_label = f"第 {task.get('weekNumber')} 周 · " if task.get("weekNumber") else ""
        day_label = f"Day {task.get('dayNumber')} · " if task.get("dayNumber") else ""
        lines.append(f"### {week_label}{day_label}{task.get('title', '')}")
        lines.append("")
        description = (task.get("description") or "").strip()
        if description:
            lines.append(description)
            lines.append("")
        tags = _task_tags(task)
        if tags:
            lines.append(f"> {' · '.join(tags)}")
            lines.append("")
    return lines


def _render_task_checklist(tasks: list[dict]) -> list[str]:
    lines: list[str] = ["## 任务安排", ""]
    for task in tasks:
        checked = "x" if task.get("status") == "done" else " "
        lines.append(f"- [{checked}] {task.get('title', '')}")
    lines.append("")
    return lines


def plan_draft_to_markdown(draft) -> str:
    """计划草案 → 详细计划文档

    结构： # 名称 / ## 目标 / ## 计划说明 / ## 前提假设 / ## 学习指导 / ## 任务安排 / ## 学习笔记
    """
    if isinstance(draft, PlanDraft):
        draft = draft.model_dump()

    lines: list[str] = [f"# {draft.get('name', '')}", ""]

    goal = (draft.get("goal") or "").strip()
    if goal:
        lines += ["## 目标", "", goal, ""]

    description = (draft.get("description") or "").strip()
    if description:
        lines += ["## 计划说明", "", description, ""]

    assumptions = draft.get("assumptions") or []
    if assumptions:
        lines += ["## 前提假设", ""]
        for a in assumptions:
            lines.append(f"- {a}")
        lines.append("")

    tasks = draft.get("tasks") or []
    if tasks:
        lines += _render_learning_guide(tasks)
        lines += _render_task_checklist(tasks)

    lines += ["## 学习笔记", "", "在这里记录学习内容、心得和遇到的问题…", ""]
    return "\n".join(lines)


# ============================================================
# 7 天默认学习计划草案（规则兜底，对应 fallbackDraft）
# ============================================================

def fallback_draft(goal: str) -> dict:
    """模型不可用时的 7 天默认学习计划草案"""
    short_goal = goal.strip()[:72]
    return {
        "name": f"{short_goal}学习计划",
        "description": f"围绕“{short_goal}”建立一个可执行的 7 天学习闭环。",
        "goal": short_goal,
        "assumptions": ["按每天约 2 小时安排", "先完成基础理解，再通过练习验证"],
        "tasks": [
            {
                "title": "Day 1：拆解目标并准备学习环境",
                "description": "明确本周产出，整理资料，完成必要的环境准备。",
                "dayNumber": 1,
                "weekNumber": 1,
                "category": "study",
                "priority": "high",
            },
            {
                "title": "Day 2：学习核心概念",
                "description": "阅读主线资料，记录三个关键概念和一个待解决问题。",
                "dayNumber": 2,
                "weekNumber": 1,
                "category": "study",
                "priority": "high",
            },
            {
                "title": "Day 3：完成一个小练习",
                "description": "把核心概念应用到一个小练习中，保留结果和遇到的问题。",
                "dayNumber": 3,
                "weekNumber": 1,
                "category": "exercise",
                "priority": "normal",
            },
            {
                "title": "Day 4：做一次项目实践",
                "description": "围绕目标完成一个可展示的小功能或小作品。",
                "dayNumber": 4,
                "weekNumber": 1,
                "category": "project",
                "priority": "high",
            },
            {
                "title": "Day 5：复盘并查漏补缺",
                "description": "回顾练习结果，补齐最薄弱的一个知识点。",
                "dayNumber": 5,
                "weekNumber": 1,
                "category": "review",
                "priority": "normal",
            },
            {
                "title": "Day 6：综合练习",
                "description": "不看答案完成一次综合任务，记录完成耗时和卡点。",
                "dayNumber": 6,
                "weekNumber": 1,
                "category": "exercise",
                "priority": "normal",
            },
            {
                "title": "Day 7：阶段总结与下一步计划",
                "description": "整理本周成果、问题和下一阶段要继续推进的事项。",
                "dayNumber": 7,
                "weekNumber": 1,
                "category": "review",
                "priority": "high",
            },
        ],
    }


# ============================================================
# 上下文快照
# ============================================================

def collect_context(user_id: str) -> AgentContextSnapshot:
    """收集计划生成所需的用户上下文快照（打卡总数 / 活跃计划进度 / 记忆数）"""
    with SessionLocal() as db:
        total_checkins = (
            db.execute(
                select(func.count()).select_from(Checkin).where(Checkin.userId == user_id)
            ).scalar()
            or 0
        )

        plans = db.execute(
            select(Plan)
            .where(Plan.userId == user_id, Plan.status == "active")
            .order_by(Plan.updatedAt.desc())
            .limit(5)
        ).scalars().all()

        plan_ids = [p.id for p in plans]
        tasks_by_plan: dict[str, list[PlanTask]] = {}
        if plan_ids:
            rows = db.execute(
                select(PlanTask).where(PlanTask.planId.in_(plan_ids))
            ).scalars().all()
            for t in rows:
                tasks_by_plan.setdefault(t.planId, []).append(t)

        memory_count = (
            db.execute(
                select(func.count())
                .select_from(UserMemory)
                .where(UserMemory.userId == user_id)
            ).scalar()
            or 0
        )

    active_plans = []
    for p in plans:
        tasks = tasks_by_plan.get(p.id, [])
        total = len(tasks)
        done = len([t for t in tasks if t.status == "done"])
        active_plans.append(
            {
                "id": p.id,
                "name": p.name,
                "progress": round(done / total * 100) if total > 0 else 0,
            }
        )

    return AgentContextSnapshot(
        totalCheckins=total_checkins,
        activePlans=active_plans,
        memoryCount=memory_count,
    )


# ============================================================
# LLM 草案生成
# ============================================================

def _extract_json_text(text: str) -> str:
    """提取模型输出中的 JSON 主体（兼容可能的 markdown 代码围栏）"""
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    return (m.group(1) if m else text).strip()


def _parse_draft(value) -> PlanDraft | None:
    """把 LLM 输出解析为 PlanDraft；无效返回 None（交给 fallback）"""
    candidate = value.get("plan") if isinstance(value, dict) and "plan" in value else value
    try:
        draft = PlanDraft.model_validate(candidate)
    except Exception:  # noqa: BLE001
        return None
    # 模型没给出任务安排（tasks 缺失或为空）→ 视为无效，交给 fallback（自带任务）
    if len(draft.tasks) == 0:
        return None
    draft.tasks = draft.tasks[:MAX_TASKS]
    return draft


def generate_draft(
    goal: str,
    context: AgentContextSnapshot,
    user_id: str,
    extras: dict | None = None,
) -> dict:
    """LLM 生成计划草案；模型不可用/解析失败自动回落 fallbackDraft

    extras: {"description", "conversation", "memories"}（保留个性化）
    :return: {"draft": PlanDraft, "source": "model" | "fallback"}
    """
    extras = extras or {}
    try:
        # 模型偶尔输出损坏/截断的 JSON（如未加引号的属性名），解析失败时重试一次
        for attempt in range(2):
            # 仅注入有值的额外上下文（与 TS 的 ...(extras?.x ? {...} : {}) 一致）
            user_payload: dict = {
                "goal": goal,
                "context": context.model_dump(),
                "instruction": "根据用户目标和真实学习数据生成 7-30 天的计划草案，优先给出清晰的阶段产出。",
            }
            if extras.get("description"):
                user_payload["description"] = extras["description"]
            if extras.get("conversation"):
                user_payload["conversation"] = extras["conversation"]
            if extras.get("memories"):
                user_payload["memories"] = extras["memories"]

            data, _model = completions_with_fallback(
                "high",
                lambda entry, client: client.chat.completions.create(
                    model=entry.modelName,
                    temperature=0.3,
                    max_tokens=8192,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "system",
                            "content": "你是学习计划规划 Agent。只返回 JSON，不要 Markdown。计划必须可执行，最多 40 个任务。字段为 name、description、goal、assumptions、tasks；tasks 每项包含 title、description、dayNumber、weekNumber、category(study/project/review/exercise)、priority(high/normal/low)。任务 description 用一两句话写清要做什么和完成标准，简明扼要。",
                        },
                        {
                            "role": "user",
                            "content": json.dumps(user_payload, ensure_ascii=False),
                        },
                    ],
                ),
                UsageContext(user_id, "agent-bg"),
            )

            text = ""
            if getattr(data, "choices", None):
                content = data.choices[0].message.content
                if content:
                    text = content.strip()
            if not text:
                continue
            try:
                parsed = _parse_draft(json.loads(_extract_json_text(text)))
                if parsed:
                    return {"draft": parsed, "source": "model"}
            except Exception as parse_error:  # noqa: BLE001
                print(
                    f"[Agent] 第 {attempt + 1} 次 draft JSON 解析失败: {parse_error}"
                )
    except Exception as error:  # noqa: BLE001
        print(f"[Agent] plan draft generation failed, using fallback: {error}")

    return {"draft": PlanDraft.model_validate(fallback_draft(goal)), "source": "fallback"}


# ============================================================
# 为已有计划生成内容
# ============================================================

def generate_plan_for_plan(
    plan_id: str,
    user_id: str,
    opts: dict | None = None,
) -> dict:
    """为已创建的计划生成完整内容：详细文档（Markdown）+ 每日任务。

    供聊天 createPlan 工具使用；模型不可用时自动回落基础草案（fallbackDraft），不会失败。
    opts: {"goal", "description", "conversation", "memories"}
    """
    opts = opts or {}

    with SessionLocal() as db:
        plan = db.execute(
            select(Plan).where(Plan.id == plan_id, Plan.userId == user_id)
        ).scalar_one_or_none()
        if plan is None:
            raise ValueError(f"计划不存在: {plan_id}")
        goal = (opts.get("goal") or plan.goal or plan.name or "学习计划").strip()
        plan_name = plan.name
        real_plan_id = plan.id

    context = collect_context(user_id)
    result = generate_draft(goal, context, user_id, opts)
    draft: PlanDraft = result["draft"]
    source = result["source"]
    print(f"[Agent] 计划草稿生成来源: {source}（{len(draft.tasks)} 个任务）")

    # 文档标题与计划名保持一致；任务直接来自 draft（结构化，比解析文档更可靠）
    document = plan_draft_to_markdown({**draft.model_dump(), "name": plan_name})

    tasks_to_create = draft.tasks[:MAX_TASKS]
    with SessionLocal() as db:
        plan_row = db.get(Plan, real_plan_id)
        plan_row.document = document

        for task in tasks_to_create:
            db.add(
                PlanTask(
                    userId=user_id,
                    planId=real_plan_id,
                    title=task.title,
                    description=task.description,
                    dayNumber=task.dayNumber,
                    weekNumber=task.weekNumber,
                    category=task.category,
                    priority=task.priority,
                )
            )
        db.commit()

    return {
        "planId": real_plan_id,
        "name": plan_name,
        "tasksCreated": len(tasks_to_create),
    }


# ============================================================
# AgentRun 运行管理
# ============================================================

def get_agent_run_for_user(run_id: str, user_id: str) -> AgentRun | None:
    """查询单个 AgentRun（预加载 steps / approvals）"""
    with SessionLocal() as db:
        run = db.execute(
            select(AgentRun).where(
                AgentRun.id == run_id, AgentRun.userId == user_id
            )
        ).scalar_one_or_none()
        if run is None:
            return None
        # 会话内触发加载，避免脱离会话后懒加载报错
        list(run.steps)
        list(run.approvals)
        return run


def list_agent_runs(user_id: str) -> list[AgentRun]:
    """列出最近 20 条 AgentRun（steps / approvals 按时间倒序）"""
    with SessionLocal() as db:
        runs = db.execute(
            select(AgentRun)
            .where(AgentRun.userId == user_id)
            .order_by(AgentRun.updatedAt.desc())
            .limit(20)
        ).scalars().all()
        for run in runs:
            run.steps.sort(key=lambda s: s.stepNumber, reverse=True)
            run.approvals.sort(key=lambda a: a.createdAt, reverse=True)
        return runs


def create_agent_run(user_id: str, goal: str, mode: str = "planner") -> AgentRun | None:
    """创建一次计划生成 AgentRun（草案生成后进入 awaiting_approval）"""
    now = _now_utc()

    with SessionLocal() as db:
        run = AgentRun(
            userId=user_id,
            mode=mode,
            goal=goal,
            status="running",
            startedAt=now,
            currentStep=1,
        )
        db.add(run)
        db.flush()
        db.add(
            AgentStep(
                runId=run.id,
                stepNumber=1,
                kind="context",
                status="running",
                title="读取学习上下文",
                detail="正在汇总近期学习记录、活跃计划和长期记忆。",
                startedAt=now,
            )
        )
        db.commit()
        run_id = run.id

    try:
        context = collect_context(user_id)

        with SessionLocal() as db:
            context_step = db.execute(
                select(AgentStep).where(
                    AgentStep.runId == run_id, AgentStep.stepNumber == 1
                )
            ).scalar_one()
            context_step.status = "completed"
            context_step.output = context.model_dump()
            context_step.completedAt = _now_utc()

            planning_step = AgentStep(
                runId=run_id,
                stepNumber=2,
                kind="planning",
                status="running",
                title="生成计划草案",
                detail="根据目标和学习数据生成可执行的阶段任务。",
                input={"goal": goal, "context": context.model_dump()},
                startedAt=_now_utc(),
            )
            db.add(planning_step)
            db.commit()
            planning_step_id = planning_step.id

        result = generate_draft(goal, context, user_id)
        draft: PlanDraft = result["draft"]
        source = result["source"]

        with SessionLocal() as db:
            step = db.get(AgentStep, planning_step_id)
            step.status = "completed"
            step.output = {"draft": draft.model_dump(), "source": source}
            step.detail = (
                "计划草案已生成，等待确认后写入学习计划。"
                if source == "model"
                else "模型暂不可用，已生成可编辑的基础草案。"
            )
            step.completedAt = _now_utc()

            db.add(
                AgentApproval(
                    runId=run_id,
                    stepId=planning_step_id,
                    action="create_plan",
                    status="pending",
                    payload=draft.model_dump(),
                )
            )

            run_row = db.get(AgentRun, run_id)
            run_row.status = "awaiting_approval"
            run_row.currentStep = 2
            run_row.summary = "计划草案已生成，等待你确认后写入学习计划。"
            db.commit()
    except Exception as error:  # noqa: BLE001
        message = str(error)
        with SessionLocal() as db:
            run_row = db.get(AgentRun, run_id)
            run_row.status = "failed"
            run_row.error = message
            run_row.completedAt = _now_utc()
            running_steps = db.execute(
                select(AgentStep).where(
                    AgentStep.runId == run_id, AgentStep.status == "running"
                )
            ).scalars().all()
            for s in running_steps:
                s.status = "failed"
                s.error = message
                s.completedAt = _now_utc()
            db.commit()

    return get_agent_run_for_user(run_id, user_id)


def decide_agent_approval(
    user_id: str,
    run_id: str,
    approval_id: str,
    decision: str,
    reason: str | None = None,
) -> AgentRun | None:
    """用户确认/拒绝计划草案"""
    run = get_agent_run_for_user(run_id, user_id)
    if run is None:
        return None

    approval = next(
        (a for a in run.approvals if a.id == approval_id and a.status == "pending"),
        None,
    )
    if approval is None:
        raise ValueError("This approval is no longer pending")

    if decision == "reject":
        with SessionLocal() as db:
            appr = db.get(AgentApproval, approval.id)
            appr.status = "rejected"
            appr.decisionReason = reason.strip() if reason and reason.strip() else None
            appr.decidedAt = _now_utc()

            db.add(
                AgentStep(
                    runId=run_id,
                    stepNumber=run.currentStep + 1,
                    kind="approval",
                    status="completed",
                    title="用户拒绝计划草案",
                    detail=reason.strip() if reason and reason.strip() else "用户暂不接受这份计划草案。",
                    completedAt=_now_utc(),
                )
            )

            run_row = db.get(AgentRun, run_id)
            run_row.status = "rejected"
            run_row.currentStep = run.currentStep + 1
            run_row.summary = "计划草案已拒绝，可以重新提交一个目标。"
            run_row.completedAt = _now_utc()
            db.commit()
        return get_agent_run_for_user(run_id, user_id)

    # approve
    draft = _parse_draft(approval.payload)
    if draft is None:
        raise ValueError("The plan draft is invalid")

    with SessionLocal() as db:
        pending = db.execute(
            select(AgentApproval).where(
                AgentApproval.id == approval_id,
                AgentApproval.runId == run_id,
                AgentApproval.status == "pending",
            )
        ).scalar_one_or_none()
        if pending is None:
            raise ValueError("This approval is no longer pending")

        run_row = db.get(AgentRun, run_id)
        base_step = run_row.currentStep

        # 确认步骤 + 执行步骤
        db.add(
            AgentStep(
                runId=run_id,
                stepNumber=base_step + 1,
                kind="approval",
                status="completed",
                title="确认计划草案",
                detail="用户已确认，开始写入计划和任务。",
                completedAt=_now_utc(),
            )
        )
        execution_step = AgentStep(
            runId=run_id,
            stepNumber=base_step + 2,
            kind="execution",
            status="running",
            title="写入学习计划",
            detail="正在创建计划和每日任务。",
            startedAt=_now_utc(),
        )
        db.add(execution_step)
        db.flush()

        plan = Plan(
            userId=user_id,
            name=draft.name,
            description=draft.description,
            goal=draft.goal,
            status="active",
            # 确认创建时直接生成详细计划文档（学习指导 + 任务安排）
            document=plan_draft_to_markdown(draft),
        )
        db.add(plan)
        db.flush()

        for task in draft.tasks[:MAX_TASKS]:
            db.add(
                PlanTask(
                    userId=user_id,
                    planId=plan.id,
                    title=task.title,
                    description=task.description,
                    dayNumber=task.dayNumber,
                    weekNumber=task.weekNumber,
                    category=task.category,
                    priority=task.priority,
                )
            )

        pending.status = "approved"
        pending.decisionReason = reason.strip() if reason and reason.strip() else None
        pending.decidedAt = _now_utc()

        execution_step.status = "completed"
        execution_step.output = {
            "planId": plan.id,
            "tasksCreated": len(draft.tasks),
        }
        execution_step.detail = f"已创建计划和 {len(draft.tasks)} 个任务。"
        execution_step.completedAt = _now_utc()

        run_row.status = "completed"
        run_row.currentStep = execution_step.stepNumber
        run_row.summary = f"计划“{draft.name}”已创建，可从今天的第一个任务开始。"
        run_row.completedAt = _now_utc()
        db.commit()

    return get_agent_run_for_user(run_id, user_id)


def cancel_agent_run(user_id: str, run_id: str) -> AgentRun | None:
    """取消一次 AgentRun"""
    run = get_agent_run_for_user(run_id, user_id)
    if run is None:
        return None
    if run.status in ("completed", "failed", "cancelled", "rejected"):
        return run

    with SessionLocal() as db:
        run_row = db.get(AgentRun, run_id)
        run_row.status = "cancelled"
        run_row.summary = "Agent 运行已取消，未执行未确认的写入操作。"
        run_row.completedAt = _now_utc()

        steps = db.execute(
            select(AgentStep).where(
                AgentStep.runId == run_id,
                AgentStep.status.in_(["running", "pending"]),
            )
        ).scalars().all()
        for s in steps:
            s.status = "cancelled"
            s.completedAt = _now_utc()
        db.commit()

    return get_agent_run_for_user(run_id, user_id)


def serialize_agent_run(run: AgentRun) -> dict:
    """AgentRun ORM → AgentRunResponse dict"""

    def _iso(dt) -> str | None:
        return dt.isoformat() if dt else None

    return {
        "id": run.id,
        "mode": run.mode,
        "goal": run.goal,
        "status": run.status,
        "currentStep": run.currentStep,
        "maxSteps": run.maxSteps,
        "summary": run.summary,
        "error": run.error,
        "startedAt": _iso(run.startedAt),
        "completedAt": _iso(run.completedAt),
        "createdAt": run.createdAt.isoformat(),
        "updatedAt": run.updatedAt.isoformat(),
        "steps": [
            {
                "id": s.id,
                "stepNumber": s.stepNumber,
                "kind": s.kind,
                "status": s.status,
                "title": s.title,
                "detail": s.detail,
                "input": s.input,
                "output": s.output,
                "error": s.error,
                "startedAt": _iso(s.startedAt),
                "completedAt": _iso(s.completedAt),
                "createdAt": s.createdAt.isoformat(),
            }
            for s in sorted(run.steps, key=lambda x: x.stepNumber)
        ],
        "approvals": [
            {
                "id": a.id,
                "action": a.action,
                "status": a.status,
                "payload": a.payload,
                "decisionReason": a.decisionReason,
                "decidedAt": _iso(a.decidedAt),
                "createdAt": a.createdAt.isoformat(),
            }
            for a in sorted(run.approvals, key=lambda x: x.createdAt, reverse=True)
        ],
    }
