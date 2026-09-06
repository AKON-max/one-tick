# ============================================================
# RAG 向量检索 — Python 余弦相似度版（对应 src/lib/rag/retriever.ts）
#
# DocumentChunk.embedding 在 db 中是 pgvector Vector 类型，
# 采用全量加载后在内存中计算余弦相似度排序的方案。
# 文档块数量通常不超过几百条，性能足够。
# ============================================================

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.knowledge import DocumentChunk


@dataclass
class DocChunk:
    """检索返回的文档块（不含 embedding，与原 TS 的 DocChunk 对齐）"""

    id: str
    sourceName: str
    sourceType: str
    chunkIndex: int
    content: str
    createdAt: datetime


# ---- 余弦相似度 ----

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """计算两个向量的余弦相似度；长度不一致返回 0"""
    if len(a) != len(b):
        return 0.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    d = (na ** 0.5) * (nb ** 0.5)
    return 0.0 if d == 0 else dot / d


# ---- 向量解析 ----

def parse_embedding(raw: Any) -> list[float]:
    """从 pgvector / 数据库返回的值中提取 number[] 向量

    pgvector 的 Vector 对象继承自 numpy.ndarray（可 tolist）；
    兼容 json 字符串、list、tuple、dict（{value/data: [...]}）等形态。
    """
    if raw is None:
        return []
    # numpy 数组 / pgvector Vector（继承 ndarray，含 tolist）
    if hasattr(raw, "tolist"):
        try:
            return [float(v) for v in raw.tolist()]
        except Exception:  # noqa: BLE001
            pass
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:  # noqa: BLE001
            return []
    if isinstance(raw, (list, tuple)):
        return [float(v) for v in raw]
    if isinstance(raw, dict):
        # 某些驱动将向量返回为 { value: [...] } 或 { data: [...] }
        for key in ("value", "data"):
            val = raw.get(key)
            if isinstance(val, (list, tuple)):
                return [float(v) for v in val]
        # 尝试直接取数字值
        vals = [v for v in raw.values() if isinstance(v, (int, float))]
        if vals:
            return [float(v) for v in vals]
    return []


# ---- 检索 ----

def search_similar_chunks(
    query_embedding: list[float],
    top_k: int = 5,
    source_filter: Optional[str] = None,
    user_id: Optional[str] = None,
) -> list[DocChunk]:
    """向量语义搜索（内存计算）

    :param query_embedding: 查询向量
    :param top_k:           返回条数（默认 5）
    :param source_filter:   可选：限定来源（sourceName）
    :param user_id:         可选：限定用户
    """
    conditions = [DocumentChunk.embedding.isnot(None)]
    if user_id:
        conditions.append(DocumentChunk.userId == user_id)
    if source_filter:
        conditions.append(DocumentChunk.sourceName == source_filter)

    # 1. 全量加载有 embedding 的文档块（与原 TS 一致，最多取 1000 条）
    stmt = (
        select(DocumentChunk)
        .where(*conditions)
        .order_by(DocumentChunk.createdAt.desc())
        .limit(1000)
    )
    with SessionLocal() as db:
        rows = db.execute(stmt).scalars().all()

    return _rank_and_return(rows, query_embedding, top_k)


def _rank_and_return(
    rows: list[DocumentChunk],
    query_embedding: list[float],
    top_k: int,
) -> list[DocChunk]:
    if not rows:
        print("[Retriever] 无文档块数据")
        return []

    # 2. 计算相似度并排序
    scored: list[tuple[DocumentChunk, float]] = []
    for row in rows:
        vec = parse_embedding(row.embedding)
        sim = cosine_similarity(query_embedding, vec) if vec else 0.0
        scored.append((row, sim))

    scored.sort(key=lambda item: item[1], reverse=True)
    top = scored[:top_k]

    top_sim = f"{top[0][1]:.4f}" if top else "N/A"
    print(
        f"[Retriever] 余弦相似度搜索 → {len(top)}/{len(rows)} 条 (top={top_sim})"
    )

    return [
        DocChunk(
            id=row.id,
            sourceName=row.sourceName,
            sourceType=row.sourceType,
            chunkIndex=row.chunkIndex,
            content=row.content,
            createdAt=row.createdAt,
        )
        for row, _ in top
    ]
