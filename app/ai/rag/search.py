# ============================================================
# Day 16 RAG: 高级搜索（召回 + 重排）（对应 src/lib/rag/search.ts）
#
# search_knowledge(query, user_id?)
#   1. query → Embedding
#   2. 召回: 向量相似度 Top-K (默认 20)
#   3. 重排: embedding 模型余弦相似度精排 → Top-N (默认 5)
#   4. 返回格式化结果
# ============================================================

from typing import Any, Optional

from sqlalchemy import func, select

from app.ai.rag.client import embed_text, rerank
from app.ai.rag.retriever import DocChunk, search_similar_chunks
from app.db.session import SessionLocal
from app.models.knowledge import DocumentChunk


# ---- 搜索 ----

def search_knowledge(
    query: str,
    user_id: Optional[str] = None,
    recall_top_k: int = 20,
    final_top_n: int = 5,
    source_filter: Optional[str] = None,
) -> dict:
    """搜索知识库

    :param query:        用户查询文本
    :param user_id:      当前用户 ID（可选）
    :param recall_top_k: 召回阶段取多少条（默认 20）
    :param final_top_n:  最终返回多少条（默认 5）
    :param source_filter: 可选：限定来源
    :return: {"query", "results": [{content, sourceName, score, chunkIndex}], "searchedChunks"}
    """
    print(f'[Search] 查询: "{query[:80]}"' + (f" (user: {user_id})" if user_id else ""))

    # 1. Query → Embedding
    query_embedding = embed_text(query)

    # 2. 召回：向量相似度 Top-K
    recalled = search_similar_chunks(query_embedding, recall_top_k, source_filter, user_id)

    if not recalled:
        print("[Search] 未找到相关结果")
        return {"query": query, "results": [], "searchedChunks": 0}

    # 统计知识库总 chunk 数（仅用于日志，与原 TS 一致）
    with SessionLocal() as db:
        total_chunks = db.execute(select(func.count(DocumentChunk.id))).scalar() or 0

    documents = [c.content for c in recalled]

    # 3. 重排：embedding 模型余弦相似度
    try:
        rr = rerank(query, documents)
        indices = rr["indices"]
        scores = rr["scores"]

        # 按重排分数取 Top-N
        top_indices = indices[:final_top_n]
        reranked: list[DocChunk] = [recalled[idx] for idx in top_indices]

        print(f"[Search] 召回 {len(recalled)}/{total_chunks} → 重排 → Top-{final_top_n}")

        return {
            "query": query,
            "results": [
                {
                    "content": c.content,
                    "sourceName": c.sourceName,
                    "score": scores[i] if i < len(scores) else 0.0,
                    "chunkIndex": c.chunkIndex,
                }
                for i, c in enumerate(reranked)
            ],
            "searchedChunks": total_chunks,
        }
    except Exception as err:  # noqa: BLE001
        # 重排失败时回退到只用相似度排序
        print(f"[Search] Rerank 失败，回退到纯向量排序: {err}")

        return {
            "query": query,
            "results": [
                {
                    "content": c.content,
                    "sourceName": c.sourceName,
                    "score": 0,  # 无重排分数
                    "chunkIndex": c.chunkIndex,
                }
                for c in recalled[:final_top_n]
            ],
            "searchedChunks": total_chunks,
        }


# ---- 格式化 ----

def format_knowledge_for_prompt(results: Any) -> str:
    """将搜索结果格式化为 system prompt 片段

    :param results: search_knowledge 的返回 dict，或其中的 results 列表
    :return: "[参考N]（来源: xxx）\n内容" 形式的 prompt 片段
    """
    items = results.get("results") if isinstance(results, dict) else results
    if not items:
        return ""

    lines = [
        f"[参考{i + 1}] （来源: {r['sourceName']}）\n{r['content']}"
        for i, r in enumerate(items)
    ]

    return "[知识库检索结果 — 请优先基于以下参考资料回答]\n" + "\n\n".join(lines) + "\n"
