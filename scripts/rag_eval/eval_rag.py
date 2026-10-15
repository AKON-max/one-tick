# ============================================================
# RAG 评测 · 检索层指标
#
# 对同一份语料、同一套问题，分别跑两条检索路径：
#   scan = 旧实现（全量搬运到 Python + 隐式 limit(1000) 截断）
#   sql  = 新实现（pgvector 余弦距离 + hnsw 索引，数据库侧 Top-K）
# 输出：Hit@5 / Recall@20 / MRR@5 / 延迟分位 / 无答案问题的最高相似度。
#
# 用法（app 容器内，只跑检索、不调 LLM，秒级出结果）：
#   docker compose run --rm \
#     -v D:/python-checkin/scripts/rag_eval:/eval \
#     -e PYTHONPATH=/app/vendor:/app \
#     app python /eval/eval_rag.py --out /eval/metrics.json
#
#   # 追加语料规模扫描（看两条路径随数据量的增长曲线）：
#   ... app python /eval/eval_rag.py --sweep
# ============================================================

import argparse
import json
import statistics
import time
from pathlib import Path

from sqlalchemy import select, text

from app.ai.rag.client import embed_text
from app.ai.rag.retriever import search_similar_chunks, search_similar_chunks_scan
from app.db.session import SessionLocal
from app.models.base import User
from app.models.knowledge import DocumentChunk

K_FINAL = 5
K_RECALL = 20

SWEEP_SIZES = [100, 250, 500, 1000, 2000, 0]  # 0 = 全量


def percentile(values: list[float], p: float) -> float:
    """线性插值分位数（样本少时比 statistics.quantiles 更稳）"""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def timeit(fn):
    """返回 (结果, 毫秒)"""
    started = time.perf_counter()
    result = fn()
    return result, (time.perf_counter() - started) * 1000


def hit_rank(ids: list[str], gold: str) -> int:
    """gold 在结果里的名次（1 起）；未命中返回 0"""
    try:
        return ids.index(gold) + 1
    except ValueError:
        return 0


def top1_similarity(vector: list[float], user_id: str) -> float:
    """最高余弦相似度（1 - 余弦距离），用于观察「无答案问题」的分数分布"""
    distance = DocumentChunk.embedding.cosine_distance(vector)
    stmt = (
        select(distance)
        .where(DocumentChunk.userId == user_id, DocumentChunk.embedding.isnot(None))
        .order_by(distance)
        .limit(1)
    )
    with SessionLocal() as db:
        row = db.execute(stmt).first()
    return 1.0 - float(row[0]) if row and row[0] is not None else 0.0


def evaluate_path(name: str, runner, questions: list[dict], user_id: str) -> dict:
    hits5 = []
    hits20 = []
    rr = []
    latencies = []
    misses = []

    for item in questions:
        # user_id 必须走关键字：第三个位置参数是 source_filter
        chunks, ms = timeit(lambda: runner(item["_vector"], K_RECALL, user_id=user_id))
        latencies.append(ms)

        ids = [c.id for c in chunks]
        gold = item["goldChunkId"]

        rank20 = hit_rank(ids, gold)
        rank5 = hit_rank(ids[:K_FINAL], gold)
        hits20.append(1 if rank20 else 0)
        hits5.append(1 if rank5 else 0)
        rr.append(1.0 / rank5 if rank5 else 0.0)

        if not rank5:
            misses.append(
                {
                    "id": item["id"],
                    "query": item["query"],
                    "goldSource": item["goldSource"],
                    "goldRank": rank20,
                }
            )

    total = len(questions)
    return {
        "path": name,
        "questions": total,
        f"hit@{K_FINAL}": round(sum(hits5) / total, 4) if total else 0.0,
        f"recall@{K_RECALL}": round(sum(hits20) / total, 4) if total else 0.0,
        f"mrr@{K_FINAL}": round(sum(rr) / total, 4) if total else 0.0,
        "latency_ms": {
            "p50": round(percentile(latencies, 0.5), 1),
            "p95": round(percentile(latencies, 0.95), 1),
            "mean": round(statistics.fmean(latencies), 1) if latencies else 0.0,
            "max": round(max(latencies), 1) if latencies else 0.0,
        },
        "misses": misses,
    }


def sweep(user_id: str) -> list[dict]:
    """语料规模扫描：分别测「把向量搬回应用层」与「数据库侧 Top-K」的耗时"""
    vector = embed_text("Python 里怎么读写文件")
    literal = "[" + ",".join(f"{v:.6f}" for v in vector) + "]"

    rows = []
    with SessionLocal() as db:
        total = db.execute(
            select(DocumentChunk.id).where(DocumentChunk.userId == user_id)
        ).scalars().all()
    total_n = len(total)

    for size in SWEEP_SIZES:
        n = total_n if size == 0 else min(size, total_n)
        with SessionLocal() as db:
            _, scan_ms = timeit(
                lambda: db.execute(
                    text(
                        'SELECT * FROM documentchunk WHERE "userId" = :uid '
                        "AND embedding IS NOT NULL LIMIT :n"
                    ),
                    {"uid": user_id, "n": n},
                ).all()
            )
            _, sql_ms = timeit(
                lambda: db.execute(
                    text(
                        'SELECT id FROM documentchunk WHERE "userId" = :uid '
                        "AND embedding IS NOT NULL "
                        "ORDER BY embedding <=> CAST(:vec AS vector) LIMIT 5"
                    ),
                    {"uid": user_id, "vec": literal},
                ).all()
            )
        rows.append({"chunks": n, "scan_ms": round(scan_ms, 1), "sql_ms": round(sql_ms, 1)})
        print(f"[Eval] sweep n={n:>5}  scan={scan_ms:8.1f}ms  sql={sql_ms:7.1f}ms")
    return rows


def hnsw_index_exists() -> bool:
    """报告里标注本次测的是「有索引」还是「无索引」，避免数字脱离前提"""
    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT 1 FROM pg_indexes WHERE tablename = 'documentchunk' "
                "AND indexname = 'ix_docchunk_embedding_hnsw'"
            )
        ).first()
    return row is not None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="rag-eval@local")
    parser.add_argument("--questions", default="/eval/questions.jsonl")
    parser.add_argument("--out", default="/eval/metrics.json")
    parser.add_argument("--paths", default="scan,sql", help="跑哪几条路径：scan,sql")
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args()

    selected = {p.strip() for p in args.paths.split(",") if p.strip()}

    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == args.email)).scalar_one_or_none()
        if user is None:
            print(f"[Eval] 评测用户不存在：{args.email}")
            raise SystemExit(1)
        chunk_count = len(
            db.execute(
                select(DocumentChunk.id).where(DocumentChunk.userId == user.id)
            ).scalars().all()
        )

    items = [json.loads(line) for line in Path(args.questions).read_text(encoding="utf-8").splitlines() if line.strip()]
    answerable = [i for i in items if i.get("answerable")]
    unanswerable = [i for i in items if not i.get("answerable")]

    print(f"[Eval] 语料 {chunk_count} 块 / 问题 {len(items)} 条（有答案 {len(answerable)}、无答案 {len(unanswerable)}）")

    # query 向量只算一次，两条路径共用（两条路径的差异只应在检索本身）
    for item in answerable + unanswerable:
        item["_vector"] = embed_text(item["query"])

    report: dict = {
        "corpus_chunks": chunk_count,
        "question_count": len(items),
        "answerable_count": len(answerable),
        "unanswerable_count": len(unanswerable),
        "hnsw_index": hnsw_index_exists(),
        "k_final": K_FINAL,
        "k_recall": K_RECALL,
        "paths": [],
    }
    if "scan" in selected:
        report["paths"].append(
            evaluate_path("scan", search_similar_chunks_scan, answerable, user.id)
        )
    if "sql" in selected:
        report["paths"].append(
            evaluate_path("sql", search_similar_chunks, answerable, user.id)
        )

    # 无答案问题：看最高相似度落在什么区间（用于判断能否用阈值触发拒答）
    if unanswerable:
        scores = [top1_similarity(i["_vector"], user.id) for i in unanswerable]
        report["unanswerable_top1_similarity"] = {
            "mean": round(statistics.fmean(scores), 4),
            "max": round(max(scores), 4),
            "min": round(min(scores), 4),
        }
        # 有答案问题的最高相似度作为对照
        gold_scores = [top1_similarity(i["_vector"], user.id) for i in answerable]
        report["answerable_top1_similarity"] = {
            "mean": round(statistics.fmean(gold_scores), 4),
            "min": round(min(gold_scores), 4),
        }

    if args.sweep:
        report["sweep"] = sweep(user.id)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for path in report["paths"]:
        print(
            f"[Eval] {path['path']:>4}  hit@5={path['hit@5']:.3f} "
            f"recall@20={path['recall@20']:.3f} mrr@5={path['mrr@5']:.3f} "
            f"p50={path['latency_ms']['p50']}ms p95={path['latency_ms']['p95']}ms"
        )
    print(f"[Eval] 结果已写入 {out}")


if __name__ == "__main__":
    main()
