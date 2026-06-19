---
name: Refactor / architecture
about: A structural change that preserves behavior or replaces a representation (conventional commit -- refactor:)
title: "refactor: "
labels: refactor
---

<!--
ASCII only. No AI-authorship markers. Read AGENTS.md scope guard first:
no static linting; no ungated warehouse-scanning probes. A refactor that
adds a compatibility shim immediately superseded by a later change is a
red flag -- prefer switching one capability at a time and removing the
legacy path in the SAME change. Delete guidance comments before submitting.
-->

## Summary

What structure changes and why. State the behavior contract: is this a
pure refactor (no behavior change) or a representation change with a
defined, tested behavior delta?

## Motivation

The concrete problem with the current structure (overloaded type, lost
evidence on mutation, linear rescans, leaked Snowflake assumptions, flat
list used as an edge path, etc.). Cite `file:line`.

## Evidence and confidence

- Status: **PROVEN** | **SPECULATIVE**
- Proof of the current structural defect (`file:line`, import graph, a test
  that is order-dependent, a measured rescan).
- If a claimed import cycle or breakage is speculative, say what would
  confirm it (e.g. `python -m compileall`, an actual injection attempt).

## Current design

```python
# dbt_diagnostics/<module>.py:<line>  (current shape)
```

## Proposed design

Describe the target representation. Show the new types/interfaces.

```python
# proposed dataclasses / protocol / function signatures
```

If this introduces a seam (adapter, gateway, index), state explicitly:
- who CONSTRUCTS it,
- who is INJECTED with it,
- who CALLS it.
A seam that nothing constructs, injects, or calls changes nothing -- do not
file that as a refactor; file it as a spike.

## Migration / compatibility plan

- What stays as a wrapper, for how long, and the issue that removes it.
- Parity matrix: every capability the legacy path has that the new path
  must match before the legacy path is deleted.

```text
capability            | legacy path | new path | switched in
--------------------- | ----------- | -------- | -----------
```

## Acceptance criteria

- [ ] Behavior delta is exactly as stated (golden output updated if user-visible).
- [ ] No capability regressions vs the parity matrix.
- [ ] No probe/query is executed twice for the same finding.
- [ ] No new import cycle (`python -m compileall dbt_diagnostics` clean).
- [ ] `--json` additive-only.
- [ ] CHANGELOG `[Unreleased]` updated if anything is user-visible.

## Test plan

- Tier(s): `unit` | `contract` | `property` | `robustness` | `e2e`
- Tests must prove a correct positive outcome on a real edge/case, not just
  that a structure exists (e.g. a real disconnect is found AND siblings are
  not falsely connected).

```python
# key invariant / parity assertion(s)
```

## Scope and files touched

- `dbt_diagnostics/...`

## Snowflake / portability impact

Does this advance or merely appear to advance warehouse-neutrality? Be
honest about what still leaks (dialect, identifier folding, error codes,
type semantics, query-history shape).

## Traceability

- OUTPUT_THREE change(s): #
- OUTPUT_FOUR finding(s):
- Parent epic: #4 | #48
- Depends on / blocks: #

## Suggested labels

`refactor`, `architecture`, `lineage` / `live` / `compat`, `correctness`
