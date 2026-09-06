# ============================================================
# 知识库文档路由（对应 src/app/api/knowledge/documents/**）
# GET    /api/knowledge/documents                文档列表（按 sourceName 聚合）
# POST   /api/knowledge/documents                上传（multipart 文件 或 JSON 文本）
# GET    /api/knowledge/documents/{sourceName}   查看单篇（仅 md 可看）
# DELETE /api/knowledge/documents/{sourceName}   删除（全部 chunk + 原文）
#
# 上传管道（对应 knowledge-upload.ts 的 processKnowledgeText）：
#   分片 → Embedding → 批量写 DocumentChunk（含向量）→ 存 KnowledgeDoc 原文
# ============================================================

import io

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ai.rag.chunk import split_markdown, split_text
from app.ai.rag.client import embed_texts
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.base import User
from app.models.knowledge import DocumentChunk, KnowledgeDoc

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

# 最小文本长度（字符数），太短无法分片检索
MIN_TEXT_LENGTH = 10


def _extract_text(content: bytes, ext: str) -> str:
    if ext == "pdf":
        from PyPDF2 import PdfReader

        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if ext == "docx":
        from docx import Document as DocxDocument

        doc = DocxDocument(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    # md / txt：按 UTF-8 解码
    return content.decode("utf-8", errors="replace")


def _process_text(text: str, source_name: str, source_type: str, db: Session, user_id: str) -> int:
    """分片 → 嵌入 → 落库 → 存原文；返回分片数"""
    # 1. 分片：markdown 按标题，其它按固定大小
    if source_type == "markdown":
        chunks = split_markdown(text)
    else:
        chunks = split_text(text)
    if not chunks:
        raise HTTPException(status_code=400, detail="无法从内容中提取有效文本")

    # 2. Embedding（一次 API 调用批量生成；失败抛 500）
    embeddings = embed_texts(chunks)

    # 3. 批量写 DocumentChunk（含向量）
    for i, (chunk, vec) in enumerate(zip(chunks, embeddings)):
        db.add(
            DocumentChunk(
                userId=user_id,
                sourceName=source_name,
                sourceType=source_type,
                chunkIndex=i,
                content=chunk,
                embedding=vec,
            )
        )

    # 4. 存原文（唯一键 userId+sourceName，供查看页直接展示）
    doc = (
        db.execute(
            select(KnowledgeDoc).where(KnowledgeDoc.userId == user_id, KnowledgeDoc.sourceName == source_name)
        )
        .scalars()
        .first()
    )
    if doc is None:
        doc = KnowledgeDoc(userId=user_id, sourceName=source_name, sourceType=source_type, content=text)
        db.add(doc)
    else:
        doc.sourceType = source_type
        doc.content = text

    db.commit()
    return len(chunks)


@router.get("/documents")
def list_knowledge_documents(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(
            DocumentChunk.sourceName,
            DocumentChunk.sourceType,
            func.count(DocumentChunk.id).label("chunk_count"),
            func.sum(func.length(DocumentChunk.content)).label("total_chars"),
            func.max(DocumentChunk.createdAt).label("created_at"),
        )
        .where(DocumentChunk.userId == user.id)
        .group_by(DocumentChunk.sourceName, DocumentChunk.sourceType)
        .order_by(func.max(DocumentChunk.createdAt).desc())
    ).all()

    return {
        "documents": [
            {
                "sourceName": r.sourceName,
                "sourceType": r.sourceType,
                "chunkCount": int(r.chunk_count),
                "totalChars": int(r.total_chars or 0),
                "createdAt": r.created_at.isoformat(),
            }
            for r in rows
        ]
    }


@router.post("/documents", status_code=201)
async def upload_knowledge_document(
    request: Request,
    file: UploadFile | None = File(default=None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    content_type = request.headers.get("content-type", "")

    # ---- multipart：文件上传（.md / .txt / .pdf / .docx） ----
    if content_type.startswith("multipart/form-data"):
        if file is None:
            raise HTTPException(status_code=400, detail="Missing file")
        filename = file.filename or ""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        ext_map = {"md": "markdown", "markdown": "markdown", "txt": "text", "pdf": "pdf", "docx": "docx"}
        if ext not in ext_map:
            raise HTTPException(status_code=400, detail="Unsupported format. 支持 md / txt / pdf / docx")
        source_type = ext_map[ext]
        source_name = filename
        text = _extract_text(await file.read(), ext)
    # ---- JSON：粘贴文本 ----
    else:
        body = None
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = None
        body = body or {}
        text = str(body.get("text") or "")
        name = str(body.get("name") or "").strip()
        source_name = f"{name or '手动输入'}.txt"
        source_type = "text"

    text = text.strip()
    if len(text) < MIN_TEXT_LENGTH:
        raise HTTPException(status_code=400, detail="内容太短，请至少输入 10 个字符")

    # 同名文档先清旧数据（覆盖上传），避免向量/原文重复堆积
    db.execute(
        delete(DocumentChunk).where(DocumentChunk.userId == user.id, DocumentChunk.sourceName == source_name)
    )
    db.execute(
        delete(KnowledgeDoc).where(KnowledgeDoc.userId == user.id, KnowledgeDoc.sourceName == source_name)
    )
    db.commit()

    chunks = _process_text(text, source_name, source_type, db, user.id)
    return {"success": True, "sourceName": source_name, "chunks": chunks}


@router.get("/documents/{source_name}")
def get_knowledge_document(
    source_name: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # 仅 markdown 允许查看（对应原版：其它类型返回 400）
    is_md = source_name.endswith((".md", ".markdown"))
    if not is_md:
        raise HTTPException(status_code=400, detail="仅 Markdown 文档支持查看")

    # 优先取 KnowledgeDoc 原文；旧数据回退用 chunk 拼接
    doc = (
        db.execute(select(KnowledgeDoc).where(KnowledgeDoc.userId == user.id, KnowledgeDoc.sourceName == source_name))
        .scalars()
        .first()
    )
    chunks = (
        db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.userId == user.id, DocumentChunk.sourceName == source_name)
            .order_by(DocumentChunk.chunkIndex.asc(), DocumentChunk.createdAt.asc())
        )
        .scalars()
        .all()
    )
    if not chunks:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc is not None:
        content = doc.content
        source_type = doc.sourceType
    else:
        content = "\n\n".join(c.content for c in chunks)
        source_type = chunks[0].sourceType

    return {
        "document": {
            "sourceName": source_name,
            "sourceType": source_type,
            "content": content,
            "chunkCount": len(chunks),
            "createdAt": chunks[0].createdAt.isoformat(),
        }
    }


@router.delete("/documents/{source_name}")
def delete_knowledge_document(
    source_name: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    result = db.execute(
        delete(DocumentChunk).where(DocumentChunk.userId == user.id, DocumentChunk.sourceName == source_name)
    )
    db.execute(
        delete(KnowledgeDoc).where(KnowledgeDoc.userId == user.id, KnowledgeDoc.sourceName == source_name)
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"success": True, "deletedChunks": result.rowcount}
