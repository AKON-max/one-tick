# ============================================================
# 专注路由（对应 src/app/api/focus/sessions/route.ts）
# 只记录自然完成的专注会话（暂停/跳过留在前端）
# ============================================================

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.base import User
from app.models.study import StudyRecord

router = APIRouter(prefix="/api/focus", tags=["focus"])

VALID_DURATIONS = {25, 45, 60}


class FocusSessionRequest(BaseModel):
    durationMinutes: int
    sessionId: str


@router.post("/sessions")
def record_focus_session(
    req: FocusSessionRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """记录一次完成的专注会话（幂等：sessionId 去重）"""
    if req.durationMinutes not in VALID_DURATIONS:
        raise HTTPException(status_code=400, detail="Invalid focus duration")
    if not req.sessionId.startswith("focus-") or len(req.sessionId) > 100:
        raise HTTPException(status_code=400, detail="Invalid focus duration")

    # 幂等去重：同一 sessionId 不重复记录
    existing = (
        db.execute(
            select(StudyRecord).where(
                StudyRecord.userId == user.id,
                StudyRecord.checkinId == req.sessionId,
            )
        )
        .scalars()
        .first()
    )
    if existing:
        return {
            "ok": True,
            "duplicate": True,
            "recordId": existing.id,
            "durationMinutes": req.durationMinutes,
        }

    record = StudyRecord(
        userId=user.id,
        date=datetime.now(timezone.utc),
        totalMinutes=req.durationMinutes,
        checkinId=req.sessionId,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {
        "ok": True,
        "recordId": record.id,
        "durationMinutes": req.durationMinutes,
        "sessionId": req.sessionId,
    }
