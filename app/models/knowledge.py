# ============================================================
# 知识库 / 文档模型
# ============================================================

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector as VECTOR

from app.db.session import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    """用户 Markdown 文档"""

    __tablename__ = "document"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text, default="")
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped["User"] = relationship()

    __table_args__ = (Index("ix_document_user_updated", "userId", "updatedAt"),)


class DocumentChunk(Base):
    """文档分块"""

    __tablename__ = "documentchunk"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    sourceName: Mapped[str] = mapped_column(String)
    sourceType: Mapped[str] = mapped_column(String, default="text")
    chunkIndex: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    embedding = mapped_column(VECTOR(1024), nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship()

    __table_args__ = (
        Index("ix_docchunk_user_source", "userId", "sourceName"),
        Index("ix_docchunk_source", "sourceName"),
    )


class KnowledgeDoc(Base):
    """知识库源文档"""

    __tablename__ = "knowledgedoc"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    userId: Mapped[str] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    sourceName: Mapped[str] = mapped_column(String)
    sourceType: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    user: Mapped["User"] = relationship(back_populates="knowledgeDocs")

    __table_args__ = (
        UniqueConstraint("userId", "sourceName", name="uq_knowledgedoc_user_source"),
        Index("ix_knowledgedoc_user", "userId"),
    )


class PlanTemplate(Base):
    """新用户引导计划模板"""

    __tablename__ = "plantemplate"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    goal: Mapped[str | None] = mapped_column(String, nullable=True)
    # Markdown，含「## 任务安排」段落；克隆后 syncTasksFromDocument 生成任务
    document: Mapped[str | None] = mapped_column(Text, nullable=True)
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DocumentTemplate(Base):
    """新用户引导文档模板"""

    __tablename__ = "documenttemplate"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(Text, default="")
    createdAt: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
