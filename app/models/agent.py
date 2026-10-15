# ============================================================
# AI 智能体模型
# ============================================================

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector as VECTOR

from app.db.session import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AgentRun(Base):
    """一次 Agent 运行批次"""

    __tablename__ = "agentrun"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    mode: Mapped[str] = mapped_column(String, default="planner")
    goal: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="queued")
    currentStep: Mapped[int] = mapped_column(Integer, default=0)
    maxSteps: Mapped[int] = mapped_column(Integer, default=12)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    startedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped["User"] = relationship(back_populates="agentRuns")
    steps: Mapped[list["AgentStep"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    approvals: Mapped[list["AgentApproval"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    toolCalls: Mapped[list["AgentToolCall"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    decisions: Mapped[list["AgentDecision"]] = relationship(back_populates="run")

    __table_args__ = (
        Index("ix_agentrun_user_updated", "userId", "updatedAt"),
        Index("ix_agentrun_user_status", "userId", "status"),
    )


class AgentStep(Base):
    """Agent 运行中的单个步骤"""

    __tablename__ = "agentstep"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    runId: Mapped[str] = mapped_column(ForeignKey("agentrun.id", ondelete="CASCADE"))
    stepNumber: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
    title: Mapped[str] = mapped_column(String)
    detail: Mapped[str | None] = mapped_column(String, nullable=True)
    input: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    startedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped["AgentRun"] = relationship(back_populates="steps")
    approvals: Mapped[list["AgentApproval"]] = relationship(back_populates="step", cascade="all, delete-orphan")
    toolCalls: Mapped[list["AgentToolCall"]] = relationship(back_populates="step", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("runId", "stepNumber", name="uq_agentstep_run_step"),
        Index("ix_agentstep_run_status", "runId", "status"),
    )


class AgentApproval(Base):
    """Agent 动作的人工审批"""

    __tablename__ = "agentapproval"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    runId: Mapped[str] = mapped_column(ForeignKey("agentrun.id", ondelete="CASCADE"))
    stepId: Mapped[str | None] = mapped_column(ForeignKey("agentstep.id"), nullable=True)
    action: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    decisionReason: Mapped[str | None] = mapped_column(String, nullable=True)
    decidedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped["AgentRun"] = relationship(back_populates="approvals")
    step: Mapped["AgentStep | None"] = relationship(back_populates="approvals")

    __table_args__ = (Index("ix_agentapproval_run_status", "runId", "status"),)


class AgentToolCall(Base):
    """Agent 的工具调用记录"""

    __tablename__ = "agenttoolcall"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    runId: Mapped[str] = mapped_column(ForeignKey("agentrun.id", ondelete="CASCADE"))
    stepId: Mapped[str | None] = mapped_column(ForeignKey("agentstep.id"), nullable=True)
    toolName: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="pending")
    idempotencyKey: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    input: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    startedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    run: Mapped["AgentRun"] = relationship(back_populates="toolCalls")
    step: Mapped["AgentStep | None"] = relationship(back_populates="toolCalls")

    __table_args__ = (
        Index("ix_agenttoolcall_run_status", "runId", "status"),
        Index("ix_agenttoolcall_run_tool", "runId", "toolName"),
    )


class AgentDecision(Base):
    """Agent 决策留痕"""

    __tablename__ = "agentdecision"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    runId: Mapped[str | None] = mapped_column(
        ForeignKey("agentrun.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    action: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="executed")
    feedback: Mapped[str | None] = mapped_column(String, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship(back_populates="decisions")
    run: Mapped["AgentRun | None"] = relationship(back_populates="decisions")

    __table_args__ = (
        Index("ix_agentdecision_user_created", "userId", "createdAt"),
        Index("ix_agentdecision_user_type", "userId", "type"),
        Index("ix_agentdecision_run", "runId"),
    )


class AgentSchedule(Base):
    """用户定时任务配置"""

    __tablename__ = "agentschedule"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String, default="daily_review")
    cron: Mapped[str] = mapped_column(String, default="0 9 * * *")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    lastRunAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    nextRunAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped["User"] = relationship()

    __table_args__ = (
        UniqueConstraint("userId", "type", name="uq_agentschedule_user_type"),
        Index("ix_agentschedule_enabled_next", "enabled", "nextRunAt"),
    )


class UserMemory(Base):
    """用户长期记忆"""

    __tablename__ = "usermemory"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String, default="fact")
    content: Mapped[str] = mapped_column(Text)
    # pgvector 向量列，用于记忆的语义检索
    embedding = mapped_column(VECTOR(1024), nullable=True)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    lastUsed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship(back_populates="memories")

    __table_args__ = (
        Index("ix_usermemory_user_type", "userId", "type"),
        Index("ix_usermemory_user_importance", "userId", "importance"),
        Index("ix_usermemory_user_lastused", "userId", "lastUsed"),
    )


class AIHistory(Base):
    """AI 对话历史"""

    __tablename__ = "aihistory"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    message: Mapped[str] = mapped_column(Text)
    response: Mapped[str] = mapped_column(Text)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship()

    __table_args__ = (Index("ix_aihistory_user_created", "userId", "createdAt"),)

