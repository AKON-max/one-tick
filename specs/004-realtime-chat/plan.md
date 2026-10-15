# Technical Plan: Realtime Chat

## Affected modules

- `app/ws/chat.py`
- `app/ws/room.py`
- `app/ws/protocol.py`
- `app/ws/ai_chat.py`
- `app/models/chat.py`
- `nginx.conf`

## Approach

Connections live in an in-process set protected by a lock. Messages are persisted before broadcast. AI mentions start asynchronous tasks so one slow provider call does not block the room. The current AI path generates once, then emits 20-character chunks over the existing delta protocol.

## Contracts

- Client types: `message`, `ping`.
- Server types: `ready`, `message`, `ai:start`, `ai:delta`, `ai:done`, `presence`, `pong`, `error`.
- Message limit: 2000 characters.
- Rate limit: 30 messages per 60 seconds.

## Risks and trade-offs

- In-memory room state prevents horizontal scaling.
- Simulated AI streaming is protocol-compatible but not token-native.
- Sequential broadcast is acceptable at the current scale.

## Verification

Use a WebSocket client to test authentication, ping/pong, duplicate IDs, rate limiting, and AI mention parsing. For multi-instance behavior, a Redis or PostgreSQL notification layer is required first.