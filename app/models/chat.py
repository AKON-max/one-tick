# ============================================================
# 聊天与对话模型
# ============================================================

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ChatMessage(Base):
    """聊天室消息"""

    __tablename__ = "chatmessage"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str | None] = mapped_column(
        ForeignKey("user.id", ondelete="SET NULL"), nullable=True
    )
    role: Mapped[str] = mapped_column(String, default="user")
    content: Mapped[str] = mapped_column(Text)
    # 聊天室 AI 角色（温柔宝/嘴欠宝），AI 消息用于区分上下文标注不串风格
    aiRole: Mapped[str | None] = mapped_column(String, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User | None"] = relationship(back_populates="chatMessages")

    __table_args__ = (Index("ix_chatmessage_created", "createdAt"),)


class Conversation(Base):
    """AI 对话会话"""

    __tablename__ = "conversation"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String, default="新对话")
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped["User"] = relationship(back_populates="conversations")
    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_conversation_user_updated", "userId", "updatedAt"),)


class ConversationMessage(Base):
    """会话中的单条消息"""

    __tablename__ = "conversationmessage"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    conversationId: Mapped[str] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")

    __table_args__ = (Index("ix_convmsg_conv_created", "conversationId", "createdAt"),)
