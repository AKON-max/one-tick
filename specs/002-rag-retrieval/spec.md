# Feature Specification: RAG Retrieval

- Status: implemented
- Last reviewed: 2026-10-15

## Problem

Users need to ask questions over their own Markdown, text, PDF, and DOCX material. The answer must be based on retrieved evidence and remain isolated per user.

## Behavior

Users upload documents through `/api/knowledge/documents`. The backend extracts text, chunks it, embeds it, and stores 1024-dimensional vectors in `DocumentChunk`. A query embeds the question, retrieves candidates with pgvector, reranks the candidates, and returns the Top-5 with source names.

## Requirements

- R1: Support `md`, `markdown`, `txt`, `pdf`, and `docx`.
- R2: Reject content shorter than ten characters.
- R3: Markdown is split by `##` sections; other text uses 500-character chunks with 50-character overlap.
- R4: Embeddings are requested in batches of at most ten.
- R5: Store the source document separately in `KnowledgeDoc`.
- R6: Same-user, same-source upload replaces the previous version.
- R7: Retrieval filters by `userId` and optional `sourceName`.
- R8: Recall Top-20, then rerank to a final Top-5.
- R9: Return `sourceName` and `chunkIndex` so the model can cite evidence.

## Failure behavior

- Unsupported format: 400.
- Empty or too-short content: 400.
- Embedding failure: surface the error and do not claim a successful ingest.
- Rerank failure: fall back to vector order and mark scores as unavailable.
- No matches: return an empty result and let the assistant state that the knowledge base has no evidence.

## Acceptance criteria

- AC1: `tests/test_chunking.py` verifies chunking behavior.
- AC2: `tests/test_ai_contract.py` verifies the retrieval and embedding constants.
- AC3: `scripts/rag_eval/RAG_EVAL.md` records corpus size, metrics, index parameters, and limitations.
- AC4: A user cannot retrieve another user's chunks.

## Out of scope

- Cross-user shared knowledge bases.
- Multimodal image extraction.
- Cross-encoder reranking.