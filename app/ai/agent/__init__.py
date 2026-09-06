# ============================================================
# Agent 系统统一导出（对应 src/lib/agent/index.ts）
#
# 模块结构：
#   types.py     — Pydantic 类型（PlanDraft / TaskDraft / AgentRunResponse ...）
#   runtime.py   — Phase 1: 自主学习循环（observe / analyze / execute / run_learning_agent）
#   decisions.py — Phase 2: Agent 决策留痕
#   report.py    — Phase 3: 学习报告生成
#   weekly.py    — 周度学习周报
#   service.py   — 计划生成（generate_plan_for_plan）+ AgentRun 运行管理
# ============================================================

# ---- 运行管理 / 计划生成（service） ----
from app.ai.agent.service import (
    cancel_agent_run,
    create_agent_run,
    decide_agent_approval,
    generate_plan_for_plan,
    get_agent_run_for_user,
    list_agent_runs,
    serialize_agent_run,
    fallback_draft,
    plan_draft_to_markdown,
)

# ---- 类型（types） ----
from app.ai.agent.types import (
    AgentContextSnapshot,
    AgentRunResponse,
    AgentRunStatus,
    PlanDraft,
    PlanTaskDraft,
    TaskDraft,
    agent_run_statuses,
)

# ---- Phase 1: Agent Runtime（runtime） ----
from app.ai.agent.runtime import (
    AGENT_COACH_PROMPT,
    analyze,
    execute_action,
    execute_agent,
    fallback_analysis,
    format_plan_for_approval,
    observe,
    plan_agent,
    run_learning_agent,
)

# ---- Phase 3: 报告生成（report） ----
from app.ai.agent.report import (
    format_report_as_markdown,
    generate_daily_report,
    generate_weekly_report,
)

# ---- Phase 2: AgentDecision（decisions） ----
from app.ai.agent.decisions import (
    create_decision,
    get_decision_stats,
    get_latest_analysis,
    list_decisions,
    update_decision_status,
)

# ---- 周度周报（weekly） ----
from app.ai.agent.weekly import create_weekly_report_notification

__all__ = [
    # service
    "cancel_agent_run",
    "create_agent_run",
    "decide_agent_approval",
    "generate_plan_for_plan",
    "get_agent_run_for_user",
    "list_agent_runs",
    "serialize_agent_run",
    "fallback_draft",
    "plan_draft_to_markdown",
    # types
    "AgentContextSnapshot",
    "AgentRunResponse",
    "AgentRunStatus",
    "PlanDraft",
    "PlanTaskDraft",
    "TaskDraft",
    "agent_run_statuses",
    # runtime
    "AGENT_COACH_PROMPT",
    "analyze",
    "execute_action",
    "execute_agent",
    "fallback_analysis",
    "format_plan_for_approval",
    "observe",
    "plan_agent",
    "run_learning_agent",
    # report
    "format_report_as_markdown",
    "generate_daily_report",
    "generate_weekly_report",
    # decisions
    "create_decision",
    "get_decision_stats",
    "get_latest_analysis",
    "list_decisions",
    "update_decision_status",
    # weekly
    "create_weekly_report_notification",
]
