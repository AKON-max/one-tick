# Contributing

This is a personal project maintained by a single developer. Changes should leave the repository easier to review, reproduce, and explain.

## Before opening a change

- Find the relevant spec in `specs/`.
- Record a non-trivial architecture decision in `docs/adr/`.
- Keep changes scoped to one feature or one infrastructure concern.
- Update `README.md` if setup, commands, or public behavior changes.

## Pull request checklist

- [ ] The behavior is described in `specs/`.
- [ ] The implementation is covered by a unit test or a reproducible command.
- [ ] Python compilation succeeds.
- [ ] Frontend type checking succeeds.
- [ ] No secret or local-only file is included.
- [ ] Known limitations and trade-offs are stated.

## Commit convention

Use a short imperative prefix:

```text
feat(ai): ...
fix(rag): ...
docs(spec): ...
chore(repo): ...
```