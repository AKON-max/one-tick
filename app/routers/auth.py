# ============================================================
# 认证路由（对应原项目 src/app/api/auth/[...all]/route.ts + Better Auth）
# 注册 / 登录 / 当前用户 / 登出
# 注册时克隆引导模板（对应原项目 auth.ts 的 databaseHooks.user.create.after）
# ============================================================

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_current_user, hash_password, verify_password
from app.db.session import get_db
from app.models.base import User
from app.services.onboard import clone_guide_templates

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
    """注册（对应原项目 Better Auth 注册 + 引导模板克隆钩子）"""
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
    """当前登录用户（对应原项目 getCurrentUser/getAuthUser）"""
    return UserResponse.from_user(user)


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, response: JSONResponse, db: Session = Depends(get_db)):
    """登录（对应原项目 Better Auth 邮箱密码登录）"""
    user = db.execute(select(User).where(User.email == req.email)).scalar_one_or_none()
    if user is None or not user.password or not verify_password(req.password, user.password):
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

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
    """修改密码（对应 settings/actions.ts 的 changePassword；改后由前端清理 cookie 完成登出）"""
    if not user.password or not verify_password(req.currentPassword, user.password):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if len(req.newPassword) < 8:
        raise HTTPException(status_code=400, detail="新密码至少 8 位")

    user.password = hash_password(req.newPassword)
    db.commit()
    return {"success": True}
