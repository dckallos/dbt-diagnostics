---
name: Feature / diagnostic capability
about: A new diagnostic capability or user-facing enhancement (conventional commit -- feat:)
title: "feat: "
labels: enhancement
---

<!--
ASCII only. No AI-authorship markers. Read AGENTS.md scope guard: the tool's
purpose is live, database-grounded root-cause analysis. No static linting;
Tier-B (warehouse-scanning) probes must be gated by a cost ceiling and opt-in.
Every state assertion must be confirmable by a live query; offline degrades to
"unverified" + the query to run. Delete guidance comments before submitting.
-->

## Summary

The capability in one or two sentences and the user value.

- **Cost tier:** A ($0 metadata) | B (warehouse-scanning, gated + opt-in)
- **Effort:** Low | Low-Med | Medium | Med-High | High
- **Usefulness:** <frequency + value, one line>

## Trigger

The exact condition that fires this diagnostic (error class, signature,
artifact state). Be precise -- a too-broad trigger is how false diagnoses happen.

## Behavior

Numbered steps. Name each probe and its cost tier. State what is confirmed
live vs inferred from artifacts, and the confidence attached to each.

```text
1. ...
2. live probe: ...   (Tier A)
3. verdict: ...       (confidence: high | medium | unverified)
```

## Evidence model

What evidence backs the verdict, the IDENTITY under which it was gathered,
and when the verdict must downgrade to `unverified`. Never emit a
high-confidence cause the evidence does not prove.

## Output

- Terminal: ...
- `--json`: new additive keys only (state them); `schema_version` bump.

```json
{
  "...": "..."
}
```

## Reuse vs net-new

Existing modules this builds on (`dag_walker`, `enrich`, `schema_inspector`,
`grouping`, `compat.safe`, ...) and what is genuinely new.

## Acceptance criteria

- [ ] The target case produces the correct, evidence-backed diagnosis.
- [ ] Offline renders `unverified` + the exact query to run; never crashes.
- [ ] Tier-B work respects the cost gate and is opt-in.
- [ ] `--json` additive-only.
- [ ] CHANGELOG `[Unreleased]` updated.

## Test plan

- Tier(s): `unit` | `contract` | `e2e` | `live`
- A positive test on the target case + a negative test that it does NOT
  fire on the look-alike-but-healthy case.

## Scope and files touched

- `dbt_diagnostics/...`

## Snowflake / portability impact

Note any hard-coded Snowflake semantics for the adapter seam.

## Traceability

- OUTPUT_THREE change(s): #
- OUTPUT_FOUR finding(s):
- Parent epic: #4 | #48
- Blocked on / depends on: #

## Suggested labels

`enhancement`, `live` / `compat`, `tier-a` / `tier-b`
