# ============================================================
# 基础模型：用户与认证（对应 prisma User / Session / Account）
# ============================================================

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "user"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    email: Mapped[str] = mapped_column(String, unique=True)
    emailVerified: Mapped[bool] = mapped_column(Boolean, default=False)
    image: Mapped[str | None] = mapped_column(String, nullable=True)
    password: Mapped[str | None] = mapped_column(String, nullable=True)
    bio: Mapped[str | None] = mapped_column(String, nullable=True)
    theme: Mapped[str] = mapped_column(String, default="system")
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    sessions: Mapped[list["Session"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    plans: Mapped[list["Plan"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    checkins: Mapped[list["Checkin"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    studyRecords: Mapped[list["StudyRecord"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    memories: Mapped[list["UserMemory"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    planTasks: Mapped[list["PlanTask"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    agentRuns: Mapped[list["AgentRun"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    decisions: Mapped[list["AgentDecision"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    todos: Mapped[list["Todo"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    knowledgeDocs: Mapped[list["KnowledgeDoc"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    chatMessages: Mapped[list["ChatMessage"]] = relationship(back_populates="user")
    tokenUsages: Mapped[list["TokenUsage"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Session(Base):
    __tablename__ = "session"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String, unique=True)
    expiresAt: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ipAddress: Mapped[str | None] = mapped_column(String, nullable=True)
    userAgent: Mapped[str | None] = mapped_column(String, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped[User] = relationship(back_populates="sessions")


class Account(Base):
    __tablename__ = "account"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    providerId: Mapped[str] = mapped_column(String)
    accountId: Mapped[str] = mapped_column(String)
    provider: Mapped[str] = mapped_column(String, default="credential")
    password: Mapped[str | None] = mapped_column(String, nullable=True)
    accessToken: Mapped[str | None] = mapped_column(String, nullable=True)
    refreshToken: Mapped[str | None] = mapped_column(String, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    __table_args__ = (UniqueConstraint("providerId", "accountId", name="uq_account_provider_account"),)
