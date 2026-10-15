# ============================================================
# 统计路由
# 专注趋势 / 学科分布 / 打卡日历 / 学习统计
# ============================================================

from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.base import User
from app.models.study import Checkin, Plan, PlanTask, StudyRecord
from app.services.study_stats import get_study_stats

router = APIRouter(prefix="/api/statistics", tags=["statistics"])


@router.get("/overview")
def overview(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """学习统计总览（打卡/连续天数/活跃计划）"""
    return get_study_stats(db, user.id)


@router.get("/focus")
def focus(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """近 7 天专注趋势（StudyRecord 按天汇总）"""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=6)
    since_start = datetime.combine(since.date(), time.min, tzinfo=timezone.utc)

    rows = (
        db.execute(
            select(StudyRecord).where(
                StudyRecord.userId == user.id,
                StudyRecord.date >= since_start,
            )
        )
        .scalars()
        .all()
    )

    # 按天聚合
    by_day: dict[str, dict] = {}
    for r in rows:
        key = r.date.date().isoformat()
        if key not in by_day:
            by_day[key] = {"date": key, "minutes": 0, "sessions": 0}
        by_day[key]["minutes"] += r.totalMinutes
        by_day[key]["sessions"] += 1

    # 补齐 7 天（无记录为 0）
    result = []
    for i in range(7):
        d = (now - timedelta(days=6 - i)).date().isoformat()
        result.append(by_day.get(d, {"date": d, "minutes": 0, "sessions": 0}))
    return {"days": result}


@router.get("/subjects")
def subjects(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """学科分布（打卡 subject 统计）"""
    rows = (
        db.execute(select(Checkin).where(Checkin.userId == user.id))
        .scalars()
        .all()
    )
    counts: dict[str, int] = {}
    for c in rows:
        s = c.subject or "未分类"
        counts[s] = counts.get(s, 0) + 1
    return {"subjects": [{"subject": k, "count": v} for k, v in counts.items()]}


@router.get("/calendar")
def calendar(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """打卡日历（热力图数据：日期 + 是否打卡）"""
    rows = (
        db.execute(select(Checkin).where(Checkin.userId == user.id))
        .scalars()
        .all()
    )
    return {
        "checkins": [
            {"date": c.checkinDate.date().isoformat(), "content": c.content}
            for c in rows
        ]
    }


@router.get("/tasks")
def tasks(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """任务完成统计"""
    rows = (
        db.execute(select(PlanTask).where(PlanTask.userId == user.id))
        .scalars()
        .all()
    )
    total = len(rows)
    done = len([t for t in rows if t.status == "done"])
    return {"total": total, "done": done, "progress": round(done / total * 100) if total else 0}


@router.get("/profile-overview")
def profile_overview(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """个人资料页（/statistics）聚合数据：用户资料 + 计划任务进度 + 番茄钟 + 打卡日期"""
    now = datetime.now(timezone.utc)
    since_start = datetime.combine((now - timedelta(days=6)).date(), time.min, tzinfo=timezone.utc)

    # 计划 + 任务（状态/完成时间）
    plans = (
        db.execute(select(Plan).where(Plan.userId == user.id))
        .scalars()
        .all()
    )
    plan_data = []
    for p in plans:
        tasks = (
            db.execute(select(PlanTask).where(PlanTask.planId == p.id))
            .scalars()
            .all()
        )
        plan_data.append(
            {
                "id": p.id,
                "name": p.name,
                "status": p.status,
                "tasks": [
                    {
                        "status": t.status,
                        "completedAt": t.completedAt.isoformat() if t.completedAt else None,
                    }
                    for t in tasks
                ],
            }
        )

    # 番茄钟记录（原前端只统计 checkinId 以 "focus-" 开头的记录）：全部累计 + 近 7 天
    records = (
        db.execute(
            select(StudyRecord).where(
                StudyRecord.userId == user.id,
                StudyRecord.checkinId.like("focus-%"),
            )
        )
        .scalars()
        .all()
    )
    focus_total_minutes = float(sum(r.totalMinutes for r in records))
    focus_session_count = len(records)
    focus_records = [
        {"date": r.date.date().isoformat(), "totalMinutes": float(r.totalMinutes)}
        for r in records
        if r.date >= since_start
    ]

    # 打卡日期（活跃日）
    checkins = (
        db.execute(select(Checkin).where(Checkin.userId == user.id))
        .scalars()
        .all()
    )
    checkin_dates = sorted({c.checkinDate.date().isoformat() for c in checkins})

    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "image": user.image,
            "bio": user.bio,
            "createdAt": user.createdAt.isoformat(),
        },
        "plans": plan_data,
        "focusTotalMinutes": focus_total_minutes,
        "focusSessionCount": focus_session_count,
        "focusRecords": focus_records,
        "checkinDates": checkin_dates,
    }
