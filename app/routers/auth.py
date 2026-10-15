# ============================================================
# 认证路由
# 注册 / 登录 / 当前用户 / 登出
# 注册时克隆引导模板
# ============================================================

import secrets
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_current_user, hash_password, verify_password
from app.db.session import get_db
from app.models.base import User
from app.models.chat import ChatMessage
from app.services.onboard import GUEST_DEMO_DAYS, clone_guide_templates, seed_guest_demo

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 游客账号：邮箱统一落在保留域名下，便于识别与回收
GUEST_EMAIL_DOMAIN = "@guest.local"
# 游客账号保留期（天）：超过这么久没活动的游客账号会被回收
GUEST_RETENTION_DAYS = 7


# ---- DTO ----

class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=100)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    image: str | None = None
    theme: str = "system"

    @classmethod
    def from_user(cls, u: User) -> "UserResponse":
        return cls(id=u.id, name=u.name, email=u.email, image=u.image, theme=u.theme)


class AuthResponse(BaseModel):
    token: str
    user: UserResponse


# ---- 路由 ----

def _set_session_cookie(response: JSONResponse, token: str) -> None:
    """把 JWT 写入 session_token cookie：同域反代下前端浏览器自动携带，无需逐处加 header"""
    response.set_cookie(
        key="session_token",
        value=token,
        max_age=7 * 24 * 3600,  # 7 天（与 JWT 有效期一致）
        httponly=False,  # 非 httpOnly：前端 proxy.ts 能读它做路由守卫
        samesite="lax",
        path="/",
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(req: RegisterRequest, response: JSONResponse, db: Session = Depends(get_db)):
    """注册并初始化用户引导模板"""
    exists = db.execute(select(User).where(User.email == req.email)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=409, detail="该邮箱已注册")

    user = User(
        name=req.name,
        email=req.email,
        emailVerified=False,
        password=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 注册钩子：克隆引导模板（失败不阻断注册）
    try:
        clone_guide_templates(db, user.id)
    except Exception as e:  # noqa: BLE001
        print(f"[onboard] 注册钩子异常: {e}")

    token = create_access_token(user.id, user.name, user.email)
    _set_session_cookie(response, token)
    return AuthResponse(token=token, user=UserResponse.from_user(user))


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)):
    """当前登录用户"""
    return UserResponse.from_user(user)


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, response: JSONResponse, db: Session = Depends(get_db)):
    """邮箱密码登录"""
    user = db.execute(select(User).where(User.email == req.email)).scalar_one_or_none()
    if user is None or not user.password or not verify_password(req.password, user.password):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    token = create_access_token(user.id, user.name, user.email)
    _set_session_cookie(response, token)
    return AuthResponse(token=token, user=UserResponse.from_user(user))


def _recycle_expired_guests(db: Session) -> None:
    """回收过期游客账号（连带其聊天记录）。

    游客每点一次「游客体验」就新建一个账号，不回收会一直堆积。
    这里用懒回收：游客登录时顺手清掉旧账号，不必额外引入定时任务。
    过期判断用 updatedAt（最后活动时间）而不是 createdAt ——
    游客的 createdAt 被回填成演示起始日，用它判断会让新游客当场被判过期。
    """
    threshold = datetime.now(timezone.utc) - timedelta(days=GUEST_RETENTION_DAYS)
    ids = (
        db.execute(
            select(User.id).where(
                User.email.like(f"%{GUEST_EMAIL_DOMAIN}"),
                User.updatedAt < threshold,
            )
        )
        .scalars()
        .all()
    )
    if not ids:
        return
    try:
        # 聊天室消息是 SET NULL 关系，不主动删会永远留在公共聊天流里
        db.execute(delete(ChatMessage).where(ChatMessage.userId.in_(ids)))
        # 其余数据（打卡/计划/待办/盆栽/会话…）由外键 ON DELETE CASCADE 连带清掉
        db.execute(delete(User).where(User.id.in_(ids)))
        db.commit()
        print(f"[auth] 已回收 {len(ids)} 个过期游客账号")
    except Exception as e:  # noqa: BLE001
        print(f"[auth] 回收过期游客失败: {e}")
        db.rollback()


@router.post("/guest", response_model=AuthResponse)
def guest_login(response: JSONResponse, db: Session = Depends(get_db)):
    """游客体验（免注册登录）。

    每个访客一个独立临时账号，数据互不干扰，可自由打卡/专注/写文档；
    账号在 GUEST_RETENTION_DAYS 天无活动后连同数据一起回收。
    """
    _recycle_expired_guests(db)

    user = User(
        name=f"游客{secrets.randbelow(9000) + 1000}",
        email=f"guest_{uuid4().hex[:12]}{GUEST_EMAIL_DOMAIN}",
        emailVerified=False,
        password=None,
        # 回填加入时间，与演示打卡历史对齐（资料页才不会出现「加入 1 天 / 已打卡 10 天」）
        createdAt=datetime.now(timezone.utc) - timedelta(days=GUEST_DEMO_DAYS - 1),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # 初始化内容（引导模板 + 演示数据）：失败不阻断登录
    try:
        clone_guide_templates(db, user.id)
        seed_guest_demo(db, user.id)
    except Exception as e:  # noqa: BLE001
        print(f"[auth] 游客初始化失败: {e}")

    token = create_access_token(user.id, user.name, user.email)
    _set_session_cookie(response, token)
    return AuthResponse(token=token, user=UserResponse.from_user(user))


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str


@router.post("/change-password")
def change_password(
    req: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改密码"""
    if not user.password or not verify_password(req.currentPassword, user.password):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if len(req.newPassword) < 8:
        raise HTTPException(status_code=400, detail="新密码至少 8 位")

    user.password = hash_password(req.newPassword)
    db.commit()
    return {"success": True}
