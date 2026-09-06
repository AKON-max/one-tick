# ============================================================
# 待办路由（对应 src/app/api/todos/**）
# ============================================================

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.base import User
from app.models.study import Todo

router = APIRouter(prefix="/api/todos", tags=["todos"])


class TodoCreateRequest(BaseModel):
    title: str
    # 可选：老 localStorage 数据一次性迁移时保留原状态/创建时间（对齐原 TS 路由）
    completed: bool | None = None
    createdAt: str | None = None


class TodoUpdateRequest(BaseModel):
    title: str | None = None
    completed: bool | None = None


class TodoResponse(BaseModel):
    id: str
    title: str
    completed: bool
    createdAt: str
    updatedAt: str

    @classmethod
    def from_model(cls, t: Todo) -> "TodoResponse":
        return cls(
            id=t.id,
            title=t.title,
            completed=t.completed,
            createdAt=t.createdAt.isoformat(),
            updatedAt=t.updatedAt.isoformat(),
        )


@router.get("")
def list_todos(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """待办列表；返回 {todos: [...]}，对齐原 src/app/api/todos/route.ts"""
    rows = (
        db.execute(
            select(Todo)
            .where(Todo.userId == user.id)
            .order_by(Todo.createdAt.desc())
        )
        .scalars()
        .all()
    )
    return {"todos": [TodoResponse.from_model(t) for t in rows]}


@router.post("", status_code=201)
def create_todo(
    req: TodoCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新建待办；返回 {todo: {...}}，对齐原 TS 路由（completed/createdAt 可选供迁移）"""
    created_at = None
    if req.createdAt:
        try:
            created_at = datetime.fromisoformat(req.createdAt.replace("Z", "+00:00"))
        except ValueError:
            created_at = None
    todo = Todo(
        userId=user.id,
        title=req.title.strip(),
        completed=req.completed if req.completed is not None else False,
        createdAt=created_at,
    )
    db.add(todo)
    db.commit()
    db.refresh(todo)
    return {"todo": TodoResponse.from_model(todo)}


@router.patch("/{todo_id}", response_model=TodoResponse)
def update_todo(
    todo_id: str,
    req: TodoUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 至少提供 title 或 completed 之一
    has_title = req.title is not None and req.title.strip() != ""
    has_completed = req.completed is not None
    if not has_title and not has_completed:
        raise HTTPException(status_code=400, detail="Title or Completed is required")

    todo = db.get(Todo, todo_id)
    if todo is None or todo.userId != user.id:
        raise HTTPException(status_code=404, detail="Todo not found")

    if has_title:
        todo.title = req.title.strip()
    if has_completed:
        todo.completed = req.completed
    db.commit()
    db.refresh(todo)
    return TodoResponse.from_model(todo)


@router.delete("/{todo_id}")
def delete_todo(
    todo_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    todo = db.get(Todo, todo_id)
    if todo is None or todo.userId != user.id:
        raise HTTPException(status_code=404, detail="Todo not found")
    db.delete(todo)
    db.commit()
    return {"success": True}
