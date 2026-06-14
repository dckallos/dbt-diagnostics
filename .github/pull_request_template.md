## What and why

<!-- One or two sentences. What changed and why. -->

Closes #
Epic: #

## Definition of Done

- [ ] Linked to an issue that traces to an epic.
- [ ] Tests added/updated; `pytest` green locally and in CI.
- [ ] `CHANGELOG.md` updated if behavior changed.
- [ ] Offline behavior defined (degrades to `unverified` + the query to run).
- [ ] No Tier-B (warehouse-scanning) probe runs without a cost gate.
- [ ] No re-entry into static-lint space (AGENTS.md scope guard).
- [ ] `--json` `schema_version` change, if any, is additive-only.
- [ ] Relevant design doc still consistent.

## Offline and live behavior

<!-- What the feature reports with no Snowflake connection, and what it
confirms live. Name the probes and their cost tier (A or B). -->

## Notes for the reviewer

<!-- Anything that helps review: tradeoffs, follow-ups, deferred work. -->
