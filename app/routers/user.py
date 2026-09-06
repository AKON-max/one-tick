# ============================================================
# 用户头像路由（对应 src/app/api/user/avatar/route.ts）
# PATCH /api/user/avatar  { avatar: "1"~"16"|"ai" 或 OSS 公开 URL }
#  - 预设头像：直接写库，不限流
#  - OSS 头像：3/min 内存限流 + 5/day 数据库限流 + HEAD 校验存在性与 ≤5MB
# ============================================================

import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.base import User
from app.models.misc import AvatarChange
from app.services.oss import (
    delete_object,
    get_object_meta,
    is_oss_configured,
    is_owned_avatar_url,
)
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/user", tags=["user"])

# 预设头像 id 白名单（对应 avatar-presets.ts 的 VALID_AVATAR_IDS："1"~"16" / "ai"）
VALID_AVATAR_IDS = {str(i) for i in range(1, 17)} | {"ai"}

# OSS 头像大小上限（5MB），超出拒绝并清理该对象
MAX_AVATAR_SIZE = 5 * 1024 * 1024

# 上传头像限流（只限 OSS 上传；预设不限流）
MINUTE_LIMIT = 3  # 3 次/分钟（内存窗口，重启清零）
DAY_LIMIT = 5  # 5 次/天（数据库持久）
WINDOW_MS = 60_000
_minute_usage: dict[str, dict] = {}


def _check_minute_budget(user_id: str) -> bool:
    now = int(time.time() * 1000)
    u = _minute_usage.get(user_id)
    if not u or now - u["window_start"] > WINDOW_MS:
        _minute_usage[user_id] = {"window_start": now, "count": 1}
        return True
    if u["count"] >= MINUTE_LIMIT:
        return False
    u["count"] += 1
    return True


class AvatarRequest(BaseModel):
    avatar: str


class ProfileUpdateRequest(BaseModel):
    name: str | None = None
    bio: str | None = None


@router.patch("/profile")
def update_profile(
    req: ProfileUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新个人资料（对应 settings/actions.ts 的 updateProfile）"""
    if req.name is not None and req.name.strip():
        user.name = req.name.strip()
    if req.bio is not None:
        user.bio = req.bio
    db.commit()
    return {"ok": True}


@router.patch("/avatar")
def update_avatar(
    req: AvatarRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    avatar = req.avatar

    # ── 预设头像：直接写库，不限流 ──
    if avatar in VALID_AVATAR_IDS:
        user.image = avatar
        db.commit()
        return {"ok": True}

    # ── OSS 上传头像：URL 必须落在本 bucket 的 avatars/{当前userId}/ 前缀下 ──
    if is_oss_configured() and is_owned_avatar_url(avatar, user.id):
        # 1. 3/min 内存限流
        if not _check_minute_budget(user.id):
            raise HTTPException(status_code=429, detail="Too many requests")

        # 2. 5/day 数据库限流
        local_now = datetime.now().astimezone()
        start_of_day = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = (
            db.execute(
                select(func.count(AvatarChange.id)).where(
                    AvatarChange.userId == user.id, AvatarChange.createdAt >= start_of_day
                )
            ).scalar()
            or 0
        )
        if today_count >= DAY_LIMIT:
            raise HTTPException(status_code=429, detail="Daily avatar limit reached")

        # 3. 对象需已存在（浏览器先直传 OSS 再 PATCH），并校验大小
        meta = get_object_meta(avatar)
        if not meta:
            raise HTTPException(status_code=400, detail="Object not found")
        if meta["size"] > MAX_AVATAR_SIZE:
            delete_object(avatar)
            raise HTTPException(status_code=400, detail="Image too large")

        # 4. 写入 + 计数 + 清理旧对象（best-effort，不影响主流程）
        old_image = user.image
        user.image = avatar
        db.add(AvatarChange(userId=user.id))
        # 顺手清 30 天前的计数行，防表膨胀（量极小）
        cutoff = datetime.now().astimezone() - timedelta(days=30)
        db.execute(delete(AvatarChange).where(AvatarChange.createdAt < cutoff))
        db.commit()
        if old_image and old_image != avatar and is_owned_avatar_url(old_image, user.id):
            delete_object(old_image)
        return {"ok": True}

    raise HTTPException(status_code=400, detail="Invalid avatar")
