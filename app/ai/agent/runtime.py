# ============================================================
# Agent Runtime — 自主学习循环的核心引擎
#
# 架构设计：
#
#   run_learning_agent(user_id)
#         │
#         ├── Step 1: observe(user_id)
#         │   └── 收集全部用户上下文（统计/计划/任务/记忆）
#         │
#         ├── Step 2: analyze(context, memories, user_id)
#         │   └── 调用 LLM 进行诊断（JSON 结构化输出）
#         │
#         ├── Step 3: plan_agent(context, analysis)
#         │   └── 行动列表（Analyze + Plan 由 LLM 一次调用完成）
#         │
#         └── Step 4: execute_agent(user_id, plan, ...)
#             └── 根据 action type 调用对应工具
#
# 设计原则：
# ① 每个 Step 是独立函数，可单独测试和复用
# ② LLM 调用带 fallback：模型不可用时返回基于规则的分析
# ③ 所有决策记录到 AgentRun + AgentDecision（可追溯）
# ④ 不依赖数据库迁移 — 使用已有 AgentRun/AgentStep/AgentApproval 模型
# ============================================================

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.ai.agent.decisions import create_decision
from app.ai.agent.report import format_report_as_markdown, generate_daily_report
from app.ai.memory import get_relevant_memories, touch_memories
from app.ai.model_pool import UsageContext, completions_with_fallback
from app.db.session import SessionLocal
from app.models.agent import AgentApproval, AgentRun, AgentStep, UserMemory
from app.models.misc import Notification
from app.models.study import Checkin, Plan, PlanTask, StudyRecord

# ---- Agent Coach 系统提示词 ----

AGENT_COACH_PROMPT = """你是 Summer，一个贴心的学习伙伴。你不是冷冰冰的报告机器人——你像朋友一样跟用户聊天，关心他们的学习状态。

## 说话方式
- 用「你」直接跟用户对话，像微信聊天一样自然
- 不要说「用户」「该用户」「该计划」这种第三人称
- 语气温暖但不油腻，像认真关心朋友的学习进度
- 可以适当用 emoji，但不要每条消息都堆满

## 你的工作

### 先看数据
系统会给你用户的学习数据：总时长、打卡天数、计划进度、待办任务、最近学了什么、之前记下的目标。

### 再想问题
1. 用户有没有偏离自己定下的目标？
2. 是不是有什么卡住了？哪些任务一直拖着没做？
3. 最近的学习节奏怎么样？是太紧还是太松？
4. 接下来最应该做什么？

### 然后给建议
基于上面的分析，生成 1-3 条具体的行动建议。每条建议要说清楚：
- 你看到了什么（引用具体数据）
- 你觉得应该怎么做
- 为什么这样做有帮助

## 输出格式

严格输出 JSON：
```json
{
  "status": "on_track" | "need_attention" | "need_adjustment" | "at_risk",
  "summary": "一句自然的总结，像朋友聊天一样",
  "findings": [
    {
      "category": "progress" | "weakness" | "deviation" | "streak" | "habit",
      "severity": "info" | "warning" | "critical",
      "detail": "像发消息一样自然地告诉用户你发现了什么，用「你」来称呼",
      "evidence": { "metric": "值" }
    }
  ],
  "actions": [
    {
      "type": "ADJUST_PLAN" | "CREATE_TASK" | "SEND_REMINDER" | "GENERATE_REPORT" | "ENCOURAGE",
      "priority": "high" | "normal" | "low",
      "reason": "为什么要做这个动作（自然的语气）",
      "detail": "具体做什么，像朋友给建议一样"
    }
  ]
}
```

## 原则
- 基于真实数据，不要编造
- 有问题就直接说，不要只讲好听的
- 建议要具体——「今天下午花30分钟做一道链表题」比「加强算法练习」好得多
- 一切正常的时候，也真诚地说一句「今天不错」
- 所有内容用中文
"""

# ---- Helper ----

def _now_utc() -> datetime:
    """当前 UTC 时间（与模型默认值一致）"""
    return datetime.now(timezone.utc)


def _utc_date(dt: datetime) -> str:
    """datetime → UTC 日期字符串"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def _local_midnight_utc() -> datetime:
    """服务器本地时区「今天零点」→ UTC，用于日界比较"""
    local_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    return local_midnight.astimezone(timezone.utc)


def _create_notification(
    db,
    user_id: str,
    ntype: str,
    title: str,
    content: str,
    action_url: str | None = None,
) -> Notification | None:
    """创建通知；同一用户当天同类型只保留一条"""
    try:
        start_of_day = _local_midnight_utc()
        existing = db.execute(
            select(Notification)
            .where(
                Notification.userId == user_id,
                Notification.type == ntype,
                Notification.createdAt >= start_of_day,
            )
        ).scalars().first()
        if existing:
            print(
                f"[Notification] 今日同类型通知已存在，跳过: type={ntype} user={user_id}"
            )
            return None
        notification = Notification(
            userId=user_id,
            type=ntype,
            title=title,
            content=content,
            actionUrl=action_url,
        )
        db.add(notification)
        db.flush()
        return notification
    except Exception as error:  # noqa: BLE001
        print(f"[Notification] 创建失败: {error}")
        return None


# ============================================================
# Step 1: Observe — 收集用户全部学习上下文
# ============================================================

def observe(user_id: str) -> dict:
    """收集用户全部学习上下文

    统计（打卡仅为小岛计数：不含时长/科目/心情）、
    活跃计划（含任务统计）、待办任务、目标类长期记忆、今日专注、最近 7 次打卡。
    """
    today_start = _local_midnight_utc()

    with SessionLocal() as db:
        # 全部打卡（时间倒序）
        all_checkins = db.execute(
            select(Checkin)
            .where(Checkin.userId == user_id)
            .order_by(Checkin.checkinDate.desc())
        ).scalars().all()

        # 活跃计划（含任务统计）
        active_plans = db.execute(
            select(Plan).where(Plan.userId == user_id, Plan.status == "active")
        ).scalars().all()
        plan_ids = [p.id for p in active_plans]
        tasks_by_plan: dict[str, list[PlanTask]] = {}
        if plan_ids:
            rows = db.execute(
                select(PlanTask).where(PlanTask.planId.in_(plan_ids))
            ).scalars().all()
            for t in rows:
                tasks_by_plan.setdefault(t.planId, []).append(t)

        # 待办任务（pending / in_progress，含计划名）
        pending_rows = db.execute(
            select(PlanTask, Plan.name)
            .join(Plan, Plan.id == PlanTask.planId)
            .where(
                PlanTask.userId == user_id,
                PlanTask.status.in_(["pending", "in_progress"]),
            )
            .order_by(PlanTask.priority.desc(), PlanTask.dayNumber.asc())
            .limit(20)
        ).all()

        # 目标类长期记忆
        goal_memories = db.execute(
            select(UserMemory.content).where(
                UserMemory.userId == user_id, UserMemory.type == "goal"
            )
        ).scalars().all()

        # 今日专注记录（番茄钟，来自 StudyRecord）
        today_focus_records = db.execute(
            select(StudyRecord.totalMinutes).where(
                StudyRecord.userId == user_id, StudyRecord.date >= today_start
            )
        ).scalars().all()

    # ---- 连续打卡（UTC 日期） ----
    check_dates = {_utc_date(c.checkinDate) for c in all_checkins}
    streak = 0
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    for i in range(365):
        d = today - timedelta(days=i)
        if d.strftime("%Y-%m-%d") in check_dates:
            streak += 1
        elif i > 0:
            break

    # ---- 计划进度（任务完成度） ----
    plans = []
    for plan in active_plans:
        tasks = tasks_by_plan.get(plan.id, [])
        total = len(tasks)
        done = len([t for t in tasks if t.status == "done"])
        task_stats = {
            "total": total,
            "done": done,
            "inProgress": len([t for t in tasks if t.status == "in_progress"]),
            "pending": len([t for t in tasks if t.status == "pending"]),
            "skipped": len([t for t in tasks if t.status == "skipped"]),
        }
        plans.append(
            {
                "id": plan.id,
                "name": plan.name,
                "progress": round(done / total * 100) if total > 0 else 0,
                "taskStats": task_stats,
            }
        )

    # ---- 近期打卡（最近 7 次，仅日期） ----
    recent_checkins = [{"date": _utc_date(c.checkinDate)} for c in all_checkins[:7]]

    # ---- 今日专注（番茄钟） ----
    today_focus_minutes = round(sum(today_focus_records))
    today_focus_sessions = len(today_focus_records)

    return {
        "userId": user_id,
        "collectedAt": _now_utc().isoformat(),
        "profile": {
            "goalMemories": list(goal_memories),
            "activePlanCount": len(active_plans),
            "activePlanNames": [p.name for p in active_plans],
        },
        "stats": {
            "streak": streak,
            "totalCheckins": len(all_checkins),
        },
        "focus": {
            "todayMinutes": today_focus_minutes,
            "todaySessions": today_focus_sessions,
        },
        "plans": plans,
        "pendingTasks": [
            {
                "id": t.id,
                "title": t.title,
                "planName": plan_name,
                "priority": t.priority,
                "category": t.category,
                "dayNumber": t.dayNumber,
            }
            for t, plan_name in pending_rows
        ],
        "recentCheckins": recent_checkins,
    }


# ============================================================
# Step 2: Analyze — LLM 分析学习状态
# ============================================================

def analyze(context: dict, memories: list[dict], user_id: str) -> dict:
    """用 LLM 分析学习状态并输出行动建议"""
    # 构建分析 prompt
    memory_text = (
        "\n".join(f"- [{m.get('type')}] {m.get('content')}" for m in memories)
        if memories
        else "暂无长期记忆"
    )

    # 精简输入，输出空间留给分析 JSON
    plan_summary = [
        {
            "name": p["name"],
            "progress": f"{p['progress']}%",
            "tasks": f"{p['taskStats']['done']}/{p['taskStats']['total']} done",
        }
        for p in context.get("plans", [])
    ]
    recent_activity = [c["date"] for c in context.get("recentCheckins", [])[:7]]

    user_message = json.dumps(
        {
            "instruction": "分析用户学习数据，输出 JSON。简明扼要，findings 不超过 5 条，actions 不超过 3 条。",
            "profile": context.get("profile", {}),
            "stats": {
                "streak": context.get("stats", {}).get("streak", 0),
                "totalCheckins": context.get("stats", {}).get("totalCheckins", 0),
            },
            "focus": {
                "todayMinutes": context.get("focus", {}).get("todayMinutes", 0),
                "todaySessions": context.get("focus", {}).get("todaySessions", 0),
            },
            "plans": plan_summary,
            "pendingCount": len(context.get("pendingTasks", [])),
            "recentActivity": recent_activity,
            "memories": memory_text,
        },
        ensure_ascii=False,
    )

    try:
        data, _model = completions_with_fallback(
            "high",
            lambda entry, client: client.chat.completions.create(
                model=entry.modelName,
                temperature=0.3,
                max_tokens=16384,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": f"{AGENT_COACH_PROMPT}\n\n请严格按照输出格式返回 JSON。不要包含 Markdown 代码块标记。",
                    },
                    {"role": "user", "content": user_message},
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
            print(
                "[Agent Runtime] LLM 返回空内容，finish_reason:",
                getattr(data.choices[0], "finish_reason", None) if getattr(data, "choices", None) else None,
            )
            raise ValueError("LLM 返回空内容")

        print(f"[Agent Runtime] LLM 分析结果: {text[:200]}...")
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("LLM 输出不是 JSON 对象")
        return {
            "status": parsed.get("status") or "on_track",
            "summary": parsed.get("summary") or "分析完成",
            "findings": parsed.get("findings") if isinstance(parsed.get("findings"), list) else [],
            "actions": parsed.get("actions") if isinstance(parsed.get("actions"), list) else [],
        }
    except Exception as error:  # noqa: BLE001
        print(f"[Agent Runtime] LLM 分析失败，使用规则兜底: {error}")
        return fallback_analysis(context)


# ---- 规则兜底分析 ----

def fallback_analysis(context: dict) -> dict:
    """规则兜底分析 — 当 LLM 不可用时，基于数据阈值做判断"""
    findings: list[dict] = []
    actions: list[dict] = []

    # 1. 检查是否有计划
    if len(context.get("plans", [])) == 0:
        findings.append(
            {
                "category": "progress",
                "severity": "warning",
                "detail": "你还没有创建学习计划哦，有个明确的学习路线会让效率高很多",
                "evidence": {},
            }
        )
        actions.append(
            {
                "type": "ENCOURAGE",
                "priority": "high",
                "reason": "还没有学习计划",
                "detail": "要不要创建一个学习计划？我可以帮你把大目标拆成每天的小任务",
            }
        )

    # 2. 检查计划进度
    for plan in context.get("plans", []):
        task_stats = plan.get("taskStats", {})
        if plan.get("progress", 0) < 30 and task_stats.get("total", 0) > 5:
            findings.append(
                {
                    "category": "progress",
                    "severity": "warning",
                    "detail": f"「{plan.get('name')}」完成了 {plan.get('progress')}%，进度有点慢，不过没关系，我们一起看看怎么调整",
                    "evidence": {
                        "progress": plan.get("progress"),
                        "taskTotal": task_stats.get("total"),
                    },
                }
            )
        if task_stats.get("pending", 0) > 5:
            actions.append(
                {
                    "type": "ADJUST_PLAN",
                    "priority": "normal",
                    "reason": f"「{plan.get('name')}」堆了 {task_stats.get('pending')} 个待办",
                    "detail": f"「{plan.get('name')}」攒了不少任务，要不要筛一下哪些是真正重要的，先做那些？",
                }
            )

    # 3. 检查连续打卡
    stats = context.get("stats", {})
    if stats.get("streak", 0) == 0 and stats.get("totalCheckins", 0) > 5:
        findings.append(
            {
                "category": "streak",
                "severity": "info",
                "detail": "今天还没打卡呢，别忘了记录你今天学了什么～",
                "evidence": {"streak": 0},
            }
        )

    # 生成状态
    has_warnings = any(f["severity"] == "warning" for f in findings)
    has_critical = any(f["severity"] == "critical" for f in findings)
    status = (
        "at_risk"
        if has_critical
        else ("need_attention" if has_warnings else "on_track")
    )
    summary = (
        f"今天已经连续打卡 {stats.get('streak', 0)} 天了，{len(context.get('plans', []))} 个计划在进行中，继续保持！"
        if len(context.get("plans", [])) > 0
        else "还没有学习计划，要不要我帮你定一个？"
    )

    return {
        "status": status,
        "summary": summary,
        "findings": findings,
        "actions": actions,
    }


# ============================================================
# Step 3: Plan — 生成行动计划（Analyze + Plan 由 LLM 一次调用完成）
# ============================================================

def plan_agent(context: dict, analysis: dict) -> list[dict]:
    """行动计划：直接复用 analyze 输出的 actions"""
    return list(analysis.get("actions") or [])


def format_plan_for_approval(analysis: dict) -> list[dict]:
    """仅保留 high/normal 优先级的行动，供写入 AgentApproval"""
    return [
        {"action": a["type"], "payload": a}
        for a in analysis.get("actions", [])
        if a.get("priority") in ("high", "normal")
    ]


# ============================================================
# Step 4: Execute — 执行 Agent 行动计划
# ============================================================

def execute_action(
    user_id: str,
    action: dict,
    context: dict | None = None,
    analysis: dict | None = None,
    db=None,
) -> dict:
    """执行一条 Agent 行动

    - SEND_REMINDER → 创建真实的 Notification 记录
    - GENERATE_REPORT → 生成结构化日报并保存为 Notification
    - CREATE_TASK → 尝试自动创建任务（查找活跃计划）
    - ADJUST_PLAN → 创建通知提醒用户确认调整
    """
    own = db is None
    if own:
        db = SessionLocal()
    try:
        action_type = action.get("type")

        if action_type == "ENCOURAGE":
            try:
                _create_notification(
                    db, user_id, "encouragement", "想跟你说", action.get("detail", "")
                )
                db.commit()
            except Exception:  # noqa: BLE001
                # 通知失败不影响主流程
                db.rollback()
            return {
                "type": action_type,
                "success": True,
                "message": action.get("detail", ""),
            }

        if action_type == "CREATE_TASK":
            # 尝试自动创建任务：查找用户的活跃计划，添加到第一个计划
            try:
                active_plan = db.execute(
                    select(Plan)
                    .where(Plan.userId == user_id, Plan.status == "active")
                    .order_by(Plan.createdAt.desc())
                ).scalars().first()

                if active_plan is None:
                    return {
                        "type": action_type,
                        "success": False,
                        "message": f"无法自动创建任务（用户无活跃计划）：{action.get('detail', '')}",
                    }

                task = PlanTask(
                    planId=active_plan.id,
                    userId=user_id,
                    title=action.get("detail", "")[:160],
                    description=f"系统自动创建 — {action.get('reason', '')}",
                    category="study",
                    priority=action.get("priority", "normal"),
                )
                db.add(task)
                db.commit()
                db.refresh(task)

                return {
                    "type": action_type,
                    "success": True,
                    "message": f"已在计划「{active_plan.name}」中自动创建任务「{task.title}」",
                }
            except Exception as error:  # noqa: BLE001
                db.rollback()
                return {
                    "type": action_type,
                    "success": False,
                    "message": f"创建任务失败：{error}",
                }

        if action_type == "ADJUST_PLAN":
            try:
                _create_notification(
                    db,
                    user_id,
                    "analysis",
                    "关于你的学习计划",
                    action.get("detail", ""),
                    action_url="/agent",
                )
                db.commit()
                return {
                    "type": action_type,
                    "success": True,
                    "message": f"已生成计划调整通知：{action.get('detail', '')}",
                }
            except Exception:  # noqa: BLE001
                db.rollback()
                return {
                    "type": action_type,
                    "success": False,
                    "message": f"计划调整通知生成失败：{action.get('detail', '')}",
                }

        if action_type == "SEND_REMINDER":
            try:
                notification = _create_notification(
                    db,
                    user_id,
                    "reminder",
                    "别忘了哦",
                    action.get("detail", ""),
                    action_url="/checkin",
                )
                db.commit()
                if notification:
                    return {
                        "type": action_type,
                        "success": True,
                        "message": f"已生成提醒通知：{action.get('detail', '')}",
                    }
                # 今日提醒已发送过（每日节流去重），视为成功但不重复打扰
                return {
                    "type": action_type,
                    "success": True,
                    "message": "今日提醒已发送过，已跳过重复提醒",
                }
            except Exception:  # noqa: BLE001
                db.rollback()
                return {
                    "type": action_type,
                    "success": False,
                    "message": f"提醒生成失败：{action.get('detail', '')}",
                }

        if action_type == "GENERATE_REPORT":
            # 生成结构化的每日学习报告
            try:
                if context and analysis:
                    report = generate_daily_report(user_id, context, analysis)
                    # 将报告保存为通知
                    markdown = format_report_as_markdown(report)
                    _create_notification(
                        db,
                        user_id,
                        "report",
                        f"{report['date']} 学习小结",
                        markdown,
                        action_url="/agent",
                    )
                    db.commit()
                    print(
                        f"[Agent Runtime] 已生成学习报告: status={report['status']}, summary={report['summary'][:60]}"
                    )
                    return {
                        "type": action_type,
                        "success": True,
                        "message": f"学习报告已生成：{report['summary']}",
                    }
                # 无 context/analysis 时降级为简单通知
                _create_notification(
                    db,
                    user_id,
                    "report",
                    "学习小结",
                    action.get("detail", ""),
                    action_url="/agent",
                )
                db.commit()
                return {
                    "type": action_type,
                    "success": True,
                    "message": f"学习报告摘要：{action.get('detail', '')}",
                }
            except Exception:  # noqa: BLE001
                db.rollback()
                return {
                    "type": action_type,
                    "success": False,
                    "message": f"报告生成失败：{action.get('detail', '')}",
                }

        return {
            "type": action_type,
            "success": False,
            "message": f"未知 action 类型：{action_type}",
        }
    finally:
        if own:
            db.close()


def execute_agent(
    user_id: str,
    plan: list[dict],
    run_id: str | None = None,
    db=None,
    context: dict | None = None,
    analysis: dict | None = None,
) -> list[dict]:
    """批量执行 Agent 行动计划"""
    results: list[dict] = []
    for action in plan:
        result = execute_action(user_id, action, context, analysis, db=db)
        results.append(result)
        print(
            f"[Agent Runtime]   action={result['type']} success={result['success']}: {result['message'][:80]}"
        )
    return results


# ============================================================
# 完整 Agent 循环：Observe → Analyze → Plan → Execute → Record
# ============================================================

def run_learning_agent(
    user_id: str,
    options: dict | None = None,
) -> dict:
    """完整自主学习循环

    options: {"persist": bool(默认 True), "mode": "coach" | "review" | "daily"(默认 "coach")}
    全量落库 AgentRun + AgentStep（每步 input/output JSON）+ AgentDecision。
    """
    opts = options or {}
    persist = bool(opts.get("persist", True))
    mode = opts.get("mode", "coach")
    started_at = _now_utc()

    print(f"[Agent Runtime] ====== 开始运行 (mode: {mode}) ======")

    run_id: str | None = None
    db = SessionLocal()
    try:
        # 创建 AgentRun 记录 + Step 1
        run: AgentRun | None = None
        if persist:
            run = AgentRun(
                userId=user_id,
                mode=mode,
                goal="每日学习状态自动分析" if mode == "daily" else f"自主{mode}分析",
                status="running",
                startedAt=started_at,
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
                    title="Observe: 收集学习上下文",
                    detail="正在汇总学习统计、计划进度、待办任务和长期记忆。",
                    startedAt=started_at,
                )
            )
            db.commit()
            run_id = run.id

        # ---- Step 1: Observe ----
        print("[Agent Runtime] Step 1/4: Observe")
        context = observe(user_id)

        # 获取长期记忆 + 标记被检索使用（用于冷淘汰）
        memories = get_relevant_memories(user_id, 20)
        touch_memories([m["id"] for m in memories])

        # 更新 Step 1
        if run:
            step1 = db.execute(
                select(AgentStep).where(
                    AgentStep.runId == run.id, AgentStep.stepNumber == 1
                )
            ).scalar_one()
            step1.status = "completed"
            step1.output = {
                "stats": context["stats"],
                "plansCount": len(context["plans"]),
                "pendingTasks": len(context["pendingTasks"]),
                "memoriesCount": len(memories),
            }
            step1.completedAt = _now_utc()
            db.commit()

        # ---- Step 2-3: Analyze + Plan (LLM 一次调用完成两步) ----
        print("[Agent Runtime] Step 2-3/4: Analyze + Plan")
        analysis_step_num = 2

        if run:
            db.add(
                AgentStep(
                    runId=run.id,
                    stepNumber=analysis_step_num,
                    kind="analysis",
                    status="running",
                    title="Analyze + Plan: LLM 分析与规划",
                    detail="正在用 LLM 分析学习状态并生成行动建议。",
                    input={
                        "statsSummary": f"连续打卡{context['stats']['streak']}天，共打卡{context['stats']['totalCheckins']}次",
                        "plansCount": len(context["plans"]),
                        "pendingTasks": len(context["pendingTasks"]),
                    },
                    startedAt=_now_utc(),
                )
            )
            db.commit()

        analysis = analyze(context, memories, user_id)

        # 更新分析步骤 + 写入 AgentApproval（UI 可展示）
        if run:
            analysis_step = db.execute(
                select(AgentStep).where(
                    AgentStep.runId == run.id, AgentStep.stepNumber == analysis_step_num
                )
            ).scalar_one()
            analysis_step.status = "completed"
            analysis_step.output = {
                "status": analysis["status"],
                "summary": analysis["summary"],
                "findingsCount": len(analysis["findings"]),
                "actionsCount": len(analysis["actions"]),
            }
            analysis_step.detail = analysis["summary"]
            analysis_step.completedAt = _now_utc()

            for finding in analysis["findings"]:
                db.add(
                    AgentApproval(
                        runId=run.id,
                        stepId=analysis_step.id,
                        action="daily_analysis",
                        status="pending",
                        payload={"type": "finding", **finding},
                    )
                )
            for action in analysis["actions"]:
                db.add(
                    AgentApproval(
                        runId=run.id,
                        stepId=analysis_step.id,
                        action="daily_action",
                        status="pending",
                        payload={**action, "type": "action"},
                    )
                )
            db.commit()

        # ---- Step 4: Execute ----
        print("[Agent Runtime] Step 4/4: Execute")
        execute_step_num = 3
        executed_actions: list[dict] = []

        if run:
            db.add(
                AgentStep(
                    runId=run.id,
                    stepNumber=execute_step_num,
                    kind="execution",
                    status="running",
                    title="Execute: 执行行动建议",
                    detail=f"正在执行 {len(analysis['actions'])} 条建议。",
                    input={"actions": analysis["actions"]},
                    startedAt=_now_utc(),
                )
            )
            db.commit()

        for action in analysis["actions"]:
            result = execute_action(user_id, action, context, analysis, db=db)
            executed_actions.append(result)
            print(
                f"[Agent Runtime]   action={result['type']} success={result['success']}: {result['message'][:80]}"
            )

            # 记录 Agent 决策到 AgentDecision 表
            if run:
                if action["type"] == "ADJUST_PLAN":
                    decision_type = "PLAN_ADJUST"
                elif action["type"] == "SEND_REMINDER":
                    decision_type = "REMINDER"
                elif action["type"] == "CREATE_TASK":
                    decision_type = "TASK_CREATE"
                else:
                    decision_type = "ANALYSIS"
                create_decision(
                    db,
                    user_id,
                    run.id,
                    decision_type,
                    action["reason"],
                    {
                        "detail": action["detail"],
                        "priority": action["priority"],
                        "executed": result["success"],
                        "message": result["message"],
                    },
                    status="pending",  # 等用户确认后才算 executed
                )

        # 更新执行步骤 + 完成 Run
        if run:
            exec_step = db.execute(
                select(AgentStep).where(
                    AgentStep.runId == run.id, AgentStep.stepNumber == execute_step_num
                )
            ).scalar_one()
            exec_step.status = "completed"
            exec_step.output = {"executedActions": executed_actions}
            exec_step.detail = f"执行了 {len(executed_actions)} 条建议，{sum(1 for a in executed_actions if a['success'])} 条成功"
            exec_step.completedAt = _now_utc()

            run.status = "completed"
            run.currentStep = execute_step_num
            run.summary = analysis["summary"]
            run.completedAt = _now_utc()
            db.commit()

        print(
            f"[Agent Runtime] ====== 完成: {analysis['status']} | {len(executed_actions)} actions ======"
        )

        return {
            "runId": run_id or "no-persist",
            "status": analysis["status"],
            "context": context,
            "analysis": analysis,
            "executedActions": executed_actions,
        }
    except Exception as error:  # noqa: BLE001
        message = str(error)
        print(f"[Agent Runtime] 执行失败: {message}")

        if run_id:
            try:
                db.rollback()
                run_row = db.get(AgentRun, run_id)
                if run_row is not None:
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
            except Exception:  # noqa: BLE001
                pass

        return {
            "runId": run_id or "no-persist",
            "status": "at_risk",
            "context": None,
            "analysis": None,
            "executedActions": [],
            "error": message,
        }
    finally:
        db.close()
