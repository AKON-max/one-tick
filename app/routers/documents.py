# ============================================================
# 文档工作室路由（对应 src/app/api/documents/**）
# GET    /api/documents                列表（100 条，updatedAt desc，不含 content）
# POST   /api/documents                创建/导入（multipart .md 文件 或 JSON）
# GET    /api/documents/{id}           单篇详情（校验归属）
# PATCH  /api/documents/{id}           更新标题/内容
# DELETE /api/documents/{id}           删除
# ============================================================

import re

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.base import User
from app.models.knowledge import Document, DocumentChunk

router = APIRouter(prefix="/api/documents", tags=["documents"])

MAX_TITLE = 120
MAX_CONTENT = 500_000
DEFAULT_TITLE = "未命名文档"


def _dto(d: Document, with_content: bool = True) -> dict:
    data = {
        "id": d.id,
        "userId": d.userId,
        "title": d.title,
        "createdAt": d.createdAt.isoformat(),
        "updatedAt": d.updatedAt.isoformat(),
    }
    if with_content:
        data["content"] = d.content
    return data


def _get_owned(db: Session, doc_id: str, user_id: str) -> Document:
    """查询 + 所有权校验：文档不存在与无权访问统一 404"""
    doc = db.get(Document, doc_id)
    if doc is None or doc.userId != user_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("")
def list_documents(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.execute(
            select(Document).where(Document.userId == user.id).order_by(Document.updatedAt.desc()).limit(100)
        )
        .scalars()
        .all()
    )
    return {"documents": [_dto(d, with_content=False) for d in rows]}


@router.post("", status_code=201)
async def create_document(
    request: Request,
    file: UploadFile | None = File(default=None),
    title: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content_type = request.headers.get("content-type", "")

    # ---- multipart：导入 .md / .markdown / .txt 文件 ----
    if content_type.startswith("multipart/form-data"):
        if file is None:
            raise HTTPException(status_code=400, detail="Missing file")
        # 标题优先取表单字段，否则取文件名去掉扩展名
        doc_title = (title or "").strip()
        if not doc_title:
            name = file.filename or ""
            doc_title = re.sub(r"\.(md|markdown|txt)$", "", name, flags=re.IGNORECASE)
        content = (await file.read()).decode("utf-8", errors="replace")
    # ---- JSON：直接传 title/content ----
    else:
        body = None
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = None
        body = body or {}
        doc_title = str(body.get("title") or "").strip()
        content = body.get("content") or ""

    # 默认标题
    if not doc_title:
        doc_title = DEFAULT_TITLE

    # 大小限制（字符数）
    if len(content) > MAX_CONTENT:
        raise HTTPException(status_code=413, detail="文档过大（>500KB）")

    doc = Document(userId=user.id, title=doc_title[:MAX_TITLE], content=content)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return {"document": _dto(doc)}


@router.get("/{doc_id}")
def get_document(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """单篇详情；indexed 表示该文档标题已加入知识库（对应 docs/[id] 页的只读判定）"""
    doc = _get_owned(db, doc_id, user.id)
    indexed = (
        db.execute(
            select(DocumentChunk.id)
            .where(
                DocumentChunk.userId == user.id,
                DocumentChunk.sourceName.in_([f"{doc.title}.md", f"{doc.title}.markdown"]),
            )
            .limit(1)
        )
        .scalar_one_or_none()
        is not None
    )
    return {"document": _dto(doc), "indexed": indexed}


class DocumentUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None


@router.patch("/{doc_id}")
def update_document(
    doc_id: str,
    req: DocumentUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = _get_owned(db, doc_id, user.id)
    if req.title is not None:
        doc.title = req.title[:MAX_TITLE]
    if req.content is not None:
        doc.content = req.content
    db.commit()
    db.refresh(doc)
    return {"document": _dto(doc)}


@router.delete("/{doc_id}")
def delete_document(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _get_owned(db, doc_id, user.id)
    doc = db.get(Document, doc_id)
    db.delete(doc)
    db.commit()
    return {"success": True}
