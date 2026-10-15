# ============================================================
# RAG 评测 · 端到端问答指标
#
# 走真实链路（HTTP → nginx → FastAPI → 模型池 → 流式返回），测用户能感知的指标：
#   · 首 token 延迟（TTFT）与整段完成耗时
#   · 有答案问题的「引用来源」比例
#   · 无答案问题的诚实说明比例（检索查不到时会不会硬编）
#
# 用法（app 容器内，会真实消耗 token）：
#   docker compose run --rm \
#     -v D:/python-checkin/scripts/rag_eval:/eval \
#     -e PYTHONPATH=/app/vendor:/app \
#     app python /eval/eval_e2e.py --limit 20 --out /eval/metrics_e2e.json
# ============================================================

import argparse
import json
import statistics
import time
from pathlib import Path

import requests
from sqlalchemy import select

from app.core.security import create_access_token
from app.db.session import SessionLocal
from app.models.base import User

# 无答案问题里出现这些措辞，视为「诚实说明没查到」而不是硬编
REFUSAL_MARKERS = [
    "没有找到",
    "没找到",
    "未找到",
    "找不到",
    "没有相关",
    "未包含",
    "不包含",
    "没有提及",
    "未提及",
    "知识库中没有",
    "知识库里没有",
    "知识库里没找到",
]

CITATION_MARKERS = ["根据", "来源", "《"]


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def ask(base_url: str, token: str, query: str, timeout: int = 120) -> dict:
    """发一次真实问答，返回 TTFT / 总耗时 / 回答全文"""
    started = time.perf_counter()
    ttft = None
    pieces: list[str] = []

    resp = requests.post(
        f"{base_url}/api/ai",
        json={"messages": [{"role": "user", "content": query}]},
        headers={"Authorization": f"Bearer {token}"},
        stream=True,
        timeout=timeout,
    )
    resp.raise_for_status()

    for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
        if not chunk:
            continue
        if ttft is None:
            ttft = (time.perf_counter() - started) * 1000
        pieces.append(chunk)

    total_ms = (time.perf_counter() - started) * 1000
    return {
        "ttft_ms": round(ttft, 1) if ttft is not None else None,
        "total_ms": round(total_ms, 1),
        "answer": "".join(pieces),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="rag-eval@local")
    parser.add_argument("--questions", default="/eval/questions.jsonl")
    parser.add_argument("--out", default="/eval/metrics_e2e.json")
    parser.add_argument("--base-url", default="http://nginx")
    parser.add_argument("--limit", type=int, default=20, help="有答案问题跑多少条（控制 token 消耗）")
    parser.add_argument("--unanswerable-limit", type=int, default=6)
    parser.add_argument("--tag", default="", help="标记这一轮是优化前还是优化后，例如 before/after")
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == args.email)).scalar_one_or_none()
        if user is None:
            print(f"[E2E] 评测用户不存在：{args.email}")
            raise SystemExit(1)
        token = create_access_token(user.id, user.name, user.email)

    items = [
        json.loads(line)
        for line in Path(args.questions).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    answerable = [i for i in items if i.get("answerable")][: args.limit]
    unanswerable = [i for i in items if not i.get("answerable")][: args.unanswerable_limit]

    records = []
    for label, group in (("answerable", answerable), ("unanswerable", unanswerable)):
        for item in group:
            query = f"从我的知识库文档里查一下：{item['query']}"
            try:
                result = ask(args.base_url, token, query)
            except Exception as err:  # noqa: BLE001
                print(f"[E2E] {item['id']} 请求失败：{err}")
                continue

            answer = result["answer"]
            record = {
                "id": item["id"],
                "kind": label,
                "query": item["query"],
                "ttft_ms": result["ttft_ms"],
                "total_ms": result["total_ms"],
                "cited": any(m in answer for m in CITATION_MARKERS),
                "refused": any(m in answer for m in REFUSAL_MARKERS),
                "answer_len": len(answer),
                "answer_head": answer[:220],
            }
            records.append(record)
            print(
                f"[E2E] {item['id']} {label:<11} ttft={record['ttft_ms']}ms "
                f"total={record['total_ms']}ms 引用={record['cited']} 说明没查到={record['refused']}"
            )

    ttfts = [r["ttft_ms"] for r in records if r["ttft_ms"]]
    totals = [r["total_ms"] for r in records]
    ans = [r for r in records if r["kind"] == "answerable"]
    unans = [r for r in records if r["kind"] == "unanswerable"]

    report = {
        "tag": args.tag,
        "base_url": args.base_url,
        "runs": len(records),
        "ttft_ms": {
            "p50": round(percentile(ttfts, 0.5), 1),
            "p95": round(percentile(ttfts, 0.95), 1),
        },
        "total_ms": {
            "p50": round(percentile(totals, 0.5), 1),
            "p95": round(percentile(totals, 0.95), 1),
        },
        "citation_rate": round(sum(1 for r in ans if r["cited"]) / len(ans), 4) if ans else None,
        "honest_refusal_rate": (
            round(sum(1 for r in unans if r["refused"]) / len(unans), 4) if unans else None
        ),
        "records": records,
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"[E2E] tag={args.tag or '-'} runs={report['runs']} "
        f"TTFT p50={report['ttft_ms']['p50']}ms p95={report['ttft_ms']['p95']}ms | "
        f"引用率={report['citation_rate']} 诚实说明率={report['honest_refusal_rate']}"
    )
    print(f"[E2E] 结果已写入 {out}")


if __name__ == "__main__":
    main()
