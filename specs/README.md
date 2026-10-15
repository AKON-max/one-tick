# Specifications

This directory contains maintained, implementation-facing specifications. Each feature keeps three artifacts:

```text
specs/<feature>/
├── spec.md      behavior, constraints, acceptance criteria
├── plan.md      technical approach, affected modules, risks
└── tasks.md     implementation and verification checklist
```

These files describe the current contract, not a claim that the repository followed a perfect historical process. When behavior changes, update the spec in the same change as code and tests.

## Active specifications

| ID | Feature | Status |
|---|---|---|
| 001 | AI chat orchestration | Implemented |
| 002 | RAG retrieval | Implemented; retrieval column projection remains open |
| 003 | Agent runtime and approval | Implemented |
| 004 | Realtime chat | Implemented; single-process limitation is explicit |

## Rules

1. One spec covers one externally observable capability.
2. Acceptance criteria must be testable by a command, a unit test, or a documented manual procedure.
3. Metrics must include corpus size, sample count, and environment.
4. Known limitations stay in the spec until they are actually removed.