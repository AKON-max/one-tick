# Maintenance Log

Running notes on what changed and why. Entries are grouped by delivery, not by release.

## 2026-10 · Retrieval quality

- Replaced the retrieval candidate scan with a single database-side Top-K query ordered by cosine distance.
- Added the HNSW cosine index in migration `0004_rag_vector_index` (`m=16`, `ef_construction=64`).
- Set `hnsw.ef_search = 100` per transaction, chosen from the sweep recorded in `scripts/rag_eval/RAG_EVAL.md`.
- Added the local cosine rerank stage (recall Top-20, rerank Top-5) and a similarity cutoff for refusal.
- Added the RAG evaluation scripts and the question set used to compare the old and new paths.

## 2026-09 · Realtime and model resilience

- Added the WebSocket room with handshake authentication, a 30s heartbeat with 2x timeout eviction, per-connection rate limiting and client id de-duplication.
- Added `@温柔宝` / `@嘴欠宝` / `/ai` parsing with per-role de-duplication, and moved AI generation off the broadcast path.
- Added the three-tier model pool with separate handling for quota exhaustion and rate limiting, and disabled SDK-level retries.
- Added token usage accounting per surface and tier.

## 2026-09 · Learning loop

- Added the plant growth state machine and island tree mapping (migrations `0002_garden`, `0003_garden_matured`).
- Added 3D island coastline generation from unlocked tiles.
- Added plan document to task synchronisation with a source hash for idempotency.
- Added the Agent runtime: observe / analyse / plan / execute with persisted runs, steps, approvals and decisions.

## Open follow-ups

- [ ] Move WebSocket connection state and model availability state to shared storage.
- [ ] Add database unique constraints for check-in and focus-session idempotency.
- [ ] Project only required columns in the production RAG query.
- [ ] Add provider-stub integration tests.
- [ ] Add monitoring, alerts, backup automation and restore drills.

## Maintenance rules

1. Behavior changes update the matching spec and tests.
2. Schema changes use a new Alembic migration.
3. Metrics include environment, corpus size and sample count.
4. Local-only files never enter a commit.
5. Deployment notes use placeholders for hosts and paths.