# ============================================================
# 学习统计服务（对应 src/lib/study-stats.ts）
#
# 打卡仅为小岛到访计数：不含时长/科目/心情。
# 统计：打卡次数、今日打卡、连续天数、活跃计划进度。
# ============================================================

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.study import Checkin, Plan, PlanTask


def _day_start(d: datetime) -> datetime:
    return datetime.combine(d.date(), time.min, tzinfo=timezone.utc)


def get_study_stats(db: Session, user_id: str) -> dict:
    now = datetime.now(timezone.utc)
    today_start = _day_start(now)

    all_checkins = (
        db.execute(
            select(Checkin)
            .where(Checkin.userId == user_id)
            .order_by(Checkin.checkinDate.desc())
        )
        .scalars()
        .all()
    )
    active_plans = (
        db.execute(
            select(Plan).where(Plan.userId == user_id, Plan.status == "active")
        )
        .scalars()
        .all()
    )
    today_count = len([c for c in all_checkins if c.checkinDate >= today_start])

    # 连续打卡：从今天往回数（今天还没打卡不算断）
    streak = 0
    check_dates = {c.checkinDate.date() for c in all_checkins}
    for i in range(365):
        d = (now - timedelta(days=i)).date()
        if d in check_dates:
            streak += 1
        elif i > 0:
            break

    active_plans_data = []
    for plan in active_plans:
        tasks = (
            db.execute(select(PlanTask).where(PlanTask.planId == plan.id))
            .scalars()
            .all()
        )
        total = len(tasks)
        done = len([t for t in tasks if t.status == "done"])
        active_plans_data.append(
            {"name": plan.name, "progress": round(done / total * 100) if total > 0 else 0}
        )

    return {
        "totalCheckins": len(all_checkins),
        "todayCount": today_count,
        "streak": streak,
        "activePlans": active_plans_data,
    }


def build_checkin_summary(db: Session, user_id: str) -> dict:
    """签到页（小岛）聚合数据，对应 checkin/page.tsx 的 7 次 Prisma 查询"""
    now = datetime.now(timezone.utc)
    today_start = _day_start(now)

    all_checkins = (
        db.execute(
            select(Checkin)
            .where(Checkin.userId == user_id)
            .order_by(Checkin.checkinDate.desc())
        )
        .scalars()
        .all()
    )
    today_checkin = any(c.checkinDate >= today_start for c in all_checkins)

    # 连续签到：今天没签不算断（从今天/昨天往回数）
    check_dates = {c.checkinDate.date() for c in all_checkins}
    streak = 0
    start = now.date() if today_checkin else now.date() - timedelta(days=1)
    for i in range(365):
        d = start - timedelta(days=i)
        if d in check_dates:
            streak += 1
        elif i > 0:
            break

    total_checkins = len(all_checkins)
    total_hours = float(sum(c.hours or 0 for c in all_checkins))

    # 本周签到天数（周一为一周起点）
    day_of_week = now.weekday()  # 0=Mon
    week_start = now.date() - timedelta(days=day_of_week)
    week_checkins = len({c.checkinDate.date() for c in all_checkins if c.checkinDate.date() >= week_start})

    # 年度热力图 + 最长连续
    year_start = date(now.year, 1, 1)
    year_end = date(now.year, 12, 31)
    year_dates = {c.checkinDate.date() for c in all_checkins if year_start <= c.checkinDate.date() <= year_end}
    heatmap = []
    d = year_start
    while d <= year_end:
        key = d.isoformat()
        heatmap.append({"date": key, "checked": d in year_dates})
        d += timedelta(days=1)

    longest_streak = 0
    current_run = 0
    d = year_start
    while d <= year_end:
        if d in year_dates:
            current_run += 1
            if current_run > longest_streak:
                longest_streak = current_run
        else:
            current_run = 0
        d += timedelta(days=1)

    return {
        "todayCheckin": today_checkin,
        "streak": streak,
        "totalCheckins": total_checkins,
        "totalHours": total_hours,
        "weekCheckins": week_checkins,
        "heatmap": heatmap,
        "longestStreak": longest_streak,
    }
