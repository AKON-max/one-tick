# 测试认证链路（临时脚本）
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import SessionLocal
from app.models.base import User
from app.core.security import hash_password, verify_password, create_access_token, decode_token

print("=== 测试密码哈希 ===")
h = hash_password("password123")
print("hash:", h[:30], "...")
print("verify ok:", verify_password("password123", h))
print("verify wrong:", verify_password("wrong", h))

print("\n=== 测试 JWT ===")
token = create_access_token("user-1", "测试", "t@t.com")
print("token:", token[:30], "...")
payload = decode_token(token)
print("decode sub:", payload.get("sub"))

print("\n=== 测试注册写库 ===")
from sqlalchemy import select
from app.services.onboard import clone_guide_templates

with SessionLocal() as db:
    exists = db.execute(select(User).where(User.email == "test@example.com")).scalar_one_or_none()
    if exists:
        print("用户已存在（上次注册成功）, id:", exists.id)
        print("密码哈希:", exists.password[:30], "...")
    else:
        user = User(name="测试用户", email="test@example.com", password=hash_password("password123"))
        db.add(user)
        db.commit()
        db.refresh(user)
        print("新用户创建:", user.id)
        # 测试引导模板克隆
        clone_guide_templates(db, user.id)
        from app.models.study import Plan
        from app.models.knowledge import Document
        plans = db.query(Plan).filter(Plan.userId == user.id).all()
        docs = db.query(Document).filter(Document.userId == user.id).all()
        print(f"克隆计划: {len(plans)} 个, 克隆文档: {len(docs)} 个")
        if plans:
            from app.models.study import PlanTask
            tasks = db.query(PlanTask).filter(PlanTask.planId == plans[0].id).all()
            print(f"计划任务: {len(tasks)} 个")
