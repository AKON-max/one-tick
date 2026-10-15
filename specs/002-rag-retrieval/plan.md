# Technical Plan: RAG Retrieval

## Affected modules

- `app/routers/knowledge.py`
- `app/ai/rag/chunk.py`
- `app/ai/rag/client.py`
- `app/ai/rag/retriever.py`
- `app/ai/rag/search.py`
- `app/ai/tools/rag_tools.py`
- `alembic/versions/0004_rag_vector_index.py`
- `scripts/rag_eval/`

## Approach

Text extraction happens in the router. Chunking is pure Python. Embeddings go through the model pool. `DocumentChunk` stores vectors in PostgreSQL; HNSW accelerates cosine distance queries. The search layer adds a local cosine rerank because the candidate set is small.

## Contracts

- `DocumentChunk.embedding`: `Vector(1024)`, nullable during failure or legacy ingest.
- HNSW index: `vector_cosine_ops`, `m=16`, `ef_construction=64`, query `ef_search=100`.
- Search result: `content`, `sourceName`, `score`, `chunkIndex`.
- Prompt format: `[参考N] （来源: sourceName）`.

## Risks and trade-offs

- HNSW is approximate and trades recall for latency.
- The production query currently selects the complete ORM row, including embedding.
- Local reranking adds embedding calls but avoids a second provider dependency.
- `searchedChunks` is a metadata count; retrieval results remain user-filtered.

## Verification

Run unit tests, then use `scripts/rag_eval/eval_rag.py` and `sweep_ef.py` against a disposable evaluation user. State whether the measurement is retrieval-only or end-to-end.