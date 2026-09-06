# ============================================================
# Agent 工具（对应 src/lib/tools/agent-tools.ts）
# ① breakdownPlanTasks — 将计划拆分为每日/每周具体任务（Agent 规划阶段）
# ② getPlanTasks       — 查询计划的所有任务及统计（Agent 观察阶段）
# ③ updateTaskStatus   — 更新任务状态（Agent 执行阶段）
# ④ getTodayTasks      — 获取今日应完成任务（每日检查 Agent）
# ============================================================

from datetime import datetime, timezone

from app.ai.agent.service import generate_plan_for_plan
from app.ai.tools.utils import safe_execute
from app.db.session import SessionLocal
from app.models.study import Plan, PlanTask


def _format_task(t: PlanTask) -> dict:
    return {
        "id": t.id,
        "planId": t.planId,
        "title": t.title,
        "description": t.description,
        "dayNumber": t.dayNumber,
        "weekNumber": t.weekNumber,
        "category": t.category or "study",
        "status": t.status or "pending",
        "priority": t.priority or "normal",
        "completedAt": t.completedAt.isoformat() if t.completedAt else None,
        "createdAt": t.createdAt.isoformat(),
    }


def create_agent_tools(user_id: str) -> dict:
    """创建 Agent Workflow 工具集"""

    def breakdown_plan_tasks(args: dict):
        """Tool: 拆分计划为任务（Agent 规划阶段，一次调用批量创建）"""
        plan_id = args.get("planId", "")

        def _run():
            with SessionLocal() as db:
                plan = db.get(Plan, plan_id)
                if plan is None or plan.userId != user_id:
                    return {"success": False, "error": "计划不存在"}

                # 复用 generate_plan_for_plan：LLM 生成 PlanDraft → 批量建任务
                result = generate_plan_for_plan(
                    plan.id, user_id,
                    {"goal": plan.goal, "description": plan.description, "conversation": None, "memories": None},
                )
                return result

        return safe_execute("breakdownPlanTasks", _run)

    def get_plan_tasks(args: dict):
        """Tool: 查询计划的所有任务及统计（Agent 观察阶段）"""
        plan_id = args.get("planId", "")

        def _run():
            with SessionLocal() as db:
                plan = db.get(Plan, plan_id)
                if plan is None or plan.userId != user_id:
                    return {"success": False, "error": "计划不存在"}
                tasks = (
                    db.query(PlanTask)
                    .filter(PlanTask.planId == plan_id)
                    .order_by(PlanTask.weekNumber.asc(), PlanTask.dayNumber.asc(), PlanTask.id.asc())
                    .all()
                )
                done = len([t for t in tasks if t.status == "done"])
                total = len(tasks)
                return {
                    "success": True,
                    "plan": {"id": plan.id, "name": plan.name, "progress": round(done / total * 100) if total else 0},
                    "taskCount": total,
                    "doneCount": done,
                    "tasks": [_format_task(t) for t in tasks],
                }

        return safe_execute("getPlanTasks", _run)

    def update_task_status(args: dict):
        """Tool: 更新任务状态（Agent 执行阶段）"""
        task_id = args.get("taskId", "")
        status = args.get("status", "")

        def _run():
            with SessionLocal() as db:
                task = db.query(PlanTask).filter(PlanTask.id == task_id, PlanTask.userId == user_id).first()
                if task is None:
                    return {"success": False, "error": "任务不存在"}
                if status not in ("pending", "in_progress", "done", "skipped"):
                    return {"success": False, "error": f"无效状态: {status}"}
                task.status = status
                task.completedAt = datetime.now(timezone.utc) if status == "done" else None
                db.commit()
                db.refresh(task)
                return {"success": True, "task": _format_task(task)}

        return safe_execute("updateTaskStatus", _run)

    def get_today_tasks(args: dict):
        """Tool: 获取今日应完成任务（每日检查 Agent）"""
        today = datetime.now(timezone.utc).date()
        day_number = (today - datetime(2026, 1, 1, tzinfo=timezone.utc).date()).days + 1  # 距起点天数

        def _run():
            with SessionLocal() as db:
                # 今日任务：dayNumber 匹配今天，或 pending/in_progress 的任务
                tasks = (
                    db.query(PlanTask)
                    .filter(PlanTask.userId == user_id)
                    .filter(
                        (PlanTask.dayNumber == day_number) | (PlanTask.status.in_(["pending", "in_progress"]))
                    )
                    .order_by(PlanTask.priority.desc(), PlanTask.dayNumber.asc())
                    .limit(20)
                    .all()
                )
                return {
                    "success": True,
                    "today": today.isoformat(),
                    "count": len(tasks),
                    "tasks": [_format_task(t) for t in tasks],
                }

        return safe_execute("getTodayTasks", _run)

    return {
        "breakdownPlanTasks": breakdown_plan_tasks,
        "getPlanTasks": get_plan_tasks,
        "updateTaskStatus": update_task_status,
        "getTodayTasks": get_today_tasks,
    }
