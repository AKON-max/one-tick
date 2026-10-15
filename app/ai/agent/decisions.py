# ============================================================
# AgentDecision 服务
#
# 记录 Agent 的每一次自主决策，供后续：
# ① 追溯 — 查看 Agent 在过去做了哪些干预
# ② 评估 — 统计决策采纳率、效果
# ③ 优化 — 分析决策质量，改进 prompt 和策略
#
# 设计原则：
# - 决策记录不阻塞 Agent 主流程（fire-and-forget，失败不抛）
# - 每个决策关联到 AgentRun，方便按运行批次追溯
# - status 字段支持决策生命周期：executed → 用户采纳/拒绝 → 效果评估
# ============================================================

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional, TypedDict

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.agent import AgentDecision

# ---- 类型 ----

DecisionType = Literal["PLAN_ADJUST", "REMINDER", "ANALYSIS", "TASK_CREATE"]
DecisionStatus = Literal["executed", "pending", "rejected", "failed"]


class AgentDecisionRecord(TypedDict):
    id: str
    userId: str
    runId: Optional[str]
    type: str
    reason: str
    action: dict
    status: str
    feedback: Optional[str]
    createdAt: str


class DecisionStats(TypedDict):
    total: int
    byType: dict[str, int]
    byStatus: dict[str, int]
    recentRate: int  # 最近7天采纳率


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(d: AgentDecision) -> AgentDecisionRecord:
    return {
        "id": d.id,
        "userId": d.userId,
        "runId": d.runId,
        "type": d.type,
        "reason": d.reason,
        "action": d.action or {},
        "status": d.status,
        "feedback": d.feedback,
        "createdAt": d.createdAt.isoformat(),
    }


# ---- 创建决策 ----

def create_decision(
    db,
    user_id: str,
    run_id: Optional[str],
    type: str,
    reason: str,
    action: dict,
    status: str = "executed",
):
    """创建一条 Agent 决策留痕。

    fire-and-forget：失败只记日志返回 None，绝不抛出影响主流程。
    可传入共享 db session（随主流程一起提交），或传 None 自行开 session。
    """
    own = db is None
    if own:
        db = SessionLocal()
    try:
        decision = AgentDecision(
            userId=user_id,
            runId=run_id,
            type=type,
            reason=reason,
            action=action or {},
            status=status,
        )
        db.add(decision)
        db.commit()
        db.refresh(decision)

        print(
            f"[Decision] 创建决策: {decision.type} | user={user_id} | run={run_id or 'no-run'}"
        )
        return _serialize(decision)
    except Exception as error:  # noqa: BLE001
        print(f"[Decision] 创建失败: {error}")
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None
    finally:
        if own:
            db.close()


# ---- 查询 ----

def list_decisions(
    user_id: str,
    options: Optional[dict] = None,
) -> list[AgentDecisionRecord]:
    """查询决策列表（options: type / limit / runId）"""
    options = options or {}
    mtype = options.get("type")
    limit = int(options.get("limit") or 20)
    run_id = options.get("runId")

    with SessionLocal() as db:
        q = select(AgentDecision).where(AgentDecision.userId == user_id)
        if mtype:
            q = q.where(AgentDecision.type == mtype)
        if run_id:
            q = q.where(AgentDecision.runId == run_id)
        rows = (
            db.execute(q.order_by(AgentDecision.createdAt.desc()).limit(limit))
            .scalars()
            .all()
        )
    return [_serialize(d) for d in rows]


def get_latest_analysis(user_id: str) -> Optional[AgentDecisionRecord]:
    """获取最近一次 Agent 分析决策"""
    decisions = list_decisions(user_id, {"type": "ANALYSIS", "limit": 1})
    return decisions[0] if decisions else None


# ---- 更新 ----

def update_decision_status(
    decision_id: str,
    user_id: str,
    status: str,
    feedback: Optional[str] = None,
) -> bool:
    """更新决策状态（用户采纳/拒绝后的反馈）"""
    try:
        with SessionLocal() as db:
            decision = db.execute(
                select(AgentDecision).where(
                    AgentDecision.id == decision_id,
                    AgentDecision.userId == user_id,
                )
            ).scalar_one_or_none()
            if decision is None:
                return False
            decision.status = status
            decision.feedback = feedback
            db.commit()
        return True
    except Exception as error:  # noqa: BLE001
        print(f"[Decision] 更新状态失败: {error}")
        return False


# ---- 统计 ----

def get_decision_stats(user_id: str) -> DecisionStats:
    """决策统计（total / byType / byStatus / 最近7天采纳率）"""
    week_start = _now() - timedelta(days=7)

    with SessionLocal() as db:
        all_rows = db.execute(
            select(AgentDecision.type, AgentDecision.status).where(
                AgentDecision.userId == user_id
            )
        ).all()
        recent_rows = db.execute(
            select(AgentDecision.status).where(
                AgentDecision.userId == user_id,
                AgentDecision.createdAt >= week_start,
            )
        ).scalars().all()

    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    for mtype, mstatus in all_rows:
        by_type[mtype] = by_type.get(mtype, 0) + 1
        by_status[mstatus] = by_status.get(mstatus, 0) + 1

    recent_rate = (
        round(
            len([s for s in recent_rows if s in ("executed", "pending")])
            / len(recent_rows)
            * 100
        )
        if recent_rows
        else 0
    )

    return {
        "total": len(all_rows),
        "byType": by_type,
        "byStatus": by_status,
        "recentRate": recent_rate,
    }
