# ============================================================
# OSS 服务
# 职责：浏览器直传 OSS 的预签名 PUT 地址签发 + 头像对象校验/删除
# 流程：前端请求 /api/oss/presign 拿 uploadUrl → 浏览器直接 PUT
#       文件到阿里云 OSS（须带同款 Content-Type，否则签名校验 403）
#       → PATCH /api/user/avatar 提交 publicUrl 落地
# ============================================================

import secrets
import time

import oss2

from app.core.config import settings

# 上传用途白名单（新增用途在此加一行即可复用整套流程）
OSS_PURPOSES = ["avatars", "wallpapers"]

# 允许的文件扩展名
OSS_ALLOWED_EXTS = ["png", "jpg", "jpeg", "webp", "gif"]

# 扩展名 → Content-Type（Content-Type 会被纳入签名，直传时必须一致）
EXT_TO_MIME = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}

# 预签名 URL 有效期（秒）
SIGN_EXPIRES = 300


def is_oss_configured() -> bool:
    """OSS 是否已配置（三件套环境变量齐全）"""
    return bool(settings.OSS_ACCESS_KEY_ID and settings.OSS_ACCESS_KEY_SECRET and settings.OSS_BUCKET)


def _bucket() -> oss2.Bucket:
    """构造 oss2 客户端（未配置时抛错，调用方需先判 is_oss_configured）"""
    auth = oss2.Auth(settings.OSS_ACCESS_KEY_ID, settings.OSS_ACCESS_KEY_SECRET)
    endpoint = f"https://{settings.OSS_REGION}.aliyuncs.com" if settings.OSS_REGION else "https://oss-cn-guangzhou.aliyuncs.com"
    return oss2.Bucket(auth, endpoint, settings.OSS_BUCKET)


def sign_upload_url(user_id: str, purpose: str = "avatars", ext: str = "png") -> tuple[str, str, str]:
    """签发预签名 PUT 地址

    :return: (uploadUrl, key, publicUrl)
    """
    ext = ext.lower().lstrip(".")
    mime = EXT_TO_MIME.get(ext)
    # 对象键：{purpose}/{userId}/{时间戳}-{8字节hex}.{ext}，保证唯一且可追溯
    key = f"{purpose}/{user_id}/{int(time.time() * 1000)}-{secrets.token_hex(8)}.{ext}"

    bucket = _bucket()
    headers = {"Content-Type": mime} if mime else {}
    upload_url = bucket.sign_url("PUT", key, SIGN_EXPIRES, headers=headers)

    public_url = f"{settings.OSS_PUBLIC_BASE_URL}/{key}"
    return upload_url, key, public_url


def _key_from_public_url(url: str) -> str:
    """从公开 URL 反解对象键（内部私有）"""
    base = settings.OSS_PUBLIC_BASE_URL
    return url[len(base) :].lstrip("/") if url.startswith(base) else url


def is_owned_avatar_url(url: str, user_id: str) -> bool:
    """校验头像 URL 必须落在本 bucket 的 avatars/{当前userId}/ 前缀下（防任意 URL 注入）"""
    prefix = f"{settings.OSS_PUBLIC_BASE_URL}/avatars/{user_id}/"
    return url.startswith(prefix)


def get_object_meta(url: str) -> dict | None:
    """HEAD 校验对象存在性，返回 {size}；不存在/异常返回 None"""
    try:
        result = _bucket().get_object_meta(_key_from_public_url(url))
        size = result.headers.get("content-length")
        if size is None:
            size = getattr(result, "content_length", None)
        return {"size": int(size)} if size is not None else {"size": 0}
    except Exception as err:  # noqa: BLE001
        print(f"[OSS] get_object_meta 失败: {err}")
        return None


def delete_object(url: str) -> bool:
    """DELETE 删除对象，best-effort 返回布尔值"""
    try:
        _bucket().delete_object(_key_from_public_url(url))
        return True
    except Exception as err:  # noqa: BLE001
        print(f"[OSS] delete_object 失败: {err}")
        return False
