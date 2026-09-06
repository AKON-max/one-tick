# ============================================================
# 对话会话路由（对应 src/app/api/conversations/** + messages）
# ============================================================

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.base import User
from app.models.chat import Conversation, ConversationMessage

router = APIRouter(prefix="/api/conversations", tags=["conversations"])


class ConversationCreateRequest(BaseModel):
    title: str | None = None


class MessageResponse(BaseModel):
    id: str
    conversationId: str
    role: str
    content: str
    createdAt: str


class ConversationResponse(BaseModel):
    id: str
    title: str
    createdAt: str
    updatedAt: str
    messages: list[MessageResponse] = []

    @classmethod
    def from_model(cls, c: Conversation, messages: list | None = None) -> "ConversationResponse":
        return cls(
            id=c.id,
            title=c.title,
            createdAt=c.createdAt.isoformat(),
            updatedAt=c.updatedAt.isoformat(),
            messages=[
                MessageResponse(
                    id=m.id,
                    conversationId=m.conversationId,
                    role=m.role,
                    content=m.content,
                    createdAt=m.createdAt.isoformat(),
                )
                for m in (messages or [])
            ],
        )


@router.get("")
def list_conversations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """对话列表（按更新时间倒序，只带首条消息预览）

    返回 {conversations: [...]}，对齐原 src/app/api/conversations/route.ts。
    """
    conversations = (
        db.execute(
            select(Conversation)
            .where(Conversation.userId == user.id)
            .order_by(Conversation.updatedAt.desc())
        )
        .scalars()
        .all()
    )
    result = []
    for c in conversations:
        first = (
            db.execute(
                select(ConversationMessage)
                .where(ConversationMessage.conversationId == c.id)
                .order_by(ConversationMessage.createdAt.asc())
                .limit(1)
            )
            .scalars()
            .all()
        )
        result.append(ConversationResponse.from_model(c, first))
    return {"conversations": result}


@router.post("", response_model=ConversationResponse, status_code=201)
def create_conversation(
    req: ConversationCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = Conversation(userId=user.id, title=(req.title or "").strip() or "新对话")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return ConversationResponse.from_model(conv)


@router.get("/{conv_id}", response_model=ConversationResponse)
def get_conversation(
    conv_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.userId != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    messages = (
        db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversationId == conv_id)
            .order_by(ConversationMessage.createdAt.asc())
        )
        .scalars()
        .all()
    )
    return ConversationResponse.from_model(conv, messages)


@router.patch("/{conv_id}/title")
def update_conversation_title(
    conv_id: str,
    req: ConversationCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新对话标题；对齐原 title/route.ts：
    - 带 title → 直接更新
    - 空 body → 按完整对话历史用 AI 生成标题；不足一轮对话返回 {skipped: true}
    """
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.userId != user.id:
        raise HTTPException(status_code=404, detail="Not found")

    if req.title:
        conv.title = req.title.strip()
        db.commit()
        return {"title": conv.title, "skipped": False}

    # 自动生成标题：需要至少一轮对话（2 条消息）
    messages = (
        db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversationId == conv_id)
            .order_by(ConversationMessage.createdAt.asc())
        )
        .scalars()
        .all()
    )
    if len(messages) < 2:
        return {"title": conv.title, "skipped": True}

    summary = "\n".join(
        f"{'用户' if m.role == 'user' else 'AI'}：{m.content}" for m in messages
    )[:2000]
    from app.routers.ai import generate_chat_title

    new_title = generate_chat_title(summary, user.id) or conv.title or "未命名对话"
    if new_title != conv.title:
        conv.title = new_title
        db.commit()
    return {"title": new_title, "skipped": False}


@router.delete("/{conv_id}")
def delete_conversation(
    conv_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.userId != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(conv)
    db.commit()
    return {"success": True}


@router.get("/{conv_id}/messages", response_model=list[MessageResponse])
def list_messages(
    conv_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.userId != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    messages = (
        db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversationId == conv_id)
            .order_by(ConversationMessage.createdAt.asc())
        )
        .scalars()
        .all()
    )
    return [
        MessageResponse(
            id=m.id,
            conversationId=m.conversationId,
            role=m.role,
            content=m.content,
            createdAt=m.createdAt.isoformat(),
        )
        for m in messages
    ]
