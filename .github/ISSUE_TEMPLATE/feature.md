---
name: Feature / capability
about: A new diagnostic capability or probe. Must be live, database-grounded root-cause analysis -- not static linting.
title: "feat: "
labels: enhancement
---

## Summary

<!-- The capability and the user problem it solves. Tie it to the project
thesis: live, DB-grounded root cause. Reject static-lint re-entry (scope guard). -->

## Cost tier

<!-- Tier A ($0 metadata, may run freely) or Tier B (warehouse-scanning:
COUNT DISTINCT, anti-joins -- MUST be cost-gated and opt-in). State which and
the guard if Tier B. -->

- Tier: **A** | **B (gated)**.

## Trigger

<!-- The exact failure/condition that activates this. Proactive checks are the
exception, allowed only as self-consistency cross-checks. -->

## Behavior

<!-- Step-by-step what it reads, probes, and concludes. Offline must degrade to
`unverified` + the query to run. -->

## Evidence and confidence

- Status: **PROVEN** | **SPECULATIVE** (basis).
- Inference risk: <if the feature infers grain/lineage, what happens when the
  inference is wrong -- confidently-wrong is worse than silent>.

## Example (input -> output, code)

```text
# trigger artifact/error in, diagnosis out -- the concrete target case
```

```python
# key probe or query the feature issues (the live confirmation step)
```

## Acceptance criteria

- [ ] The named target case produces the correct, evidence-backed diagnosis.
- [ ] Tier-B probes never run without the cost gate; offline -> `unverified` + query.
- [ ] A wrong/absent signal degrades safely (no false high-confidence cause).
- [ ] `--json` additive-only; CHANGELOG `[Unreleased]`.

## Test plan

- Tiers: `unit`, `e2e` (`--no-live`); `live` (gated) for the confirmation step.

## Scope and files touched

- `path/to/file.py`

## Snowflake / portability impact

<!-- Snowflake-specific SQL/types/identifiers introduced? Note for N7/N8. -->

## Traceability

- OUTPUT_THREE changes: <n, ...>
- OUTPUT_FOUR findings: <...>
- Parent epic: #4 | #48
- Depends on / blocked by: #<n>

## Suggested labels

`enhancement` (+ `tier-a`/`tier-b`, `live`, `json`, `api`, `decision`)
