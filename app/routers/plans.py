# ============================================================
# 计划路由
# - 列表 / 详情 / 创建（默认文档+任务同步）/ 更新（文档→任务同步）/ 删除
# - 任务列表 / 更新任务状态
# ============================================================

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.base import User
from app.models.study import Plan, PlanTask
from app.services.plan_split import (
    plan_task_source,
    plan_task_source_hash,
    split_plan_tasks,
)
from app.services.plan_sync import sync_tasks_from_document

router = APIRouter(prefix="/api/plans", tags=["plans"])


# ---- 工具 ----

def default_plan_document(name: str, goal: str | None = None) -> str:
    """新计划默认模板文档（带「## 任务安排」，同步成任务清单）"""
    return "\n".join(
        [
            f"# {name}",
            "",
            "## 目标",
            goal or "（写下这个计划最终要达成的结果，越具体越好）",
            "",
            "## 计划说明",
            "（整体安排、时间节奏）",
            "",
            "## 学习指导",
            "（分阶段展开：每个阶段学什么、怎么学、推荐资源、完成标准）",
            "",
            "## 任务安排",
            "- [ ] 明确目标：写下这个计划最终要达成的结果",
            "- [ ] 收集资料：整理官方文档、教程与参考资源",
            "- [ ] 学习核心知识：搭建整体框架",
            "- [ ] 动手实践：完成练习或一个小项目",
            "- [ ] 复习巩固并复盘：记录收获与待补强点",
        ]
    )


# ---- DTO ----

class PlanCreateRequest(BaseModel):
    name: str
    description: str | None = None
    goal: str | None = None
    startDate: str | None = None


class PlanUpdateRequest(BaseModel):
    name: str | None = None
    goal: str | None = None
    description: str | None = None
    status: str | None = None
    document: str | None = None
    startDate: str | None = None


class TaskUpdateRequest(BaseModel):
    taskId: str
    status: str | None = None
    title: str | None = None
    dayNumber: int | None = None


def serialize_plan(p: Plan) -> dict:
    return {
        "id": p.id,
        "userId": p.userId,
        "name": p.name,
        "description": p.description,
        "goal": p.goal,
        "document": p.document,
        "startDate": p.startDate.isoformat() if p.startDate else None,
        "status": p.status,
        "createdAt": p.createdAt.isoformat(),
        "updatedAt": p.updatedAt.isoformat(),
    }


def serialize_task(t: PlanTask) -> dict:
    return {
        "id": t.id,
        "planId": t.planId,
        "userId": t.userId,
        "title": t.title,
        "description": t.description,
        "dayNumber": t.dayNumber,
        "weekNumber": t.weekNumber,
        "category": t.category,
        "status": t.status,
        "priority": t.priority,
        "completedAt": t.completedAt.isoformat() if t.completedAt else None,
        "createdAt": t.createdAt.isoformat(),
    }


def _get_owned_plan(db: Session, plan_id: str, user_id: str) -> Plan:
    plan = db.get(Plan, plan_id)
    if plan is None or plan.userId != user_id:
        raise HTTPException(status_code=404, detail="Not found")
    return plan


# ---- 路由 ----

@router.get("")
def list_plans(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    include_tasks: bool = Query(False),
):
    """计划列表；include_tasks=true 时附带任务状态摘要"""
    rows = (
        db.execute(
            select(Plan).where(Plan.userId == user.id).order_by(Plan.updatedAt.desc())
        )
        .scalars()
        .all()
    )

    result = []
    for p in rows:
        d = serialize_plan(p)
        if include_tasks:
            tasks = (
                db.execute(select(PlanTask).where(PlanTask.planId == p.id))
                .scalars()
                .all()
            )
            d["tasks"] = [
                {
                    "status": t.status,
                    "completedAt": t.completedAt.isoformat() if t.completedAt else None,
                }
                for t in tasks
            ]
        result.append(d)
    return result


@router.post("", status_code=201)
def create_plan(
    req: PlanCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新建计划（带默认文档 + 任务同步）"""
    doc = default_plan_document(req.name, req.goal)
    start_date = None
    if req.startDate:
        try:
            start_date = datetime.fromisoformat(req.startDate.replace("Z", "+00:00"))
        except ValueError:
            start_date = None

    plan = Plan(
        userId=user.id,
        name=req.name,
        description=req.description,
        goal=req.goal,
        startDate=start_date,
        document=doc,
        status="active",
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)

    try:
        sync_tasks_from_document(db, plan.id, user.id, doc)
    except Exception as e:  # noqa: BLE001
        print(f"[createPlan] 任务同步失败: {e}")

    return {"success": True, "plan": serialize_plan(plan)}


@router.get("/{plan_id}")
def get_plan(
    plan_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = _get_owned_plan(db, plan_id, user.id)
    return serialize_plan(plan)


@router.patch("/{plan_id}")
def update_plan(
    plan_id: str,
    req: PlanUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = _get_owned_plan(db, plan_id, user.id)

    data = req.model_dump(exclude_unset=True)
    # startDate 需先解析成 datetime 再写列，避免字符串直接赋给日期列
    if "startDate" in data and data["startDate"] is not None:
        try:
            data["startDate"] = datetime.fromisoformat(data["startDate"].replace("Z", "+00:00"))
        except ValueError:
            data["startDate"] = None
    for field, value in data.items():
        setattr(plan, field, value)

    # 文档变更时，把「## 任务安排」段落同步回 PlanTask（勾选状态 + 新增任务，不删除）
    if req.document is not None:
        try:
            sync_tasks_from_document(db, plan.id, user.id, req.document)
        except Exception as e:  # noqa: BLE001
            print(f"[updatePlan] 任务同步失败: {e}")

    db.commit()
    db.refresh(plan)
    return serialize_plan(plan)


@router.post("/{plan_id}/split")
def split_plan(
    plan_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """任务重新拆分

    AI 判断文档变化是否实质影响任务 → 需要则重新拆解并对账增删改。
    幂等：2 分钟内重复触发直接返回 alreadyRunning（不重复消耗 AI 配额）。
    响应 { success, alreadyRunning, changed, reason?, created, updated, deleted }。
    """
    plan = _get_owned_plan(db, plan_id, user.id)
    try:
        return split_plan_tasks(db, plan, user.id)
    except ValueError as e:
        # 无可拆分内容返回 400，其它解析或运行时错误返回 500
        status = 400 if "可拆分的内容" in str(e) else 500
        raise HTTPException(status_code=status, detail=str(e))
    except Exception as e:  # noqa: BLE001
        print(f"[split] 拆分失败 plan={plan_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{plan_id}")
def delete_plan(
    plan_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = _get_owned_plan(db, plan_id, user.id)
    db.delete(plan)
    db.commit()
    return {"success": True}


# ---- 任务子路由 ----

@router.get("/{plan_id}/tasks")
def list_plan_tasks(
    plan_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = _get_owned_plan(db, plan_id, user.id)

    tasks = (
        db.execute(
            select(PlanTask)
            .where(PlanTask.planId == plan_id)
            .order_by(
                PlanTask.weekNumber.asc(),
                PlanTask.dayNumber.asc(),
                PlanTask.id.asc(),
            )
        )
        .scalars()
        .all()
    )

    # 任务是否过期：文档（含目标/说明）自上次拆分后是否有改动
    stale = bool(plan.tasksSourceHash) and plan.tasksSourceHash != plan_task_source_hash(plan)
    # 是否正在后台拆分任务
    splitting = plan.tasksSplittingAt is not None

    return {
        "stale": stale,
        "splitting": splitting,
        "tasks": [serialize_task(t) for t in tasks],
    }


@router.patch("/{plan_id}/tasks")
def update_plan_task(
    plan_id: str,
    req: TaskUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = _get_owned_plan(db, plan_id, user.id)

    task = db.get(PlanTask, req.taskId)
    if task is None or task.planId != plan_id:
        raise HTTPException(status_code=404, detail="Not found")

    if req.title is not None:
        task.title = req.title
    if req.dayNumber is not None:
        task.dayNumber = req.dayNumber
    if req.status is not None:
        task.status = req.status
        task.completedAt = datetime.now(timezone.utc) if req.status == "done" else None

    db.commit()
    db.refresh(task)
    return serialize_task(task)
