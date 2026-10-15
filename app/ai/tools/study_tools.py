# ============================================================
# Study 工具
# 工厂函数 create_study_tools(user_id) 闭包注入用户身份
# ============================================================

from datetime import datetime, timedelta, timezone

from app.ai.memory import get_relevant_memories
from app.ai.tools.utils import safe_execute
from app.db.session import SessionLocal
from app.models.study import Checkin, Plan, PlanTask
from app.services.study_stats import get_study_stats


def _default_plan_document(name: str, goal: str | None = None) -> str:
    """新计划默认模板文档（带「## 任务安排」同步成任务清单）"""
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
            "## 任务安排",
            "- [ ] 明确目标：写下这个计划最终要达成的结果",
            "- [ ] 收集资料：整理官方文档、教程与参考资源",
            "- [ ] 学习核心知识：搭建整体框架",
            "- [ ] 动手实践：完成练习或一个小项目",
            "- [ ] 复习巩固并复盘：记录收获与待补强点",
        ]
    )


def create_study_tools(
    user_id: str,
    opts: dict | None = None,
):
    """创建针对特定用户的学习助手工具集"""
    opts = opts or {}

    def create_plan(args: dict):
        """Tool 1: 创建学习计划（只收结构化小参数，详细文档+任务由系统生成）"""
        name = args.get("name", "")
        goal = args.get("goal")
        description = args.get("description")

        def _run():
            with SessionLocal() as db:
                doc = _default_plan_document(name, goal)
                plan = Plan(
                    userId=user_id,
                    name=name,
                    description=description,
                    goal=goal,
                    document=doc,
                    status="active",
                )
                db.add(plan)
                db.commit()
                db.refresh(plan)

                # 同步文档「## 任务安排」段落为任务
                from app.services.plan_sync import sync_tasks_from_document
                sync_tasks_from_document(db, plan.id, user_id, doc)

                task_count = len(plan.tasks)
                return {
                    "success": True,
                    "message": f"学习计划「{name}」创建成功，共 {task_count} 个任务",
                    "plan": {"id": plan.id, "name": plan.name, "goal": plan.goal},
                }

        return safe_execute("createPlan", _run)

    def get_my_plans(args: dict):
        """Tool 2: 查询所有学习计划及进度"""
        status = args.get("status")

        def _run():
            with SessionLocal() as db:
                q = db.query(Plan).filter(Plan.userId == user_id)
                if status:
                    q = q.filter(Plan.status == status)
                plans = q.order_by(Plan.updatedAt.desc()).all()

                if not plans:
                    return {"success": True, "count": 0, "plans": [], "message": "还没有学习计划"}

                plans_with_progress = []
                for plan in plans:
                    tasks = db.query(PlanTask).filter(PlanTask.planId == plan.id).all()
                    total = len(tasks)
                    done = len([t for t in tasks if t.status == "done"])
                    progress = round(done / total * 100) if total > 0 else 0
                    plans_with_progress.append(
                        {
                            "id": plan.id,
                            "name": plan.name,
                            "goal": plan.goal,
                            "progress": progress,
                            "status": plan.status,
                        }
                    )
                return {"success": True, "count": len(plans_with_progress), "plans": plans_with_progress}

        return safe_execute("getMyPlans", _run)

    def get_recent_checkins(args: dict):
        """Tool 3: 查询近期打卡记录"""
        days = min(int(args.get("days") or 7), 30)

        def _run():
            since = datetime.now(timezone.utc) - timedelta(days=days)
            with SessionLocal() as db:
                checkins = (
                    db.query(Checkin)
                    .filter(Checkin.userId == user_id, Checkin.checkinDate >= since)
                    .order_by(Checkin.checkinDate.desc())
                    .all()
                )
                if not checkins:
                    return {"success": True, "count": 0, "checkins": []}
                return {
                    "success": True,
                    "count": len(checkins),
                    "checkins": [
                        {"content": c.content, "planName": None, "date": c.checkinDate.isoformat()}
                        for c in checkins
                    ],
                }

        return safe_execute("getRecentCheckins", _run)

    def get_my_memories(args: dict):
        """Tool 4: 查询 AI 对用户的长期记忆"""
        limit = int(args.get("limit") or 10)
        query = args.get("query")

        def _run():
            memories = get_relevant_memories(user_id, limit, query)
            if not memories:
                return {
                    "success": True,
                    "count": 0,
                    "memories": [],
                    "message": "我目前还没有关于你的长期记忆。多和我聊聊吧！",
                }
            return {
                "success": True,
                "count": len(memories),
                "memories": [
                    {"id": m["id"], "content": m["content"], "category": m["type"],
                     "createdAt": m["createdAt"].isoformat()}
                    for m in memories
                ],
            }

        return safe_execute("getMyMemories", _run)

    def get_study_stats(args: dict):
        """Tool 5: 综合学习统计"""
        def _run():
            with SessionLocal() as db:
                stats = get_study_stats(db, user_id)
                return {"success": True, "stats": stats}

        return safe_execute("getStudyStats", _run)

    tools = {
        "getMyPlans": get_my_plans,
        "getRecentCheckins": get_recent_checkins,
        "getMyMemories": get_my_memories,
        "getStudyStats": get_study_stats,
    }
    # 在文档工作室编辑已有计划时不提供 createPlan
    if not opts.get("excludeCreatePlan"):
        tools["createPlan"] = create_plan
    return tools
