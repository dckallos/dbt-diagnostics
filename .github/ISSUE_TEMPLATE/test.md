---
name: Test / CI
about: New test coverage, fixtures, or CI/shift-left work (conventional commit -- test: or chore(ci):)
title: "test: "
labels: test
---

<!--
ASCII only. No AI-authorship markers. Tests must assert CORRECTNESS, not
branch selection or wording. "Asserts a graph has edges" or "asserts a
param was collected" without checking the user-visible, correct outcome is
test theater -- the exact failure mode the OUTPUT_FOUR red-team called out.
NOTE: the agent token cannot edit .github/workflows/*; any ci.yml change is
handed to the maintainer to commit by hand. Delete guidance before submitting.
-->

## Summary

What behavior or contract this locks down, and the gap it closes.

## What is under-tested today

The specific code path, version, or input class with no coverage. Cite
`file:line` or the missing tier.

## Test design

- Tier(s): `unit` | `contract` | `property` | `robustness` | `e2e` | `chaos` | `live`
- Offline vs live: which assertions need a real Snowflake account?
- Fixtures: real `real_*` golden artifact, recorded connector rows, or
  synthetic? (Prefer real; justify any synthetic fixture.)

```python
# the key assertions -- show that a CORRECT positive result is asserted,
# not just the absence of a previous false one
```

## Fixtures / data needed

- [ ] `dbt_diagnostics/fixtures/real_*` ... (provenance: dbt-core/adapter
      version, capture command, date)
- [ ] recorded tuple shapes (cite the Snowflake doc for column order)

## CI / shift-left (if applicable)

What should run on every PR with NO warehouse, and what needs a gated live
job. Examples that need no warehouse: real-artifact contracts, first-party
schema validation, property/robustness, `--no-live` CLI e2e, recorded-row
adapter contracts, `python -m compileall`, a build + installed-wheel smoke
test, a 3.11/3.12 matrix.

```yaml
# proposed ci.yml job/step (for the maintainer to commit -- token cannot
# modify .github/workflows/*)
```

## Acceptance criteria

- [ ] New tests fail before the fix/feature and pass after (or guard a
      known-good contract).
- [ ] Assertions check correctness, not wording/branch selection.
- [ ] Live-only assertions are gated by credentials and never exposed to
      forked PRs.
- [ ] Required status checks updated if a new gate is added (maintainer).

## Scope and files touched

- `dbt_diagnostics/tests/...`, `dbt_diagnostics/fixtures/...`
- `.github/workflows/ci.yml` (maintainer-applied)

## Traceability

- OUTPUT_THREE change(s): #
- OUTPUT_FOUR finding(s): (e.g. Section 5 CI gaps; "test theater")
- Parent epic: #4 | #48
- Depends on: #12, #44, #52 (real fixtures) as applicable

## Suggested labels

`test`, `ci`, `compat` / `live`, `robustness`
