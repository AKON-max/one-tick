# ADR 0004: Use a Tiered Model Fallback Pool

- Status: accepted
- Date: 2026-10-15

## Context

Model providers have independent free quotas and rate limits. Different product surfaces need different latency and capability profiles.

## Decision

Define HIGH, LOW, and EMBEDDING chains. On quota exhaustion mark a model unavailable in-process; on rate limiting cool it down for 60 seconds. Set SDK retries to zero so the pool controls retry behavior.

## Consequences

Positive:

- A single provider failure does not take down all AI surfaces.
- Cheap models handle background and low-risk work.
- Usage can be attributed to the model that actually served the request.

Negative:

- Availability state is process-local.
- Output style changes when fallback occurs.
- Logs must retain the selected model for debugging.