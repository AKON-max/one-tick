# Maintenance Log

## 2026-10-15 · Public repository preparation

- Added `README.md`, `specs/`, ADRs and unit tests.
- Added GitHub Actions CI for backend tests and frontend checks.
- Normalized One-Tick naming across runtime configuration and package metadata.
- Removed legacy migration and course references from implementation comments.
- Fixed Settings parsing when `.env` also contains Compose-only variables.
- Fixed RAG retrieval metadata to use the current user scope.
- Added sanitized architecture assets and handoff documentation.
- Kept local-only interview material outside the repository.

### Open follow-ups

- [ ] Move WebSocket connection state and model availability state to shared storage.
- [ ] Add database unique constraints for check-in and focus-session idempotency.
- [ ] Project only required columns in the production RAG query.
- [ ] Add provider-stub integration tests.
- [ ] Add monitoring, alerts, backup automation and restore drills.

## 2026-09 · Learning-loop delivery

- Added the plant growth state machine and island tree mapping.
- Added the 3D island coastline generation based on unlocked tiles.
- Added the RAG vector index migration.
- Added model fallback tiers and streaming AI chat orchestration.

## Maintenance rules

1. Behavior changes update the matching spec and tests.
2. Schema changes use a new Alembic migration.
3. Metrics include environment, corpus size and sample count.
4. Local-only files never enter a commit.
5. Deployment notes use placeholders for hosts and paths.