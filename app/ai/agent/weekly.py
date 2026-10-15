# ============================================================
# 周度学习周报：显式生成
#
# 周日由 cron daily 调用；用 observe + fallbackAnalysis（纯统计，不耗 LLM）
# 汇总「本周一 ~ 今天」的真实数据，落库为 report 通知。
# 注意：周报按「周」去重、直接落库，不走通用 createNotification 的「每日去重」，
# 否则会被当天已有的任何 report（如每日小结）挤掉。
# ============================================================

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.ai.agent.report import format_report_as_markdown, generate_weekly_report
from app.ai.agent.runtime import fallback_analysis, observe
from app.db.session import SessionLocal
from app.models.misc import Notification


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def create_weekly_report_notification(user_id: str, db=None) -> dict | None:
    """为用户生成并落库一条「本周学习周报」通知。

    本周已生成过则返回 None（周度去重跳过）。
    """
    now_local = datetime.now()
    # 回退到本周一（本地时区），对应 TS weekStart.setDate(now.getDate() - ((now.getDay() + 6) % 7))
    week_start_local = (now_local - timedelta(days=now_local.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    # 时间统一按 UTC 比较；这里把本地周起点转换为 UTC
    week_start_utc = week_start_local.astimezone(timezone.utc)

    own = db is None
    if own:
        db = SessionLocal()
    try:
        # 周度去重：本周已生成过周报则跳过
        existing = db.execute(
            select(Notification.id)
            .where(
                Notification.userId == user_id,
                Notification.type == "report",
                Notification.title == "本周学习周报",
                Notification.createdAt >= week_start_utc,
            )
        ).scalars().first()
        if existing:
            print(f"[Weekly] 本周周报已存在，跳过: user={user_id[:8]}")
            return None

        context = observe(user_id)
        analysis = fallback_analysis(context)

        report = generate_weekly_report(
            user_id,
            context,
            analysis,
            week_start=week_start_utc.strftime("%Y-%m-%d"),
            week_end=_now_utc().strftime("%Y-%m-%d"),
        )

        markdown = format_report_as_markdown(report)

        notification = Notification(
            userId=user_id,
            type="report",
            title="本周学习周报",
            content=markdown,
            actionUrl="/agent",
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)
        print(f"[Weekly] 已生成本周学习周报: user={user_id[:8]}")
        return {
            "id": notification.id,
            "userId": notification.userId,
            "type": notification.type,
            "title": notification.title,
            "content": notification.content,
            "read": notification.read,
            "actionUrl": notification.actionUrl,
            "createdAt": notification.createdAt.isoformat(),
        }
    finally:
        if own:
            db.close()
