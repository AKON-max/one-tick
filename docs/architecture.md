# Architecture

## Runtime topology

```mermaid
flowchart LR
    U[Browser] --> N[Nginx]
    N -->|/api/* and /ws| A[FastAPI]
    N -->|pages and assets| W[Next.js]
    A --> P[(PostgreSQL + pgvector)]
    A --> M[Model providers]
    W -->|server-side fetch| A
```

Nginx keeps the application on one origin. Browser requests use relative paths; the frontend uses the same session cookie without configuring a public API base URL.

## Backend layers

| Layer | Responsibility |
|---|---|
| `app/routers/` | Authentication, validation, HTTP and WebSocket protocol |
| `app/services/` | Reusable domain services: statistics, plan splitting, notifications, usage, OSS |
| `app/ai/` | Model routing, RAG, memory, Agent runtime, tool registry |
| `app/models/` | SQLAlchemy ORM and database constraints |
| `alembic/` | Schema evolution and pgvector index creation |
| `app/ws/` | Connection lifecycle, room broadcast, chat protocol, AI mentions |
| `frontend/src/` | App Router pages, Server Actions, UI, Three.js island |

## AI request path

```mermaid
sequenceDiagram
    participant Browser
    participant API as FastAPI /api/ai
    participant Tools as Tool registry
    participant Pool as Model pool
    participant DB as PostgreSQL

    Browser->>API: POST /api/ai
    API->>DB: load conversation + memories
    API->>Tools: create user-scoped tools
    API->>Pool: streaming completion with tool loop
    Pool-->>API: deltas and tool calls
    API-->>Browser: StreamingResponse deltas
    API->>DB: save assistant message, usage, extracted memories
```

## Data ownership

- Business queries are scoped by `userId`.
- `DocumentChunk` and `KnowledgeDoc` are per-user.
- AI tools created by `create_*_tools(user_id)` close over the current user ID.
- Planner approvals must belong to the current user before a write is performed.

## Important trade-offs

- pgvector keeps vectors in the same transaction and backup boundary as business data.
- HNSW is used because the knowledge base is written incrementally; `ef_search` is a measured trade-off.
- WebSocket is intentionally single-process at the current scale.
- Model-provider availability is process-local; it is business-level degradation, not platform-wide HA.