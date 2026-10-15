# ============================================================
# 用量路由
# GET /api/usage — 今日 AI token 用量（雨宝精力条每 30s 轮询）
# ============================================================

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.base import User
from app.services.usage import get_today_usage

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("")
def get_usage(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """今日用量汇总：返回裸对象 {used, limit, remaining, unlimited}"""
    return get_today_usage(user.id, db)
