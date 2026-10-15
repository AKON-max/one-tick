# ============================================================
# Todo 工具
# ============================================================

from app.ai.tools.utils import safe_execute
from app.db.session import SessionLocal
from app.models.study import Todo


def _format_todo(t: Todo) -> dict:
    return {
        "id": t.id,
        "title": t.title,
        "completed": t.completed,
        "createdAt": t.createdAt.isoformat(),
    }


def create_todo_tools(user_id: str) -> dict:
    """创建针对特定用户的待办工具集"""

    def get_my_todos(args: dict):
        """Tool 1: 查询今日待办（未完成在前、新的在前）"""
        def _run():
            with SessionLocal() as db:
                todos = (
                    db.query(Todo)
                    .filter(Todo.userId == user_id)
                    .order_by(Todo.completed.asc(), Todo.createdAt.desc())
                    .all()
                )
                if not todos:
                    return {
                        "success": True,
                        "count": 0,
                        "todos": [],
                        "message": "今天还没有待办，要不要加一条？",
                    }
                return {"success": True, "count": len(todos), "todos": [_format_todo(t) for t in todos]}

        return safe_execute("getMyTodos", _run)

    def create_todo(args: dict):
        """Tool 2: 新增待办"""
        title = args.get("title", "")

        def _run():
            with SessionLocal() as db:
                t = Todo(userId=user_id, title=title.strip())
                db.add(t)
                db.commit()
                db.refresh(t)
                return {
                    "success": True,
                    "message": f"已把「{t.title}」加入今日待办",
                    "todo": _format_todo(t),
                }

        return safe_execute("createTodo", _run)

    def update_todo(args: dict):
        """Tool 3: 更新待办（勾选完成/取消 + 修改标题）"""
        todo_id = args.get("id")
        title = args.get("title")
        completed = args.get("completed")

        def _run():
            with SessionLocal() as db:
                existing = (
                    db.query(Todo).filter(Todo.id == todo_id, Todo.userId == user_id).first()
                )
                if not existing:
                    raise ValueError(f"待办不存在: {todo_id}")
                if title is None and completed is None:
                    raise ValueError("请至少提供 title 或 completed 之一")

                if title is not None:
                    existing.title = title.strip()
                if completed is not None:
                    existing.completed = bool(completed)

                db.commit()
                db.refresh(existing)

                msg = (
                    f"已勾选「{existing.title}」"
                    if completed is True
                    else f"已重新打开「{existing.title}」"
                    if completed is False
                    else f"已把待办改为「{existing.title}」"
                )
                return {"success": True, "message": msg, "todo": _format_todo(existing)}

        return safe_execute("updateTodo", _run)

    def delete_todo(args: dict):
        """Tool 4: 删除待办"""
        todo_id = args.get("id")

        def _run():
            with SessionLocal() as db:
                existing = (
                    db.query(Todo).filter(Todo.id == todo_id, Todo.userId == user_id).first()
                )
                if not existing:
                    raise ValueError(f"待办不存在: {todo_id}")
                db.delete(existing)
                db.commit()
                return {"success": True, "message": f"已删除待办「{existing.title}」"}

        return safe_execute("deleteTodo", _run)

    return {
        "getMyTodos": get_my_todos,
        "createTodo": create_todo,
        "updateTodo": update_todo,
        "deleteTodo": delete_todo,
    }
