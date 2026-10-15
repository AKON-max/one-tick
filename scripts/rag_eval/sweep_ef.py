# ============================================================
# RAG 评测 · hnsw.ef_search 调参实验
#
# 目的：HNSW 是近似近邻索引，ef_search 决定「搜索时探索多少候选」。
#   太小 → 召回掉；太大 → 延迟涨。需要一条「召回 vs 延迟」曲线来选值。
#
# 基准（ground truth）：SET enable_indexscan = off 强制顺序扫描，得到精确 Top-K。
#
# 两个必须做的防污染措施（第一版踩过坑）：
#   ① 每个档位都在**同一个 session** 内先 SET 再 SHOW 读回校验，
#      确认设置真的生效，而不是「以为设了、其实没设」；
#   ② 每档先跑一次 warmup 并丢弃，避免首查的库表预热开销混进分位数。
#
# 用法：
#   docker compose run --rm \
#     -v D:/python-checkin/scripts/rag_eval:/eval \
#     -e PYTHONPATH=/app/vendor:/app \
#     app python /eval/sweep_ef.py
# ============================================================

import argparse
import json
import statistics
import time
from pathlib import Path

from sqlalchemy import text

from app.ai.rag.client import embed_text
from app.db.session import SessionLocal

EF_VALUES = [1, 10, 40, 100, 200, 400]
K_FINAL = 5
K_RECALL = 20

SEARCH_SQL = (
    'SELECT id FROM documentchunk WHERE "userId" = :uid '
    "AND embedding IS NOT NULL "
    "ORDER BY embedding <=> CAST(:vec AS vector) LIMIT :k"
)


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def load_vectors(path: Path, questions: list[dict]) -> dict[str, list[float]]:
    """查询向量缓存：embedding 是付费 API 调用，重复实验不该重复花钱"""
    cache = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    missing = [q for q in questions if q["id"] not in cache]
    if missing:
        print(f"[ef-sweep] 需要新算 {len(missing)} 条 query 向量")
        for q in missing:
            cache[q["id"]] = embed_text(q["query"])
        path.write_text(json.dumps(cache), encoding="utf-8")
    return cache


def literal_of(vector: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in vector) + "]"


def search(db, user_id: str, vector: list[float], k: int) -> tuple[list[str], float]:
    started = time.perf_counter()
    rows = db.execute(
        text(SEARCH_SQL), {"uid": user_id, "vec": literal_of(vector), "k": k}
    ).all()
    return [r[0] for r in rows], (time.perf_counter() - started) * 1000


def measure(db, questions: list[dict], vectors, user_id: str) -> tuple[list[list[str]], list[float]]:
    """跑完一轮问题，返回 (每题的命中 id 列表, 每题耗时 ms)"""
    results: list[list[str]] = []
    latencies: list[float] = []
    warmup_done = False
    for item in questions:
        ids, ms = search(db, user_id, vectors[item["id"]], K_RECALL)
        if warmup_done:
            results.append(ids)
            latencies.append(ms)
        else:
            # 首查含预热开销，结果照收、耗时丢弃
            warmup_done = True
            results.append(ids)
    return results, latencies


def score(hits: list[list[str]], questions: list[dict]) -> dict:
    n = len(questions)
    h5 = sum(1 for ids, q in zip(hits, questions) if q["goldChunkId"] in ids[:K_FINAL])
    r20 = sum(1 for ids, q in zip(hits, questions) if q["goldChunkId"] in ids)
    return {"hit@5": round(h5 / n, 4), "recall@20": round(r20 / n, 4)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="rag-eval@local")
    parser.add_argument("--questions", default="/eval/questions.jsonl")
    parser.add_argument("--vectors", default="/eval/qvec.json")
    parser.add_argument("--out", default="/eval/metrics_ef_sweep.json")
    args = parser.parse_args()

    with SessionLocal() as db:
        row = db.execute(
            text('SELECT id FROM "user" WHERE email = :e'), {"e": args.email}
        ).first()
        if row is None:
            print(f"[ef-sweep] 评测用户不存在：{args.email}")
            raise SystemExit(1)
        user_id = row[0]

    items = [
        json.loads(line)
        for line in Path(args.questions).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    answerable = [i for i in items if i.get("answerable")]
    vectors = load_vectors(Path(args.vectors), answerable)

    sweep: list[dict] = []

    # ---- 基准：强制顺序扫描 = 精确 Top-K ----
    with SessionLocal() as db:
        db.execute(text("SET enable_indexscan = off"))
        verified = db.execute(text("SHOW enable_indexscan")).scalar()
        print(f"[ef-sweep] 基准档 enter，enable_indexscan={verified}（应为 off）")
        exact_hits, exact_lat = measure(db, answerable, vectors, user_id)
    exact_score = score(exact_hits, answerable)
    sweep.append(
        {
            "ef_search": "exact (enable_indexscan=off，顺序扫描)",
            **exact_score,
            "latency_ms": {"p50": round(percentile(exact_lat, 0.5), 1)},
        }
    )
    print(f"[ef-sweep] exact  hit@5={exact_score['hit@5']:.3f} recall@20={exact_score['recall@20']:.3f} "
          f"p50={percentile(exact_lat, 0.5):.1f}ms")

    # ---- 各档 ef_search（session 级 SET + 读回校验）----
    # 关键：必须 SET enable_seqscan = off。
    # 实测发现 ef_search 偏小时（LIMIT 5 → ef<40、LIMIT 20 → ef<100），
    # PostgreSQL 的代价模型会放弃 HNSW 索引、退化成全表顺序扫描，
    # 于是「低 ef 档」量到的其实是精确结果（延迟也变成 ~25ms）。
    # 那是小表（9885 行）特有的规划器行为，不是 HNSW 的真实表现。
    # 强制走索引，才能得到干净的「ef_search ↔ 召回/延迟」关系。
    with SessionLocal() as db:
        db.execute(text("SET enable_seqscan = off"))
        for ef in EF_VALUES:
            db.execute(text(f"SET hnsw.ef_search = {ef}"))
            actual = int(db.execute(text("SHOW hnsw.ef_search")).scalar())
            if actual != ef:
                raise RuntimeError(f"ef_search 设置未生效：期望 {ef}，实际 {actual}")
            hits, lat = measure(db, answerable, vectors, user_id)
            s = score(hits, answerable)
            agree = sum(
                1
                for ids, gold_ids, q in zip(hits, exact_hits, answerable)
                if q["goldChunkId"] in ids and q["goldChunkId"] in gold_ids
            )
            sweep.append(
                {
                    "ef_search": ef,
                    **s,
                    "agree_with_exact@20": round(agree / len(answerable), 4),
                    "latency_ms": {
                        "p50": round(percentile(lat, 0.5), 1),
                        "p95": round(percentile(lat, 0.95), 1),
                    },
                }
            )
            print(f"[ef-sweep] ef={ef:<4} hit@5={s['hit@5']:.3f} recall@20={s['recall@20']:.3f} "
                  f"p50={percentile(lat, 0.5):.1f}ms p95={percentile(lat, 0.95):.1f}ms")

    report = {
        "questions": len(answerable),
        "k_final": K_FINAL,
        "k_recall": K_RECALL,
        "note": "exact 用 enable_indexscan=off 顺序扫描作 ground truth；各档 ef 均读回校验生效",
        "sweep": sweep,
        "exact_latency_mean_ms": round(statistics.fmean(exact_lat), 1),
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ef-sweep] 结果已写入 {args.out}")


if __name__ == "__main__":
    main()
