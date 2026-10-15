# Development

## Prerequisites

- Python 3.12+
- Node.js 22+
- Docker Desktop or Docker Engine with Compose
- PostgreSQL 16 with pgvector when running outside Compose

## Environment

```bash
cp .env.example .env
```

Fill at minimum:

- `JWT_SECRET`
- `POSTGRES_PASSWORD`
- one chat provider key: `ALIYUN_API_KEY` or `AGNES_API_KEY`
- `EMBEDDING_API_KEY` when embeddings use a separate key

Never commit `.env`.

## Backend

```bash
python -m venv .venv
# activate the environment for your shell
pip install -r requirements.txt
docker compose up -d db
alembic upgrade head
uvicorn app.main:app --reload --port 8001
```

Health check: `GET http://localhost:8001/health`.

## Frontend

```bash
cd frontend
npm install
API_PROXY_TARGET=http://localhost:8001 npm run dev
```

The Next.js rewrite sends `/api/*` to FastAPI during local development. In production, Nginx performs the split.

## Checks

```bash
python -m compileall -q app
python -m unittest discover -s tests -v

cd frontend
npm run typecheck
npm run lint
```

## Database migrations

```bash
alembic revision -m "describe change"
alembic upgrade head
```

Migration rules:

- Keep migrations deterministic and reversible where practical.
- Do not edit an applied migration to change deployed schema.
- Verify physical index state after manual DDL changes; an Alembic version is not proof that the physical index exists.