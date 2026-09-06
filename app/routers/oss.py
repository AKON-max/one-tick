# ============================================================
# OSS 预签名路由（对应 src/app/api/oss/presign/route.ts）
# GET /api/oss/presign?ext=png&purpose=avatars
# 浏览器直传 OSS，文件不经过服务器
# ============================================================

import time

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user
from app.models.base import User
from app.services.oss import OSS_ALLOWED_EXTS, OSS_PURPOSES, is_oss_configured, sign_upload_url

router = APIRouter(prefix="/api/oss", tags=["oss"])

# 预签名限流：同用户每分钟最多签 10 次（内存窗口，重启清零）
PRESIGN_BUDGET = 10
WINDOW_MS = 60_000
_presign_usage: dict[str, dict] = {}


def _check_presign_budget(user_id: str) -> bool:
    now = int(time.time() * 1000)
    u = _presign_usage.get(user_id)
    if not u or now - u["window_start"] > WINDOW_MS:
        _presign_usage[user_id] = {"window_start": now, "count": 1}
        return True
    if u["count"] >= PRESIGN_BUDGET:
        return False
    u["count"] += 1
    return True


@router.get("/presign")
def presign(
    ext: str,
    purpose: str = "avatars",
    user: User = Depends(get_current_user),
):
    # 用途白名单
    if purpose not in OSS_PURPOSES:
        raise HTTPException(status_code=400, detail="Invalid purpose")

    # 扩展名白名单（忽略大小写与前导点）
    ext = ext.lower().lstrip(".")
    if ext not in OSS_ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    # 限流
    if not _check_presign_budget(user.id):
        raise HTTPException(status_code=429, detail="Too many requests")

    # OSS 未配置 → 503
    if not is_oss_configured():
        raise HTTPException(status_code=503, detail="OSS not configured")

    try:
        upload_url, key, public_url = sign_upload_url(user.id, purpose, ext)
    except Exception as err:  # noqa: BLE001
        print(f"[OSS] 签发失败: {err}")
        raise HTTPException(status_code=500, detail="Failed to sign upload URL") from err

    return {"uploadUrl": upload_url, "key": key, "publicUrl": public_url}
