# ============================================================
# RAG 评测 · 评测集构建
#
# 从评测语料里分层抽样 chunk（每个来源最多取一块，保证覆盖面），
# 让 LLM 为每块生成一个「只能靠它回答」的问题，gold 标为该 chunk。
# 另生成一批语料不可能覆盖的「无答案问题」，用来测检索的区分度
# （而非模型拒答 —— 拒答在端到端评测里看）。
#
# 产物 questions.jsonl，每行：
#   {"id","query","answerable":true,"goldChunkId","goldSource","goldContent"}
#   {"id","query","answerable":false}
#
# 两个工程处理（都是被真实限流打出来的）：
#   ① 批量出题：一次请求生成 5 题，把请求数压到 1/5，绕开 429 冷却；
#   ② 逐题落盘 + 按 goldChunkId 续跑：中途被打断不用从头再来。
#
# 用法（app 容器内）：
#   docker compose run --rm \
#     -v D:/python-checkin/scripts/rag_eval:/eval \
#     -e PYTHONPATH=/app/vendor:/app \
#     app python /eval/build_questions.py --count 40 --unanswerable 10
# ============================================================

import argparse
import json
import random
import re
import time
from pathlib import Path

from sqlalchemy import select

from app.ai.model_pool import completions_with_fallback
from app.db.session import SessionLocal
from app.models.base import User
from app.models.knowledge import DocumentChunk

SEED = 42
BATCH_SIZE = 5

BATCH_PROMPT = """下面有 {n} 段学习资料，编号依次为 1 到 {n}。

请为每一段写一个**只能靠这一段回答**的问题。

要求：
1. 用学习者会用的自然语言提问，可以保留必要的术语，但不要整句照抄原文；
2. 问题要具体、有唯一答案，不要问「这段话讲了什么」这类泛泛的问题；
3. 输出格式严格为每行一条：编号|问题，编号与资料编号一一对应；
4. 不要输出答案，不要加解释、编号说明或多余空行。

{blocks}"""

UNANSWERABLE_PROMPT = """请生成 {n} 个关于「{topic}」的问题。

要求：
1. 问题要具体、像真实用户会去查资料的那种问法；
2. 不要涉及编程、Python、Web 开发、数据库等软件话题；
3. 每行一个问题，不要编号，不要任何解释。"""

# 与「Python 学习资料」语料刻意错开的领域，保证语料里查不到答案
UNANSWERABLE_TOPICS = [
    "深海地质勘探设备的制造工艺",
    "十七世纪荷兰郁金香期货市场的交割规则",
]


def llm(prompt: str, temperature: float = 0.3) -> str:
    """低频档模型跑生成任务（评测集构建不需要强模型）"""

    def call(entry, client):
        return client.chat.completions.create(
            model=entry.modelName,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )

    resp, _model = completions_with_fallback("low", call)
    return (resp.choices[0].message.content or "").strip()


def usable(chunk: DocumentChunk) -> bool:
    """挑适合出概念题的块：太短的没信息量，代码块/表格为主的不适合问概念"""
    text = chunk.content
    if len(text) < 200:
        return False
    if text.count("```") > 2:
        return False
    if text.count("|") > 20:
        return False
    return True


def parse_batch(raw: str, size: int) -> dict[int, str]:
    """解析「编号|问题」批量输出；编号不是 1..size 的丢弃"""
    out: dict[int, str] = {}
    for line in raw.splitlines():
        line = line.strip().lstrip("-* ").strip()
        if not line or "|" not in line:
            continue
        head, _, question = line.partition("|")
        digits = re.sub(r"\D", "", head)
        if not digits:
            continue
        idx = int(digits)
        question = question.strip()
        if 1 <= idx <= size and len(question) >= 8:
            out[idx] = question
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="rag-eval@local")
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--unanswerable", type=int, default=10)
    parser.add_argument("--out", default="/eval/questions.jsonl")
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.execute(select(User).where(User.email == args.email)).scalar_one_or_none()
        if user is None:
            print(f"[Build] 评测用户不存在：{args.email}（先跑 ingest.py）")
            raise SystemExit(1)
        rows = (
            db.execute(
                select(DocumentChunk)
                .where(DocumentChunk.userId == user.id)
                .order_by(DocumentChunk.sourceName, DocumentChunk.chunkIndex)
            )
            .scalars()
            .all()
        )

    by_source: dict[str, list[DocumentChunk]] = {}
    for row in rows:
        if usable(row):
            by_source.setdefault(row.sourceName, []).append(row)

    sources = sorted(by_source)
    random.seed(SEED)
    random.shuffle(sources)

    picked: list[DocumentChunk] = []
    for source in sources:
        if len(picked) >= args.count:
            break
        picked.append(random.choice(by_source[source]))

    print(f"[Build] 语料 {len(rows)} 块 / 可用来源 {len(sources)} 个 → 抽样 {len(picked)} 块出题")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 逐题落盘：生成 40 条要发几十次 LLM 请求，中途被打断不能从头再来
    items: list[dict] = []
    done_ids: set[str] = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            existing = json.loads(line)
            items.append(existing)
            if existing.get("goldChunkId"):
                done_ids.add(existing["goldChunkId"])
        print(f"[Build] 断点续跑：已有 {len(items)} 条，跳过已出题的 {len(done_ids)} 块")

    started = time.time()
    pending = [c for c in picked if c.id not in done_ids]

    with out.open("a", encoding="utf-8") as fh:
        for start in range(0, len(pending), BATCH_SIZE):
            batch = pending[start : start + BATCH_SIZE]
            blocks = "\n\n".join(
                f"[{i}]\n{chunk.content[:900]}" for i, chunk in enumerate(batch, 1)
            )
            raw = llm(BATCH_PROMPT.format(n=len(batch), blocks=blocks))
            parsed = parse_batch(raw, len(batch))

            for i, chunk in enumerate(batch, 1):
                question = parsed.get(i)
                if not question:
                    print(f"[Build] 批次 {start // BATCH_SIZE + 1} 第 {i} 条缺失，跳过")
                    continue
                item = {
                    "id": f"q{len(items) + 1:02d}",
                    "query": question,
                    "answerable": True,
                    "goldChunkId": chunk.id,
                    "goldSource": chunk.sourceName,
                    "goldContent": chunk.content[:160],
                }
                items.append(item)
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")
                fh.flush()
                print(f"[Build] {len(items)}/{len(picked)} [{chunk.sourceName}] → {question}")

        # 无答案问题：测检索在语料覆盖不到时的区分度
        if not any(not it.get("answerable") for it in items):
            per_topic = max(1, args.unanswerable // len(UNANSWERABLE_TOPICS))
            for topic in UNANSWERABLE_TOPICS:
                raw = llm(UNANSWERABLE_PROMPT.format(n=per_topic, topic=topic), temperature=0.8)
                for line in raw.splitlines():
                    line = line.strip().lstrip("0123456789.、) ").strip()
                    if len(line) < 8:
                        continue
                    item = {"id": f"u{len(items):03d}", "query": line, "answerable": False}
                    items.append(item)
                    fh.write(json.dumps(item, ensure_ascii=False) + "\n")
                    fh.flush()

    answerable = sum(1 for i in items if i["answerable"])
    print(
        f"[Build] 完成：{len(items)} 条（有答案 {answerable} / 无答案 {len(items) - answerable}）"
        f" / 耗时 {time.time() - started:.1f}s → {out}"
    )


if __name__ == "__main__":
    main()
