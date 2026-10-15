# Testing and Verification

## Current test layers

| Layer | Location | Purpose |
|---|---|---|
| Unit | `tests/` | Pure contracts: chunking, plan sync, security helpers, feature constants |
| Evaluation | `scripts/rag_eval/` | Retrieval quality, index sweeps, end-to-end behavior |
| Manual smoke | `scripts/test_*.py` | Legacy endpoint checks kept for local development |

## Commands

```bash
python -m compileall -q app
python -m unittest discover -s tests -v
```

Frontend:

```bash
cd frontend
npm run typecheck
npm run lint
```

## Evaluation discipline

When changing retrieval behavior, record:

1. Corpus and chunk count.
2. Question set and whether negative questions are included.
3. Index and `ef_search` settings.
4. Hit/Recall/MRR or the metric actually used.
5. Latency distribution and whether it is retrieval-only or end-to-end.
6. Known limitations and any measurement mistakes.

The RAG evaluation log is the reference example: [`scripts/rag_eval/RAG_EVAL.md`](../scripts/rag_eval/RAG_EVAL.md).

## Not covered yet

- No database integration test suite.
- No automated browser E2E suite.
- No provider-mock contract test for every model tier.
- No CI/CD deployment pipeline.