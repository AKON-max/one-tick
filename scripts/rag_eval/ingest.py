# ============================================================
# RAG 评测 · 语料灌库
#
# 把一批 Markdown 语料切片、向量化，写入一个**独立评测用户**名下，
# 与正式数据完全隔离；评测结束后由 teardown.py 整体删除。
#
# 用法（在 app 容器内执行，无需重建镜像）：
#   docker compose run --rm \
#     -v D:/rag-corpus:/corpus \
#     -v D:/one-tick/scripts/rag_eval:/eval \
#     -e PYTHONPATH=/app/vendor:/app \
#     app python /eval/ingest.py /corpus --reset
#
# 参数：
#   corpus_dir      语料根目录（递归查找 *.md / *.markdown）
#   --email         评测用户邮箱（默认 rag-eval@local）
#   --max-chunks    最多灌入多少个 chunk（0 表示不限）
#   --reset         先清空该用户已有的知识库数据
# ============================================================

import argparse
import sys
import time
from pathlib import Path

from sqlalchemy import delete, select

from app.ai.rag.chunk import split_markdown
from app.ai.rag.client import embed_texts
from app.db.session import SessionLocal
from app.models.base import User
from app.models.knowledge import DocumentChunk, KnowledgeDoc

# 语料目录里常见的非正文路径
EXCLUDE_DIRS = {".git", ".github", "node_modules", "images", "image", "res", "assets", "static"}


def find_docs(root: Path) -> list[Path]:
    """递归找出所有 Markdown 文件（按路径排序，保证多次灌库顺序一致）"""
    docs: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in (".md", ".markdown"):
            continue
        parts = path.relative_to(root).parts
        if any(part in EXCLUDE_DIRS for part in parts):
            continue
        docs.append(path)
    return docs


def get_or_create_user(db, email: str) -> User:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user:
        return user
    user = User(name="RAG 评测语料", email=email, emailVerified=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def ingested_sources(db, user_id: str) -> set[str]:
    """已灌过的来源（灌库要发几百次 embedding 请求，中途被打断后需要能续跑）"""
    return set(
        db.execute(
            select(KnowledgeDoc.sourceName).where(KnowledgeDoc.userId == user_id)
        ).scalars().all()
    )


def reset_user_data(db, user_id: str) -> None:
    db.execute(delete(DocumentChunk).where(DocumentChunk.userId == user_id))
    db.execute(delete(KnowledgeDoc).where(KnowledgeDoc.userId == user_id))
    db.commit()


def embed_with_retry(texts: list[str], attempts: int = 3) -> list[list[float]]:
    """embedding 带退避重试：灌库要发几百次请求，偶发网络抖动不该中断整轮"""
    last_err: Exception | None = None
    for i in range(attempts):
        try:
            return embed_texts(texts)
        except Exception as err:  # noqa: BLE001
            last_err = err
            wait = 2 ** i
            print(f"[Ingest] embedding 失败（{i + 1}/{attempts}）：{err}；{wait}s 后重试")
            time.sleep(wait)
    raise last_err  # type: ignore[misc]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("corpus_dir")
    parser.add_argument("--email", default="rag-eval@local")
    parser.add_argument("--max-chunks", type=int, default=0)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()

    root = Path(args.corpus_dir)
    if not root.is_dir():
        print(f"[Ingest] 语料目录不存在：{root}")
        sys.exit(1)

    docs = find_docs(root)
    print(f"[Ingest] 找到 {len(docs)} 个 Markdown 文件")

    with SessionLocal() as db:
        user = get_or_create_user(db, args.email)
        if args.reset:
            reset_user_data(db, user.id)
            print("[Ingest] 已清空该用户既有知识库数据")

        done = ingested_sources(db, user.id)
        if done:
            print(f"[Ingest] 断点续跑：跳过已入库的 {len(done)} 个来源")

        total = 0
        started = time.time()

        for idx, path in enumerate(docs, 1):
            text = path.read_text(encoding="utf-8", errors="ignore")
            chunks = split_markdown(text)
            if not chunks:
                continue

            if args.max_chunks:
                remain = args.max_chunks - total
                if remain <= 0:
                    break
                chunks = chunks[:remain]

            source_name = str(path.relative_to(root)).replace("\\", "/")
            if source_name in done:
                continue
            vectors = embed_with_retry(chunks)

            db.add(
                KnowledgeDoc(
                    userId=user.id,
                    sourceName=source_name,
                    sourceType="markdown",
                    content=text,
                )
            )
            for i, (content, vec) in enumerate(zip(chunks, vectors)):
                db.add(
                    DocumentChunk(
                        userId=user.id,
                        sourceName=source_name,
                        sourceType="markdown",
                        chunkIndex=i,
                        content=content,
                        embedding=vec,
                    )
                )
            db.commit()

            total += len(chunks)
            print(f"[Ingest] {idx}/{len(docs)} {source_name} → {len(chunks)} chunks（累计 {total}）")

        print(
            f"[Ingest] 完成：{len(docs)} 文件 / {total} chunks / "
            f"耗时 {time.time() - started:.1f}s / 评测用户 {args.email} ({user.id})"
        )


if __name__ == "__main__":
    main()
