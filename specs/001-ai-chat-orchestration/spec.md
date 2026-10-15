# Feature Specification: AI Chat Orchestration

- Status: implemented
- Last reviewed: 2026-10-15

## Problem

The learning assistant must answer from the user's real learning data, support personal documents, and remain usable when a model provider is rate-limited or out of quota.

## Behavior

`POST /api/ai` and `POST /api/ai/chat` accept a conversation history and return a streamed text response. The backend may call user-scoped business tools before producing the final answer.

## Requirements

- R1: Authenticate with Bearer token or `session_token` cookie.
- R2: Enforce the per-user daily token limit before starting an interactive call.
- R3: Create a conversation when no conversation ID is supplied and return `X-Conversation-Id`.
- R4: Keep at most the latest 20 rounds / 40 messages.
- R5: Inject relevant long-term memories when available.
- R6: Expose study, RAG, todo, and agent tools to the model.
- R7: Bound the tool loop to four rounds and always produce a final text response.
- R8: Save the assistant message, token usage, and extracted memories after streaming.
- R9: Fall back to another model for quota and rate-limit errors.

## Failure behavior

- Daily limit: stream a user-facing limit message and do not call a model.
- No conversation ownership: return 404.
- Tool failure: return a structured tool error and continue the loop.
- Provider quota: mark the model unavailable in-process and try the next model.
- Provider rate limit: cool down for 60 seconds and try the next model.
- Unexpected provider failure: return a generic recoverable response rather than leaking provider details.

## Acceptance criteria

- AC1: `python -m compileall -q app` succeeds.
- AC2: `tests/test_ai_contract.py` asserts the context and loop limits.
- AC3: `tests/test_ws_ai_mentions.py` verifies AI mention parsing.
- AC4: A manual request creates a conversation and persists both user and assistant messages.
- AC5: A quota failure switches models without changing the public response shape.

## Out of scope

- Multi-process model-state coordination.
- Long-term memory moving to database-side vector search.