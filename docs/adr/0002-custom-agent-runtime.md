# ADR 0002: Use a Small Custom Agent Runtime

- Status: accepted
- Date: 2026-10-15

## Context

The application needs persisted runs, explicit approvals, tool ownership, and a UI timeline. The workflow is currently bounded and mostly linear.

## Decision

Implement a small custom runtime around `AgentRun`, `AgentStep`, `AgentApproval`, `AgentDecision`, and user-scoped tool closures instead of introducing a graph framework.

## Consequences

Positive:

- Every step can be persisted and queried.
- Approval can be inserted at the exact write boundary.
- The dependency surface stays narrow.

Negative:

- No graph visualization, resumable checkpoint engine, or distributed scheduler is provided.
- More complex branching workflows will increase maintenance cost.