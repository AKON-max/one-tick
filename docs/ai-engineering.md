# AI Engineering Notes

## Responsibility split

```text
model_pool.py   provider selection, quota/rate-limit fallback, token accounting
rag/            ingestion, retrieval, reranking, prompt formatting
memory.py       long-term memory extraction, ranking, deduplication, cleanup
agent/          persisted multi-step runs, approvals, reports
tools/          user-scoped business actions exposed to the model
```

## Tool-calling contract

- Every tool is created for one user.
- The model receives JSON tool specifications, not database credentials.
- Tool results are structured dictionaries with `success` and an error or payload.
- A tool exception must not break the complete chat request.
- The tool loop is bounded. The current chat loop allows at most four model rounds.

## Model fallback

The provider chain has three tiers:

| Tier | Intended use |
|---|---|
| HIGH | agent, planning, document analysis |
| LOW | titles, memory extraction, classification |
| EMBEDDING | document and memory vectors |

The pool treats quota exhaustion and rate limiting as expected runtime events:

- 429: cooldown for 60 seconds.
- 403 / insufficient quota: mark unavailable in the current process.
- Ordinary errors: surface them instead of silently changing model.

This is not a distributed gateway. Process-local model state is a known scaling limitation.

## RAG quality rules

- Retrieval and rerank behavior must be measurable.
- Metrics must state corpus size, question count, index parameters, and whether the run is retrieval-only or end-to-end.
- `LIMIT 1000` was a correctness defect, not a tuning result. Do not present it as a simple speed-up.
- HNSW loses recall relative to exact search; quantify the loss instead of claiming exactness.
- Keep source names in the formatted prompt so the model can cite where an answer came from.