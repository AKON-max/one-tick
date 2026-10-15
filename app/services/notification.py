# ============================================================
# 通知服务
# 职责：通知的创建（每日按类型去重）/ 列表 / 已读 / 删除 / 清理
# 通知由 Agent（cron 巡检）生成，本模块只提供数据能力
# ============================================================

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.base import User
from app.models.misc import Notification

# 合法通知类型
NOTIFICATION_TYPES = ("reminder", "analysis", "report", "encouragement", "system")


def create_notification(
    db: Session,
    userId: str,
    type: str,
    title: str,
    content: str,
    actionUrl: str | None = None,
) -> Notification | None:
    """创建通知，每日节流去重：同用户当天同类型只保留一条

    去重键 = 用户 + 类型 + 本地时区当天（本地时区当天）。
    命中已存在 → 跳过并返回 None；任何异常也返回 None（不打扰主流程）。
    """
    try:
        # 本地时区当天零点（转成 UTC 时刻，便于与库里的 UTC createdAt 比较）
        local_now = datetime.now().astimezone()
        start_of_day_utc = local_now.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)

        exists = (
            db.execute(
                select(Notification.id)
                .where(Notification.userId == userId, Notification.type == type, Notification.createdAt >= start_of_day_utc)
                .limit(1)
            )
            .first()
        )
        if exists is not None:
            print(f"[Notification] 今日同类型通知已存在，跳过: type={type} user={userId}")
            return None

        n = Notification(userId=userId, type=type, title=title, content=content, actionUrl=actionUrl)
        db.add(n)
        db.commit()
        db.refresh(n)
        return n
    except Exception as err:  # noqa: BLE001
        print(f"[Notification] 创建通知失败: {err}")
        db.rollback()
        return None


def list_notifications(
    db: Session,
    userId: str,
    type: str | None = None,
    unreadOnly: bool = False,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Notification], int]:
    """通知列表（createdAt desc）+ 符合过滤条件的总数"""
    conditions = [Notification.userId == userId]
    if type:
        conditions.append(Notification.type == type)
    if unreadOnly:
        conditions.append(Notification.read.is_(False))

    rows = (
        db.execute(
            select(Notification)
            .where(*conditions)
            .order_by(Notification.createdAt.desc())
            .offset(offset)
            .limit(limit)
        )
        .scalars()
        .all()
    )
    total = db.execute(select(func.count(Notification.id)).where(*conditions)).scalar() or 0
    return list(rows), total


def get_unread_count(db: Session, userId: str) -> int:
    """未读通知总数（独立于列表过滤条件）"""
    return (
        db.execute(select(func.count(Notification.id)).where(Notification.userId == userId, Notification.read.is_(False))).scalar()
        or 0
    )


def mark_as_read(db: Session, notificationId: str, userId: str) -> bool:
    """标记单条已读（带所有权校验：updateMany where {id, userId}）"""
    try:
        result = db.execute(
            update(Notification).where(Notification.id == notificationId, Notification.userId == userId).values(read=True)
        )
        db.commit()
        return result.rowcount > 0
    except Exception as err:  # noqa: BLE001
        print(f"[Notification] 标记已读失败: {err}")
        db.rollback()
        return False


def mark_all_as_read(db: Session, userId: str) -> int:
    """全部标记已读，返回被标记条数"""
    result = db.execute(
        update(Notification).where(Notification.userId == userId, Notification.read.is_(False)).values(read=True)
    )
    db.commit()
    return result.rowcount


def delete_notification(db: Session, notificationId: str, userId: str) -> bool:
    """删除单条通知

    注意：早期实现只按 id 删除（存在越权风险），
    这里改用 deleteMany 带 userId 做所有权校验（安全且对本人行为一致）。
    """
    try:
        result = db.execute(
            delete(Notification).where(Notification.id == notificationId, Notification.userId == userId)
        )
        db.commit()
        return result.rowcount > 0
    except Exception as err:  # noqa: BLE001
        print(f"[Notification] 删除通知失败: {err}")
        db.rollback()
        return False


def cleanup_old_notifications(db: Session, userId: str, olderThanDays: int = 30) -> int:
    """清理 N 天前已读通知（未读不清理），由 Agent cron 调用"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=olderThanDays)
    result = db.execute(
        delete(Notification).where(
            Notification.userId == userId,
            Notification.read.is_(True),
            Notification.createdAt < cutoff,
        )
    )
    db.commit()
    if result.rowcount > 0:
        print(f"[Notification] 清理 {result.rowcount} 条旧通知 (user={userId})")
    return result.rowcount
