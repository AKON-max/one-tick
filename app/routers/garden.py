# ============================================================
# 植物农场路由（自研玩法）
#   GET  /api/garden        — 植物状态（能量/浇水次数/阶段）
#   POST /api/garden/water  — 浇水：消耗 25 能量，植物进阶一段
# 能量由专注会话自动累积（见 focus.py），本路由只读 + 浇水消耗
# ============================================================

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.base import User
from app.models.garden import MAX_STAGE, WATER_COST, Garden

router = APIRouter(prefix="/api/garden", tags=["garden"])


def _get_or_create(user_id: str, db: Session) -> Garden:
    garden = db.execute(select(Garden).where(Garden.userId == user_id)).scalars().first()
    if garden is None:
        garden = Garden(userId=user_id)
        db.add(garden)
        db.commit()
        db.refresh(garden)
    return garden


@router.get("")
def get_garden(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """植物当前状态（每用户一行，首次访问自动创建）"""
    garden = _get_or_create(user.id, db)
    return garden.to_dict()


@router.post("/water")
def water_plant(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """浇水：消耗 WATER_COST 能量，浇水次数 +1（原子防刷：能量不足不扣）。
    阶段 0→4 是生长过程；在“开花结果”(MAX_STAGE) 后再浇一次 = 收获：
    maturedCount +1（小岛多一棵树），盆栽回到种子重新种。
    """
    garden = _get_or_create(user.id, db)

    if garden.energy < WATER_COST:
        raise HTTPException(
            status_code=400,
            detail={"code": "INSUFFICIENT_ENERGY", "message": "能量不足，先专注攒能量吧"},
        )

    now = datetime.now(timezone.utc)
    # 条件更新保证幂等：energy 在扣减瞬间低于阈值则 rowcount=0，不会误扣
    result = db.execute(
        update(Garden)
        .where(Garden.userId == user.id, Garden.energy >= WATER_COST)
        .values(
            energy=Garden.energy - WATER_COST,
            wateredCount=Garden.wateredCount + 1,
            updatedAt=now,
        )
    )
    db.commit()

    if result.rowcount == 0:
        raise HTTPException(
            status_code=400,
            detail={"code": "INSUFFICIENT_ENERGY", "message": "能量不足，先专注攒能量吧"},
        )

    db.refresh(garden)
    harvested = False
    if garden.wateredCount > MAX_STAGE:
        # 超出最高造型的那次浇水 = 收获：树种到小岛，盆栽重新播种
        garden.maturedCount += 1
        garden.wateredCount = 0
        garden.updatedAt = now
        db.commit()
        db.refresh(garden)
        harvested = True

    return {"ok": True, "harvested": harvested, **garden.to_dict()}
