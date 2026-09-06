# ============================================================
# 杂项模型（对应 prisma Notification / TokenUsage / AvatarChange）
# ============================================================

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Notification(Base):
    """通知（对应 prisma Notification，含 daily/weekly 去重逻辑）"""

    __tablename__ = "notification"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String, default="reminder")
    title: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    actionUrl: Mapped[str | None] = mapped_column(String, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship(back_populates="notifications")

    __table_args__ = (
        Index("ix_notification_user_read_created", "userId", "read", "createdAt"),
        Index("ix_notification_user_type", "userId", "type"),
    )


class TokenUsage(Base):
    """用户 AI token 用量（对应 prisma TokenUsage，每日限额）"""

    __tablename__ = "tokenusage"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    surface: Mapped[str] = mapped_column(String)  # agent | studio | chatroom | title | memory | split | agent-bg
    tier: Mapped[str] = mapped_column(String)  # low | high
    model: Mapped[str] = mapped_column(String)  # 实际使用模型
    inputTokens: Mapped[int] = mapped_column(Integer, default=0)
    outputTokens: Mapped[int] = mapped_column(Integer, default=0)
    totalTokens: Mapped[int] = mapped_column(Integer, default=0)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship(back_populates="tokenUsages")

    __table_args__ = (Index("ix_tokenusage_user_created", "userId", "createdAt"),)


class AvatarChange(Base):
    """头像变更记录（对应 prisma AvatarChange）"""

    __tablename__ = "avatarchange"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (Index("ix_avatarchange_user_created", "userId", "createdAt"),)
