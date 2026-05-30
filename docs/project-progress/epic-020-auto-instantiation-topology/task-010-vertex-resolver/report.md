# Task Report — T010 VertexResolver

**Epic:** E020 — Auto-instantiation & Topology Validation
**Task:** T010
**Status:** DONE
**Date:** 2026-05-29

## Summary

Implemented `VertexResolver` — a Flyweight (GoF) singleton-per-class registry for
`StateVertex` auto-instantiation. All DoD criteria met; ruff, mypy --strict, and
the full pytest suite pass.

## Files Created / Modified

| File | Action |
|------|--------|
| `src/agentflow/statemachine/resolver.py` | Created |
| `src/agentflow/tests/statemachine/test_resolver.py` | Created |
| `src/agentflow/statemachine/__init__.py` | Updated — added `VertexResolver` export |
| `doc/project-progress/epic-020-auto-instantiation-topology/task-010-vertex-resolver/dod.md` | Updated — all items checked |

## Implementation Notes

- `VertexResolver.resolve(v)` accepts `type[StateVertex] | StateVertex`.
  - If `v` is already a `StateVertex` instance → returned unchanged (identity).
  - If `v` is a class → constructor validated via `inspect.signature`, then
    instantiated and cached in `self._store`.
- Validation skips `self` and raises `ValueError` on the first parameter that
  lacks a default value (message matches spec exactly).
- `clear()` empties `self._store` — test isolation without creating a new resolver.
- Pattern: Flyweight (GoF) — noted in class-level comment.

## Code Quality Results

```
ruff check src/agentflow/statemachine/resolver.py  →  All checks passed!
mypy --strict --follow-imports=skip resolver.py    →  Success: no issues found in 1 source file
```

## Test Results

```
pytest src/agentflow/tests/statemachine/test_resolver.py -v
5 passed in 0.06s

pytest src/agentflow/tests/statemachine/ -v
49 passed in 0.24s
```
