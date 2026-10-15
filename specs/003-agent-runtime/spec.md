# Feature Specification: Agent Runtime and Approval

- Status: implemented
- Last reviewed: 2026-10-15

## Problem

AI-generated plans and daily suggestions need to be explainable and controllable. A model must not silently write arbitrary business data.

## Behavior

The planner generates a structured `PlanDraft` and pauses at `awaiting_approval`. Approval creates the plan and tasks. The daily runtime observes learning data, produces findings and actions, records the run, and executes non-destructive notifications/reports.

## Requirements

- R1: Persist every run in `AgentRun`.
- R2: Persist ordered steps in `AgentStep`.
- R3: Persist approvals in `AgentApproval`.
- R4: Validate the draft with Pydantic and limit tasks to 40.
- R5: Fall back to a deterministic seven-day draft if generation fails.
- R6: Require ownership when reading, approving, or cancelling a run.
- R7: Allow cancellation of running or pending steps.
- R8: Keep daily action execution observable through decisions and notifications.

## Failure behavior

- Invalid or truncated model JSON: retry once, then use fallback.
- Missing run: 404.
- Approval on the wrong state: return 400 instead of writing partial data.
- Daily failure for one user: continue the remaining users.

## Acceptance criteria

- AC1: `python -m compileall -q app` succeeds.
- AC2: `tests/test_ai_contract.py` verifies draft limits.
- AC3: A planner run reaches `awaiting_approval` before creating a plan.
- AC4: A rejected run creates no plan.

## Out of scope

- Distributed recovery for runs interrupted mid-process.
- Fine-grained policy approval per tool type.