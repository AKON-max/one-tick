# ADR 0003: Put Nginx in Front of FastAPI and Next.js

- Status: accepted
- Date: 2026-10-15

## Context

The browser needs same-origin pages, REST requests, cookies, server-sent chunks, and WebSocket connections in development and production.

## Decision

Serve pages from Next.js and route `/api/*` plus `/ws` to FastAPI through one Nginx origin. Disable response buffering for AI streaming and configure WebSocket upgrade headers explicitly.

## Consequences

Positive:

- No browser CORS configuration is needed.
- Cookies work without a public API base URL.
- API and WebSocket share one entry point.

Negative:

- Nginx timeout and buffering behavior is part of the AI correctness surface.
- Host and forwarded-header handling must remain correct for Server Actions and cookies.