# ============================================================
# 聊天记录 REST API（对应 src/app/api/chat/messages/route.ts）
# GET /api/chat/messages — 最近 100 条聊天记录（单房间全局流）
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.base import User
from app.models.chat import ChatMessage
from app.ws.protocol import iso_z

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/messages")
def list_chat_messages(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """最近 100 条聊天记录（倒序取后反转 → 正序返回），含 user 的 id/name/image"""
    messages = (
        db.execute(
            select(ChatMessage)
            .options(selectinload(ChatMessage.user))
            .order_by(ChatMessage.createdAt.desc())
            .limit(100)
        )
        .scalars()
        .all()
    )
    return {
        "messages": [
            {
                "id": m.id,
                "userId": m.userId,
                "role": m.role,
                "content": m.content,
                "aiRole": m.aiRole,
                "createdAt": iso_z(m.createdAt),
                "user": (
                    {"id": m.user.id, "name": m.user.name, "image": m.user.image}
                    if m.user is not None
                    else None
                ),
            }
            for m in reversed(messages)
        ]
    }
