# ============================================================
# 用户每日 AI token 用量与限额
# 模型池（completions_with_fallback / stream_with_fallback）统一记账；
# 交互式面（agent / studio / 聊天室）超限抛 UsageLimitError，返回友好提示。
# ============================================================

from datetime import datetime, time, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.misc import TokenUsage

ENERGY_DOWN_MESSAGE = "没精力了，宕机了"


class UsageLimitError(Exception):
    """交互式面超限（每日精力用完）时抛出，路由据此返回友好文本"""

    def __init__(self, message: str = ENERGY_DOWN_MESSAGE):
        super().__init__(message)
        self.message = message


def usage_limit() -> int:
    """每日限额（env AI_TOKEN_LIMIT，0 = 不限），默认 20 万 token"""
    raw = settings.AI_TOKEN_LIMIT
    return raw if raw and raw > 0 else 0


def _day_start() -> datetime:
    return datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)


def get_today_usage(user_id: str, db: Optional[Session] = None) -> dict:
    """今日用量汇总"""
    limit = usage_limit()
    used = 0
    if db is not None:
        total = db.execute(
            select(func.coalesce(func.sum(TokenUsage.totalTokens), 0)).where(
                TokenUsage.userId == user_id,
                TokenUsage.createdAt >= _day_start(),
            )
        ).scalar()
        used = total or 0
    else:
        with SessionLocal() as own_db:
            total = own_db.execute(
                select(func.coalesce(func.sum(TokenUsage.totalTokens), 0)).where(
                    TokenUsage.userId == user_id,
                    TokenUsage.createdAt >= _day_start(),
                )
            ).scalar()
            used = total or 0

    remaining = max(limit - used, 0) if limit > 0 else 2**63 - 1
    return {
        "used": used,
        "limit": limit,
        "remaining": remaining,
        "unlimited": limit <= 0,
    }


def assert_interactive_usage_allowed(user_id: str, db: Optional[Session] = None) -> None:
    """交互式面超限检查；只剩 0 时抛 UsageLimitError"""
    data = get_today_usage(user_id, db)
    if data["remaining"] <= 0:
        raise UsageLimitError()


def record_usage(rec: dict, db: Optional[Session] = None) -> None:
    """记录一次 AI 调用用量；拿不到用量（totalTokens<=0）或写入失败都不阻断主流程"""
    if not rec.get("totalTokens") or rec["totalTokens"] <= 0:
        return
    try:
        row = TokenUsage(
            userId=rec["userId"],
            surface=rec["surface"],
            tier=rec["tier"],
            model=rec["model"],
            inputTokens=rec.get("inputTokens", 0),
            outputTokens=rec.get("outputTokens", 0),
            totalTokens=rec["totalTokens"],
        )
        if db is not None:
            db.add(row)
            db.commit()
        else:
            with SessionLocal() as own_db:
                own_db.add(row)
                own_db.commit()
    except Exception as e:  # noqa: BLE001
        print(f"[usage] 记录用量失败: {e}")
