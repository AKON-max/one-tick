# ============================================================
# 应用配置（环境变量集中管理）
# 对应原项目 src/lib/env.ts + server/config.ts + model-pool 的 env 读取
# ============================================================

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ---- 基础 ----
    APP_NAME: str = "python-checkin"
    DEBUG: bool = False
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # ---- 数据库 ----
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/python_checkin"

    # ---- 认证（替代 Better Auth）----
    JWT_SECRET: str = "change-me-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 天
    # 定时任务（cron）专用密钥：调用 /api/agent/cron/daily 需带
    # Authorization: Bearer <CRON_SECRET>；留空则不校验（本地调试用）
    CRON_SECRET: str = ""

    # ---- AI 模型池（对应 src/lib/model-pool.ts 的 PROVIDER_CONFIG）----
    AGNES_BASE_URL: str = "https://apihub.agnes-ai.com/v1"
    AGNES_API_KEY: str = ""
    ALIYUN_API_KEY: str = ""
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    EMBEDDING_MODEL: str = "text-embedding-v2"

    # ---- 用量限额（对应 src/lib/usage.ts，0 = 不限）----
    AI_TOKEN_LIMIT: int = 200_000

    # ---- OSS（对应 src/lib/oss.ts）----
    OSS_ACCESS_KEY_ID: str = ""
    OSS_ACCESS_KEY_SECRET: str = ""
    OSS_BUCKET: str = ""
    OSS_REGION: str = ""
    OSS_PUBLIC_BASE_URL: str = ""

    # ---- 聊天室 WS（对应 server/config.ts）----
    HEARTBEAT_INTERVAL_MS: int = 30_000
    MAX_MESSAGE_LENGTH: int = 2000
    RATE_LIMIT_WINDOW_MS: int = 60_000
    RATE_LIMIT_MAX: int = 30
    AI_CONTEXT_MESSAGES: int = 20

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
