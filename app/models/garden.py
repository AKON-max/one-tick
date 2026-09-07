# ============================================================
# 植物农场模型（本平台特色玩法）
# 每用户一行：专注时长自动累积为能量，手动浇水消耗能量让植物进阶
# ============================================================

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# 一次浇水消耗的能量（专注分钟）
WATER_COST = 25
# 植物造型阶段：0(种子) ~ 4(成株)，共 5 个造型
MAX_STAGE = 4


class Garden(Base):
    """植物农场状态（userId 主键，每用户一行）"""

    __tablename__ = "garden"

    userId: Mapped[str] = mapped_column(
        String, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    # 可用能量 = 累计专注分钟 - 已消耗（浇水）
    energy: Mapped[int] = mapped_column(Integer, default=0)
    # 浇水次数（驱动阶段进阶：stage = min(wateredCount, MAX_STAGE)）
    wateredCount: Mapped[int] = mapped_column(Integer, default=0)
    # 成熟收获次数：每次“开花结果”后再浇水一次即收获，
    # 小岛上的树 +1，盆栽回到种子重新长（见 routers/garden.py）
    maturedCount: Mapped[int] = mapped_column(Integer, default=0)
    createdAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now
    )
    updatedAt: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    @property
    def stage(self) -> int:
        """当前造型阶段 0~4（收获后会回到 0 重新种）"""
        return min(self.wateredCount, MAX_STAGE)

    def to_dict(self) -> dict:
        return {
            "energy": self.energy,
            "wateredCount": self.wateredCount,
            "maturedCount": self.maturedCount,
            "stage": self.stage,
            "waterCost": WATER_COST,
            "maxStage": MAX_STAGE,
            "updatedAt": self.updatedAt.isoformat() if self.updatedAt else None,
        }
