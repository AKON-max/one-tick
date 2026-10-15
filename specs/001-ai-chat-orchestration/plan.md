# Technical Plan: AI Chat Orchestration

## Affected modules

- `app/routers/ai.py`
- `app/ai/model_pool.py`
- `app/ai/memory.py`
- `app/ai/tools/`
- `app/models/chat.py`
- `app/services/usage.py`

## Approach

The route owns authentication, conversation persistence, context truncation, and the HTTP response. A blocking provider call runs in a worker thread and publishes deltas through a queue. The model pool owns provider selection and usage accounting. Tools are closures created for the current user.

## Contracts

- `Conversation` and `ConversationMessage` persist history.
- `UserMemory` supplies personalization.
- `TokenUsage` records `surface`, `tier`, model, and token counts.
- `X-Conversation-Id` is the continuation contract for clients.

## Risks and trade-offs

- A thread and queue bridge blocking SDK calls to an async response; the generator is intentionally synchronous and runs in Starlette's worker pool.
- Process-local provider state is sufficient for one instance but not for horizontal scaling.
- Context truncation can remove details needed for old references; the assistant must not invent them.

## Verification

Run the unit tests, inspect a streamed response, then force a quota or rate-limit error in a local provider stub or test environment.