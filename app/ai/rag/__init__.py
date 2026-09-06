# ============================================================
# Day 16 RAG: 统一导出（对应 src/lib/rag/index.ts）
# ============================================================

from app.ai.rag.chunk import split_markdown, split_text
from app.ai.rag.client import embed_text, embed_texts, rerank
from app.ai.rag.retriever import (
    DocChunk,
    cosine_similarity,
    parse_embedding,
    search_similar_chunks,
)
from app.ai.rag.search import format_knowledge_for_prompt, search_knowledge

__all__ = [
    # chunk
    "split_text",
    "split_markdown",
    # retriever
    "cosine_similarity",
    "parse_embedding",
    "search_similar_chunks",
    "DocChunk",
    # client
    "embed_texts",
    "embed_text",
    "rerank",
    # search
    "search_knowledge",
    "format_knowledge_for_prompt",
]
