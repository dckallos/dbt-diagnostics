---
name: Test / CI / fixtures
about: Add or harden tests, fixtures, or CI -- including real-artifact contracts and gated live jobs. Shift-left coverage.
title: "test: "
labels: test
---

## Summary

<!-- What coverage gap or CI gap this closes, and the class of defect it would
have caught (e.g. a missing-import would be caught by compileall). -->

## Evidence and confidence

- Status: **PROVEN** (what CI does today vs misses) | **SPECULATIVE** (fixture not yet captured).
- Today: <what runs now -- jobs, Python versions, tiers, gates>.
- Missing: <the gap>.

## What runs with NO warehouse (offline, every PR)

- [ ] `real_*` artifact contracts (exact classification, structured fields, `--json`, degradation).
- [ ] First-party schema validation of consumed paths.
- [ ] Property/robustness (malformed shapes, unknown versions, Hypothesis invariants).
- [ ] `--no-live` CLI e2e (text, JSON, exit status, redaction, template fallback).
- [ ] Build/import gate:

```bash
python -m compileall dbt_diagnostics
python -m build
python -m venv smoke-venv && smoke-venv/bin/pip install dist/*.whl
smoke-venv/bin/dbt-diagnostics --help
```

## What requires a real Snowflake account (gated)

<!-- Visibility differences, effective grants, relation kinds, query-history
correlation, session params, real connector tuple shapes, real_* capture.
Gate by credentials + approved environment; never expose secrets to forked PRs. -->

## Acceptance criteria

- [ ] New tests fail on the defect they target and pass on the fix.
- [ ] Offline tiers run on every PR (3.11 and 3.12).
- [ ] Fixtures are real (`real_*`) or explicitly justified as synthetic, with provenance.
- [ ] CHANGELOG `[Unreleased]` if behavior/contract changes.

## Scope and files touched

- `dbt_diagnostics/tests/**`, `dbt_diagnostics/fixtures/real_*`
- `.pre-commit-config.yaml` (new) -- pushable
- `.github/workflows/*.yml`, branch-protection JSON -- **maintainer-applied** (the agent token cannot modify `.github/workflows/*`; deliver content for hand-commit).

## Traceability

- OUTPUT_THREE changes: <n, ...>
- OUTPUT_FOUR findings: Section 5 (CI / shift-left) | <...>
- Parent epic: #4 | #48
- Depends on: #12, #44, #52 (real fixtures) and the corrected probe APIs.

## Suggested labels

`test` (+ `ci`, `live`, `compat`)
