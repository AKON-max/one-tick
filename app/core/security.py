# ============================================================
# 认证安全模块（对应 src/lib/auth.ts + src/lib/auth-utils.ts）
# - 密码哈希：scrypt，格式 salt:hash（与 Better Auth 兼容，原项目 reset-password 同算法）
# - JWT：签发 / 校验 / 获取当前用户依赖
# ============================================================

import hashlib
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.base import User

# ---- scrypt 参数（与 Better Auth 完全一致）----
SCRYPT_N = 16384
SCRYPT_R = 16
SCRYPT_P = 1
SCRYPT_DKLEN = 64
# scrypt 内存需求 = 128 * N * r；默认 32MB 不够，需显式放开（Better Auth 同样处理）
SCRYPT_MAXMEM = 128 * SCRYPT_N * SCRYPT_R * 2


def hash_password(password: str) -> str:
    """生成 Better Auth 兼容的 scrypt 哈希：salt:hash（hex）"""
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(
        unicodedata.normalize("NFKC", password).encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )
    return f"{salt.hex()}:{key.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码（兼容 salt:hash 格式）"""
    try:
        salt_hex, hash_hex = stored.split(":")
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, AttributeError):
        return False
    key = hashlib.scrypt(
        unicodedata.normalize("NFKC", password).encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_DKLEN,
        maxmem=SCRYPT_MAXMEM,
    )
    return secrets.compare_digest(key, expected)


# ---- JWT ----

def create_access_token(user_id: str, user_name: str, email: str) -> str:
    """签发 JWT（7 天有效期）"""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": user_id,
        "name": user_name,
        "email": email,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """解析 JWT，非法/过期返回 None"""
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


# ---- FastAPI 依赖：获取当前用户 ----

# 兼容两种认证来源（同域反代场景）：
# 1. Authorization: Bearer <token>（标准，第三方客户端）
# 2. Cookie: session_token=<token>（Next.js 前端同域部署，浏览器自动携带，
#    前端 52 处 fetch("/api/...") 无需逐个加 header）
_bearer = HTTPBearer(auto_error=False)

# 前端登录后写入的 cookie 名（与 src/proxy.ts 检查的一致）
SESSION_COOKIE = "session_token"


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    request: Request = None,  # noqa: FA100 - FastAPI 按类型自动注入
    db: Session = Depends(get_db),
) -> User:
    """Bearer Token 或 Cookie(session_token) → 当前用户"""
    token = credentials.credentials if credentials is not None else None
    if token is None and request is not None:
        token = request.cookies.get(SESSION_COOKIE)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未登录",
        )
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录已过期，请重新登录",
        )
    user = db.get(User, payload.get("sub"))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    return user
