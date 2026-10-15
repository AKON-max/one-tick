# Feature Specification: Realtime Chat

- Status: implemented
- Last reviewed: 2026-10-15

## Problem

The learning workspace includes a shared realtime chatroom with AI personas. The server must reject unauthenticated sockets, prevent basic flooding and duplicate sends, and clean up stale connections.

## Behavior

Clients connect to `/ws` with a token in the query string or cookie. The server broadcasts messages to online connections, supports `@` mentions for AI personas, and broadcasts AI responses.

## Requirements

- R1: Reject connections without a valid JWT.
- R2: Keep a per-connection sliding-window rate limit.
- R3: Drop duplicate client message IDs.
- R4: Enforce the maximum message length.
- R5: Send periodic ping/pong and remove stale connections.
- R6: Support `@温柔宝`, `@嘴欠宝`, `@雨宝`, `@AI`, and `/ai`.
- R7: Use the model pool and token accounting for AI responses.
- R8: Store chat messages in `ChatMessage`.

## Failure behavior

- Invalid or expired token: close with policy code 1008.
- Invalid JSON or unknown type: return a structured error.
- Flooding: return `rate_limited`.
- AI quota exhausted: broadcast the user-facing energy message.
- Connection failure: remove it from the room and broadcast presence.

## Acceptance criteria

- AC1: `tests/test_ws_ai_mentions.py` verifies mention extraction and role deduplication.
- AC2: A valid socket receives `ready` and `presence`.
- AC3: A duplicate `clientId` produces one broadcast.
- AC4: A stale socket is removed by the heartbeat loop.

## Out of scope

- Multi-room chat.
- Multi-instance broadcast.
- Message editing or deletion.