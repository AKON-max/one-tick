# ============================================================
# 打卡路由（对应 src/app/(dashboard)/checkin/actions.ts + api）
# - daily_checkin：每日签到（当天去重）
# - 列表 / 详情
# ============================================================

from datetime import datetime, time, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.base import User
from app.models.study import Checkin

router = APIRouter(prefix="/api/checkins", tags=["checkin"])


class DailyCheckinRequest(BaseModel):
    mood: str | None = None
    scene: str | None = None


class CheckinResponse(BaseModel):
    id: str
    content: str
    hours: float
    subject: str | None = None
    mood: str | None = None
    screenshot: str | None = None
    checkinDate: str
    planId: str | None = None

    @classmethod
    def from_model(cls, c: Checkin) -> "CheckinResponse":
        return cls(
            id=c.id,
            content=c.content,
            hours=c.hours,
            subject=c.subject,
            mood=c.mood,
            screenshot=c.screenshot,
            checkinDate=c.checkinDate.isoformat(),
            planId=c.planId,
        )


def _day_start() -> datetime:
    return datetime.combine(datetime.now(timezone.utc).date(), time.min, tzinfo=timezone.utc)


@router.post("/daily")
def daily_checkin(
    req: DailyCheckinRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """每日签到（当天去重；场景决定文案）"""
    now = datetime.now(timezone.utc)
    today_start = _day_start()

    existing = (
        db.execute(
            select(Checkin).where(
                Checkin.userId == user.id,
                Checkin.checkinDate >= today_start,
            )
        )
        .scalars()
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="今天已经来过了")

    # 场景文案（未传或非法兜底雨林）
    visit_text = "到访雨林"
    if req.scene == "snow":
        visit_text = "到访雪日"
    elif req.scene == "cloud":
        visit_text = "到访暖云"

    checkin = Checkin(
        userId=user.id,
        content=visit_text,
        hours=0,
        mood=req.mood,
        checkinDate=now,
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)
    return {"success": True, "checkin": CheckinResponse.from_model(checkin)}


@router.get("", response_model=list[CheckinResponse])
def list_checkins(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """打卡历史（按时间倒序）"""
    rows = (
        db.execute(
            select(Checkin)
            .where(Checkin.userId == user.id)
            .order_by(Checkin.checkinDate.desc())
        )
        .scalars()
        .all()
    )
    return [CheckinResponse.from_model(c) for c in rows]


# ---- 签到页聚合数据（对应 checkin/page.tsx 的 7 次 Prisma 查询）----

class CheckinSummaryResponse(BaseModel):
    """小岛签到页一次拿全的数据"""
    todayCheckin: bool
    streak: int
    totalCheckins: int
    totalHours: float
    weekCheckins: int
    heatmap: list[dict]
    longestStreak: int

    @classmethod
    def from_data(cls, d: dict) -> "CheckinSummaryResponse":
        return cls(**d)


@router.get("/summary", response_model=CheckinSummaryResponse)
def checkin_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """签到页聚合：今日/连续/总数/时长/本周/年度热力图/最长连续"""
    from app.services.study_stats import build_checkin_summary

    data = build_checkin_summary(db, user.id)
    return CheckinSummaryResponse.from_data(data)


@router.get("/{checkin_id}", response_model=CheckinResponse)
def get_checkin(
    checkin_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    c = db.get(Checkin, checkin_id)
    if c is None or c.userId != user.id:
        raise HTTPException(status_code=404, detail="打卡记录不存在")
    return CheckinResponse.from_model(c)
