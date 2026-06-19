---
name: Bug / fix
about: A defect with reproducible wrong behavior (conventional commit -- fix:)
title: "fix: "
labels: bug
---

<!--
ASCII only. No AI-authorship markers anywhere (the environment auto-injects
one; strip it). First person, plain voice. Read AGENTS.md scope guard first.
Delete the guidance comments before submitting; keep the headings.
-->

## Summary

One or two sentences: what is wrong and the user-visible impact (e.g. a
false high-confidence verdict, a crash, a silently dropped result).

## Evidence and confidence

- Status: **PROVEN** | **SPECULATIVE** (pick one; delete the other)
- If PROVEN: cite the proof -- `file:line`, a failing test, or a first-party
  doc/schema URL. A claim about current behavior is not PROVEN until it is
  confirmed against the actual source on the branch, not against a snapshot.
- If SPECULATIVE: state exactly what evidence would confirm it (a real
  `real_*` fixture, a live Snowflake run, a doc citation) and open that as a
  verification task FIRST. Do not implement on speculation.

## Current (wrong) behavior

What happens today. Paste the offending code with a path:line reference.

```python
# dbt_diagnostics/<module>.py:<line>  (current)
# paste the real lines that are wrong
```

If it is a SQL/identifier/portability defect, show the exact statement:

```sql
-- current statement that is wrong
```

## Root cause

The actual mechanism, not the symptom. Name the epistemic error if there is
one (e.g. "treats a role-visibility-filtered empty SHOW as physical
nonexistence"; "failed probe rendered as a negative fact").

## Expected behavior

What it should do instead and the principle behind it.

## Proposed fix

```python
# dbt_diagnostics/<module>.py  (proposed)
# minimal, targeted diff -- no opportunistic refactor
```

## Reproduction

Exact steps, command, and the artifact/fixture that triggers it.

```text
$ dbt-diagnostics diagnose --project-dir ... [--no-live]
# observed vs expected output
```

## Acceptance criteria

- [ ] The defect no longer reproduces under the steps above.
- [ ] A regression test proves the CORRECT behavior (a positive assertion),
      not merely the absence of the previous false output.
- [ ] No new Snowflake assumption leaks outside the intended module.
- [ ] `--json` `schema_version` change, if any, is additive-only.
- [ ] CHANGELOG `[Unreleased]` updated (behavior change).

## Test plan

- Tier(s): `unit` | `contract` | `property` | `robustness` | `e2e` | `chaos` | `live`
- Runs offline, or needs a real Snowflake account? (state which assertions
  need live; gate those behind credentials, never on forked PRs.)

```python
# sketch the key test assertion(s)
```

## Scope and files touched

List files so file-disjoint issues can run as parallel PRs and colliding
ones are sequenced.

- `dbt_diagnostics/...`

## Snowflake / portability impact

Does the fix hard-code Snowflake codes, SQL, identifier folding, or type
semantics? If so, note what the future `WarehouseAdapter` seam must own.

## Traceability

- OUTPUT_THREE change(s): #
- OUTPUT_FOUR finding(s):
- Parent epic: #4 (Live Verification Engine) | #48 (Cross-Version Compat)
- Depends on / blocks: #

## Suggested labels

`bug`, `live` / `compat`, `correctness`, `snowflake`, `security` (as apt)
