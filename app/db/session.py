# ============================================================
# 数据库会话管理（对应 src/lib/prisma.ts）
# SQLAlchemy 2.0 + pgvector，同步 + 异步双 session
# ============================================================

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类"""


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,  # 连接前 ping，避免陈旧连接
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    """FastAPI 依赖注入：每请求一个 session，用完即关"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
