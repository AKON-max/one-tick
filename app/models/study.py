# ============================================================
# 学习核心模型（对应 prisma Plan / PlanTask / Todo / Checkin / StudyRecord）
# ============================================================

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Plan(Base):
    __tablename__ = "plan"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    goal: Mapped[str | None] = mapped_column(String, nullable=True)
    document: Mapped[str | None] = mapped_column(String, nullable=True)
    # 任务最后一次拆分时所用文档的哈希，用于判断文档改动后任务是否过期
    tasksSourceHash: Mapped[str | None] = mapped_column(String, nullable=True)
    # 任务正在后台拆分的起始时间（非空 = 刷新中）
    tasksSplittingAt: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    startDate: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, default="active")
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped["User"] = relationship(back_populates="plans")
    checkins: Mapped[list["Checkin"]] = relationship(back_populates="plan")
    tasks: Mapped[list["PlanTask"]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class PlanTask(Base):
    __tablename__ = "plantask"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    planId: Mapped[str] = mapped_column(ForeignKey("plan.id", ondelete="CASCADE"))
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    dayNumber: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekNumber: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[str] = mapped_column(String, default="study")
    status: Mapped[str] = mapped_column(String, default="pending")
    priority: Mapped[str] = mapped_column(String, default="normal")
    completedAt: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped["User"] = relationship(back_populates="planTasks")
    plan: Mapped["Plan"] = relationship(back_populates="tasks")

    __table_args__ = (
        Index("ix_plantask_planId", "planId"),
        Index("ix_plantask_user_status", "userId", "status"),
        Index("ix_plantask_user_day", "userId", "dayNumber"),
    )


class Todo(Base):
    __tablename__ = "todo"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped["User"] = relationship(back_populates="todos")

    __table_args__ = (
        Index("ix_todo_user_completed", "userId", "completed"),
        Index("ix_todo_user_created", "userId", "createdAt"),
    )


class Checkin(Base):
    __tablename__ = "checkin"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    planId: Mapped[str | None] = mapped_column(ForeignKey("plan.id"), nullable=True)
    sourceTaskId: Mapped[str | None] = mapped_column(String, nullable=True)
    content: Mapped[str] = mapped_column(String)
    hours: Mapped[float] = mapped_column(Float, default=0)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    mood: Mapped[str | None] = mapped_column(String, nullable=True)
    screenshot: Mapped[str | None] = mapped_column(String, nullable=True)
    checkinDate: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped["User"] = relationship(back_populates="checkins")
    plan: Mapped["Plan | None"] = relationship(back_populates="checkins")

    __table_args__ = (
        Index("ix_checkin_user_date", "userId", "checkinDate"),
        Index("ix_checkin_source_task", "sourceTaskId"),
    )


class StudyRecord(Base):
    __tablename__ = "studyrecord"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    totalMinutes: Mapped[float] = mapped_column(Float, default=0)
    subject: Mapped[str | None] = mapped_column(String, nullable=True)
    checkinId: Mapped[str | None] = mapped_column(String, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship(back_populates="studyRecords")

    __table_args__ = (Index("ix_studyrecord_user_date", "userId", "date"),)
