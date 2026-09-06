# ============================================================
# Agent 路由（对应 src/app/api/agent/runs/** + decisions/** + cron/daily）
# ============================================================

from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.agent import (
    cancel_agent_run,
    create_agent_run,
    decide_agent_approval,
    get_agent_run_for_user,
    list_agent_runs,
    serialize_agent_run,
    list_decisions,
    update_decision_status,
    get_decision_stats,
    create_weekly_report_notification,
    run_learning_agent,
)
from app.core.security import get_current_user
from app.db.session import SessionLocal, get_db
from app.models.base import User

router = APIRouter(prefix="/api/agent", tags=["agent"])


# ---- DTO ----

class CreateRunRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=1000, description="目标至少需要 3 个字")
    mode: str = Field(default="planner", pattern="^(planner|coach|review)$")


class ApprovalRequest(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    reason: str | None = None


class DecisionFeedbackRequest(BaseModel):
    feedback: str


# ---- AgentRun ----

@router.get("/runs")
def list_runs(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Agent 运行列表（含最新步骤 + 待审批）"""
    runs = list_agent_runs(user.id)
    return {
        "runs": [
            {
                "id": r.id,
                "mode": r.mode,
                "goal": r.goal,
                "status": r.status,
                "currentStep": r.currentStep,
                "summary": r.summary,
                "error": r.error,
                "createdAt": r.createdAt.isoformat(),
                "updatedAt": r.updatedAt.isoformat(),
                "latestStep": (
                    {
                        "title": r.steps[0].title,
                        "status": r.steps[0].status,
                        "detail": r.steps[0].detail,
                    }
                    if r.steps
                    else None
                ),
                "pendingApproval": (
                    {"id": next(a.id for a in r.approvals if a.status == "pending")}
                    if any(a.status == "pending" for a in r.approvals)
                    else None
                ),
            }
            for r in runs
        ]
    }


@router.post("/runs", status_code=201)
def create_run(
    req: CreateRunRequest,
    user: User = Depends(get_current_user),
):
    """创建 Agent 运行"""
    try:
        run = create_agent_run(user.id, req.goal, req.mode)
        return {"run": serialize_agent_run(run)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    user: User = Depends(get_current_user),
):
    run = get_agent_run_for_user(run_id, user.id)
    if not run:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return {"run": serialize_agent_run(run)}


@router.post("/runs/{run_id}/approval")
def approve_run(
    run_id: str,
    req: ApprovalRequest,
    user: User = Depends(get_current_user),
):
    """审批 Agent 动作（approve/reject）"""
    try:
        result = decide_agent_approval(run_id, user.id, req.decision, req.reason)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/runs/{run_id}/cancel")
def cancel_run(
    run_id: str,
    user: User = Depends(get_current_user),
):
    """取消 Agent 运行"""
    try:
        result = cancel_agent_run(run_id, user.id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ---- AgentDecision ----

@router.get("/decisions")
def list_decisions_route(
    type: str | None = None,
    limit: int = 50,
    user: User = Depends(get_current_user),
):
    """决策列表（type 按决策类型过滤，limit 限制条数）"""
    decisions = list_decisions(user.id, {"type": type, "limit": limit})
    return {"decisions": decisions}


@router.get("/decisions/stats")
def decisions_stats(
    user: User = Depends(get_current_user),
):
    """决策统计（采纳率等）"""
    return get_decision_stats(user.id)


@router.post("/decisions/{decision_id}/feedback")
def decision_feedback(
    decision_id: str,
    req: DecisionFeedbackRequest,
    user: User = Depends(get_current_user),
):
    """给决策打反馈"""
    try:
        result = update_decision_status(decision_id, user.id, feedback=req.feedback)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ---- Cron 巡检（对应 src/app/api/agent/cron/daily/route.ts）----

@router.post("/cron/daily")
def cron_daily(
    authorization: str | None = Header(default=None),
):
    """每日巡检：对所有用户跑 run_learning_agent + 周报。

    生产环境由外部调度（APScheduler / crontab）定时调用本接口。
    鉴权与原项目一致：配置了 CRON_SECRET 时要求
    `Authorization: Bearer <CRON_SECRET>`，未配置则不校验（本地调试）。
    """
    from app.core.config import settings

    expected = settings.CRON_SECRET
    if expected and authorization != f"Bearer {expected}":
        raise HTTPException(status_code=401, detail="Unauthorized")

    from app.models.base import User as UserModel

    with SessionLocal() as db:
        users = db.execute(select(UserModel)).scalars().all()
        results = []
        for u in users:
            try:
                run_learning_agent(u.id)
                # 周日生成周报
                if datetime.now().weekday() == 6:
                    create_weekly_report_notification(u.id, db)
                results.append({"userId": u.id, "status": "ok"})
            except Exception as e:  # noqa: BLE001
                print(f"[cron/daily] 用户 {u.id} 巡检失败: {e}")
                results.append({"userId": u.id, "status": "error", "error": str(e)})
    return {"success": True, "results": results}
