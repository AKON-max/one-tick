# ============================================================
# RAG 向量检索
#
# 生产路径 search_similar_chunks：把 Top-K 近邻计算交给数据库
#   —— pgvector 余弦距离算子 `<=>`，由 hnsw 索引（见迁移 0004）加速，
#      只把命中的文本取回应用层。
#
# 另保留旧实现 search_similar_chunks_scan（全量加载 + Python 余弦），
# 仅供 scripts/rag_eval 做优化前后对比，生产代码不再调用。
# ============================================================

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select, text

from app.db.session import SessionLocal
from app.models.knowledge import DocumentChunk

# HNSW 是近似近邻：ef_search 越大召回越高、延迟越高（pgvector 默认 40）。
# 实测（9885 块语料 / 40 条评测问题，见 scripts/rag_eval/sweep_ef.py）：
#   ef=40（默认） recall@20 = 87.5% / P50 1.1ms
#   ef=100        recall@20 = 92.5% / P50 1.4ms   ← 采用
#   精确全扫      recall@20 = 95.0% / P50 24.8ms
# 取 100 的理由：用约 1/18 的延迟换回 5pp 召回；再往上加到 400 只是与精确持平，
# 差异仅 1 条问题（n=40），不足以支撑继续调参，故停在这里。
HNSW_EF_SEARCH = 100


@dataclass
class DocChunk:
    """检索返回的文档块（不含 embedding）"""

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

def _to_doc_chunk(row: DocumentChunk) -> DocChunk:
    return DocChunk(
        id=row.id,
        sourceName=row.sourceName,
        sourceType=row.sourceType,
        chunkIndex=row.chunkIndex,
        content=row.content,
        createdAt=row.createdAt,
    )


def _filters(source_filter: Optional[str], user_id: Optional[str]) -> list:
    conditions = [DocumentChunk.embedding.isnot(None)]
    if user_id:
        conditions.append(DocumentChunk.userId == user_id)
    if source_filter:
        conditions.append(DocumentChunk.sourceName == source_filter)
    return conditions


def search_similar_chunks(
    query_embedding: list[float],
    top_k: int = 5,
    source_filter: Optional[str] = None,
    user_id: Optional[str] = None,
) -> list[DocChunk]:
    """向量语义搜索（数据库侧近邻查询）

    :param query_embedding: 查询向量
    :param top_k:           返回条数（默认 5）
    :param source_filter:   可选：限定来源（sourceName）
    :param user_id:         可选：限定用户
    """
    distance = DocumentChunk.embedding.cosine_distance(query_embedding)
    stmt = (
        select(DocumentChunk)
        .where(*_filters(source_filter, user_id))
        .order_by(distance)
        .limit(top_k)
    )
    with SessionLocal() as db:
        # 只作用于当前事务，不影响连接池里其它查询
        db.execute(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))
        rows = db.execute(stmt).scalars().all()

    print(f"[Retriever] 近邻搜索 → {len(rows)} 条 (k={top_k}, ef_search={HNSW_EF_SEARCH})")
    return [_to_doc_chunk(row) for row in rows]


def search_similar_chunks_scan(
    query_embedding: list[float],
    top_k: int = 5,
    source_filter: Optional[str] = None,
    user_id: Optional[str] = None,
) -> list[DocChunk]:
    """【旧实现，仅供评测对比】全量加载 + Python 内计算余弦相似度

    未加索引时的原始路径。两个已知问题（由 scripts/rag_eval 量化）：
      ① 每次查询都要把最多 1000 条 × 1024 维向量从数据库搬到 Python 解析，
         瓶颈不在算余弦，而在向量的序列化与传输；
      ② limit(1000) 是隐式硬截断：知识库超过 1000 块后，
         更早录入的内容永远进不了候选集，属于召回缺口。
    """
    # 1. 全量加载有 embedding 的文档块（最多取 1000 条，仅供评测对比）
    stmt = (
        select(DocumentChunk)
        .where(*_filters(source_filter, user_id))
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

    return [_to_doc_chunk(row) for row, _ in top]
