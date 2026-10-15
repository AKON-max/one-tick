# ============================================================
# RAG 评测 · 数据清理
#
# 评测数据全部挂在独立评测用户名下，跑完直接删掉，不碰正式数据。
# 先显式删知识库两张表（DocumentChunk / KnowledgeDoc），再删用户本体，
# 其余关联表（会话、记忆、用量等）由 ON DELETE CASCADE 兜底。
#
# 用法（app 容器内）：
#   docker compose run --rm -v D:/python-checkin/scripts/rag_eval:/eval \
#     -e PYTHONPATH=/app/vendor:/app app python /eval/teardown.py
# ============================================================

import argparse

from sqlalchemy import delete, func, select

from app.db.session import SessionLocal
from app.models.base import User
from app.models.knowledge import DocumentChunk, KnowledgeDoc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="rag-eval@local")
    parser.add_argument("--yes", action="store_true", help="确认执行删除")
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == args.email)).scalar_one_or_none()
        if user is None:
            print(f"[Teardown] 用户不存在，无需清理：{args.email}")
            return

        chunks = db.execute(
            select(func.count(DocumentChunk.id)).where(DocumentChunk.userId == user.id)
        ).scalar() or 0
        docs = db.execute(
            select(func.count(KnowledgeDoc.id)).where(KnowledgeDoc.userId == user.id)
        ).scalar() or 0
        print(f"[Teardown] 待清理：{chunks} 个 chunk / {docs} 篇文档（用户 {args.email}）")

        if not args.yes:
            print("[Teardown] 未加 --yes，仅预演，不做删除")
            return

        db.execute(delete(DocumentChunk).where(DocumentChunk.userId == user.id))
        db.execute(delete(KnowledgeDoc).where(KnowledgeDoc.userId == user.id))
        db.commit()

        db.delete(user)  # 其余关联数据走 ON DELETE CASCADE
        db.commit()
        print(f"[Teardown] 已删除评测用户及其全部数据：{args.email}")


if __name__ == "__main__":
    main()
