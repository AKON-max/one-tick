# ADR 0001: Use PostgreSQL with pgvector and HNSW

- Status: accepted

## Context

The knowledge base is small enough to remain a single-node system, but it needs user isolation, deletion semantics, transactional consistency, and vector retrieval.

## Decision

Store business data and 1024-dimensional vectors in PostgreSQL 16 with pgvector. Use an HNSW cosine index and tune `ef_search` against an exact-search baseline.

## Consequences

Positive:

- One database, one transaction boundary, and one backup boundary.
- Deleting a user can cascade to `DocumentChunk`.
- User and source filters combine naturally with vector predicates.

Negative:

- Vector search shares database resources with business queries.
- HNSW is approximate, so recall must be measured.
- A future corpus in the tens of millions may require a separate vector store.