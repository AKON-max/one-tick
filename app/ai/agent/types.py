# ============================================================
# Agent 类型定义
#
# 字段名与 TS 保持一致（camelCase），Pydantic 模型约束
# 对照 zod schema：长度/取值/默认值逐条对齐。
# ============================================================

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# ---- 运行状态 ----

agent_run_statuses = [
    "queued",
    "running",
    "awaiting_approval",
    "completed",
    "failed",
    "cancelled",
    "rejected",
]

AgentRunStatus = Literal[
    "queued",
    "running",
    "awaiting_approval",
    "completed",
    "failed",
    "cancelled",
    "rejected",
]

# ---- 任务草案 ----

TaskCategory = Literal["study", "project", "review", "exercise"]
TaskPriority = Literal["high", "normal", "low"]


class TaskDraft(BaseModel):
    """单条任务草案"""

    title: str = Field(min_length=1, max_length=160)
    description: Optional[str] = Field(default=None, max_length=600)
    dayNumber: Optional[int] = Field(default=None, ge=1, le=365)
    weekNumber: Optional[int] = Field(default=None, ge=1, le=52)
    category: TaskCategory = "study"
    priority: TaskPriority = "normal"


# 别名：保持既有的 planTaskDraftSchema 命名
PlanTaskDraft = TaskDraft


# ---- 计划草案 ----

class PlanDraft(BaseModel):
    """学习计划草案"""

    name: str = Field(min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=600)
    goal: str = Field(min_length=1, max_length=600)
    tasks: list[TaskDraft] = Field(default_factory=list, max_length=40)
    assumptions: list[str] = Field(default_factory=list, max_length=8)


# ---- 上下文快照（AgentContextSnapshot） ----

class AgentContextSnapshot(BaseModel):
    """计划生成场景下的用户上下文快照"""

    totalCheckins: int
    activePlans: list[dict[str, Any]]
    memoryCount: int


# ---- Agent 运行响应（AgentRunResponse） ----

class AgentRunStepResponse(BaseModel):
    """AgentRun 的步骤序列化"""

    id: str
    stepNumber: int
    kind: str
    status: str
    title: str
    detail: Optional[str] = None
    input: Any = None
    output: Any = None
    error: Optional[str] = None
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None
    createdAt: str


class AgentRunApprovalResponse(BaseModel):
    """AgentRun 的审批序列化"""

    id: str
    action: str
    status: str
    payload: Any = None
    decisionReason: Optional[str] = None
    decidedAt: Optional[str] = None
    createdAt: str


class AgentRunResponse(BaseModel):
    """Agent 运行响应"""

    id: str
    mode: str
    goal: str
    status: str
    currentStep: int
    maxSteps: int
    summary: Optional[str] = None
    error: Optional[str] = None
    startedAt: Optional[str] = None
    completedAt: Optional[str] = None
    createdAt: str
    updatedAt: str
    steps: list[AgentRunStepResponse]
    approvals: list[AgentRunApprovalResponse]
