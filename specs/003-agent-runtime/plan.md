# Technical Plan: Agent Runtime and Approval

## Affected modules

- `app/ai/agent/runtime.py`
- `app/ai/agent/service.py`
- `app/ai/agent/decisions.py`
- `app/ai/agent/report.py`
- `app/routers/agent.py`
- `app/models/agent.py`

## Approach

Planner runs use explicit state transitions and the approval table as a write barrier. Daily runs use an observe/analyze/execute loop and persist steps around each phase. Both paths store enough input/output JSON for debugging without exposing hidden chain-of-thought.

## Contracts

- `AgentRun.status` values: `queued`, `running`, `awaiting_approval`, `completed`, `failed`, `cancelled`, `rejected`.
- `PlanDraft` maximum 40 tasks.
- `(runId, stepNumber)` is unique.
- `AgentDecision` records reason, action, status, and feedback.

## Risks and trade-offs

- The model can produce semantically plausible but unsafe actions.
- The current approval gate is strongest for plan creation; daily actions are recorded but not all block on approval.
- A self-built runtime lacks the visualization and recovery tooling of a graph framework.

## Verification

Exercise create → approval/rejection → completion/cancel in a disposable database. Verify a rejected run has no `Plan` or `PlanTask` rows.