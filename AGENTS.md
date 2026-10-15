# Repository Working Agreement

## Source of truth

1. `app/`, `frontend/src/`, `alembic/` and `scripts/` are the implementation source of truth.
2. `specs/` contains the maintained behavior contract and acceptance criteria.
3. `docs/adr/` records decisions and trade-offs that should not be rediscovered every time.
4. Do not claim a metric, deployment property, or integration that is not reproducible from the repository.

## Spec-driven workflow

Before changing behavior:

1. Read the matching spec under `specs/<feature>/`.
2. Update `spec.md` if the externally visible behavior changes.
3. Update `plan.md` if the technical approach changes.
4. Keep `tasks.md` current enough that another engineer can see what remains.
5. Add or update a test or a reproducible verification command.

## Quality gates

- Python: `python -m compileall -q app` and `python -m unittest discover -s tests -v`.
- Frontend: `npm run typecheck` and `npm run lint` from `frontend/`.
- RAG behavior: update `scripts/rag_eval/` evidence when retrieval behavior changes.

## Security

- Never commit `.env`, credentials, private keys, or production data.
- User-scoped queries must include the owning user ID.
- New AI tools must be created with a user-scoped closure and must not trust model-provided IDs without ownership checks.