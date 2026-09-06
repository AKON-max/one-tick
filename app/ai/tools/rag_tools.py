# ============================================================
# RAG 工具（对应 src/lib/tools/rag-tools.ts）
# searchKnowledgeBase — 仅搜索当前用户上传的文档
# ============================================================

from app.ai.rag.search import search_knowledge
from app.ai.tools.utils import safe_execute


def create_rag_tool(user_id: str) -> dict:
    """创建针对特定用户的 RAG 搜索工具"""

    def search_knowledge_base(args: dict):
        """搜索用户个人知识库（其上传的文档/资料）。用户询问自己的文档内容时用。"""
        query = args.get("query", "")

        def _run():
            print(f"[RAG Tool] 用户 {user_id} 搜索知识库: {query[:80]}")
            result = search_knowledge(query, user_id)

            if not result["results"]:
                return {
                    "success": True,
                    "query": result["query"],
                    "found": False,
                    "message": "知识库中未找到与你的问题相关的内容。",
                    "results": [],
                }

            print(
                f"[RAG Tool] ✅ 找到 {len(result['results'])} 条结果 "
                f"(搜索了 {result['searchedChunks']} 个文档块)"
            )
            return {
                "success": True,
                "query": result["query"],
                "found": True,
                "count": len(result["results"]),
                "searchedChunks": result["searchedChunks"],
                "message": f"从知识库中找到了 {len(result['results'])} 条相关内容",
                "results": [
                    {
                        "content": r["content"],
                        "source": r["sourceName"],
                        "relevanceScore": round(r["score"], 2),
                    }
                    for r in result["results"]
                ],
            }

        return safe_execute("searchKnowledge", _run)

    return {"searchKnowledgeBase": search_knowledge_base}
