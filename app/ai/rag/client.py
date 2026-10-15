# ============================================================
# Embedding 服务客户端 — 对接 OpenAI 兼容 Embedding API
#
#
# 走模型池 embedding 档（text-embedding-v4 优先，v2 兜底），
# 不计入用户 token 精力条。自动分批，每批最多 10 条
# （DashScope text-embedding-v4 单次 batch 上限为 10）。
# ============================================================

from typing import Any

from app.ai.model_pool import embedding_with_fallback
from app.ai.rag.retriever import cosine_similarity

BATCH_SIZE = 10


def embed_texts(texts: list[str]) -> list[list[float]]:
    """批量文本 → 向量

    :param texts: 文本列表
    :return: 与输入顺序一致的向量列表
    """
    if not texts:
        return []

    # 小批量直接请求
    if len(texts) <= BATCH_SIZE:
        data, _model = embedding_with_fallback(texts)
        return data

    # 大批量分批请求
    print(f"[Embed] 分批: {len(texts)} 条 → {(len(texts) + BATCH_SIZE - 1) // BATCH_SIZE} 批")
    all_results: list[tuple[int, list[float]]] = []
    offset = 0

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        data, _model = embedding_with_fallback(batch)
        # 恢复全局 index
        for j, emb in enumerate(data):
            all_results.append((offset + j, emb))
        offset += len(batch)

    all_results.sort(key=lambda item: item[0])
    return [emb for _, emb in all_results]


def embed_text(text: str) -> list[float]:
    """单条文本 → 向量"""
    results = embed_texts([text])
    return results[0]


# ---- Rerank（本地余弦相似度，无需远程服务）----

def rerank(query: str, documents: list[str]) -> dict[str, Any]:
    """Rerank：对候选文档按与 query 的余弦相似度重新排序

    ① query → embedding
    ② 每个文档 → embedding
    ③ 计算 cosineSimilarity → 排序

    对于个人知识库（几百条 chunk），这个性能完全够用。

    :param query:     用户查询文本
    :param documents: 候选文档文本列表
    :return: 按相似度降序排列 {"scores": [...], "indices": [...]}
    """
    if not documents:
        return {"scores": [], "indices": []}

    # query + documents 一起 embedding（embed_texts 内部自动分批）
    all_texts = [query, *documents]
    all_vectors = embed_texts(all_texts)
    query_vec = all_vectors[0]
    doc_vecs = all_vectors[1:]

    # 计算余弦相似度并按分数降序
    scored = sorted(
        ((i, cosine_similarity(query_vec, vec)) for i, vec in enumerate(doc_vecs)),
        key=lambda item: item[1],
        reverse=True,
    )

    return {
        "scores": [s for _, s in scored],
        "indices": [i for i, _ in scored],
    }
