# ============================================================
# 通知路由
# GET    /api/notifications           列表 + 未读数（分页）
# POST   /api/notifications           全部标记已读 {action:"markAllRead"}
# PATCH  /api/notifications/{id}      标记单条已读 {read:true}
# DELETE /api/notifications/{id}      删除单条
# ============================================================

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.base import User
from app.models.misc import Notification
from app.services.notification import (
    delete_notification,
    get_unread_count,
    list_notifications,
    mark_all_as_read,
    mark_as_read,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def _dto(n: Notification) -> dict:
    return {
        "id": n.id,
        "userId": n.userId,
        "type": n.type,
        "title": n.title,
        "content": n.content,
        "read": n.read,
        "actionUrl": n.actionUrl,
        "createdAt": n.createdAt.isoformat(),
    }


@router.get("")
def get_notifications(
    unreadOnly: str = "false",
    type: str | None = None,
    limit: int = 20,
    offset: int = 0,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    limit = min(limit if limit > 0 else 20, 100)
    offset = max(offset, 0)

    rows, total = list_notifications(
        db, user.id, type=type or None, unreadOnly=(unreadOnly == "true"), limit=limit, offset=offset
    )
    unread_count = get_unread_count(db, user.id)

    return {
        "notifications": [_dto(n) for n in rows],
        "total": total,
        "unreadCount": unread_count,
        "hasMore": offset + limit < total,
    }


class MarkAllReadRequest(BaseModel):
    action: str | None = None


@router.post("")
def post_notifications(
    req: MarkAllReadRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    action = req.action if req else None
    if action != "markAllRead":
        raise HTTPException(status_code=400, detail="Invalid action. Supported: markAllRead")

    marked = mark_all_as_read(db, user.id)
    return {"success": True, "markedRead": marked}


class MarkOneReadRequest(BaseModel):
    read: bool


@router.patch("/{notification_id}")
def patch_notification(
    notification_id: str,
    req: MarkOneReadRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not req or req.read is not True:
        raise HTTPException(status_code=400, detail="Invalid action. Send { read: true }")

    if not mark_as_read(db, notification_id, user.id):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}


@router.delete("/{notification_id}")
def delete_one_notification(
    notification_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not delete_notification(db, notification_id, user.id):
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"success": True}
