---
name: Refactor
about: A structural change (no new user-facing capability) that improves correctness, separation, or maintainability behind compatibility.
title: "refactor: "
labels: architecture
---

## Summary

<!-- What is being restructured and WHY now. A refactor must buy a concrete
correctness or extensibility win -- not motion for its own sake. -->

## Evidence and confidence

- Status: **PROVEN** | **SPECULATIVE** (basis: <source read / import graph / metrics>).
- Current structural problem: `path/to/file.py:LINE` -- <overload, duplication, leak, cycle>.
- If SPECULATIVE (e.g. "this will become an import cycle"): what would confirm it.

## Current structure

```python
# the shape today (the coupling/duplication/overload being removed)
```

## Target structure

```python
# the shape after -- typed seams, single source of truth, injection points
```

## Compatibility / migration

<!-- One-PR-per-issue. Keep a shim ONLY if it is removed in the SAME change or
a named follow-up; do not ship a temporary layer that is immediately
superseded (an OUTPUT_FOUR anti-pattern). State what stays and what is
switched, one capability at a time. -->

- [ ] Old call sites enumerated (no "and others"): <list>
- [ ] Behavior preserved or the user-visible delta is documented (golden updates).

## Acceptance criteria

- [ ] No behavior regression (or documented + golden-updated).
- [ ] The seam is actually USED (injected/called), not merely defined.
- [ ] No duplicated work introduced (e.g. double probes, rebuilt indexes).
- [ ] Tests prove the new path is exercised, not the legacy fallback.
- [ ] CHANGELOG `[Unreleased]`; `--json` additive-only.

## Test plan

- Tiers: `unit`, `contract`; import/compile check (`python -m compileall`).

## Scope and files touched

- `path/to/file.py`

## Snowflake / portability impact

<!-- Does the refactor move Snowflake assumptions behind a seam, or just
relocate them? Be honest about what still leaks. -->

## Traceability

- OUTPUT_THREE changes: <n, ...>
- OUTPUT_FOUR findings: <...>
- Parent epic: #4 | #48
- Depends on / blocks: #<n>

## Suggested labels

`architecture` (+ `live`, `correctness`, `lineage`, `snowflake`)
