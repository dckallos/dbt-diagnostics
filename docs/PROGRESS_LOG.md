# Progress log

> The newest dated entry is the current state. Append; do not rewrite history.
> When resuming, read the latest entry first and skip items already done.
>
> This log replaces the older hand-off notes. `docs/HANDOFF_PROMPT.md` and
> `docs/HANDOFF_PROMPT_2.md` are kept for history as of 2026-06-14 -- read them
> for background, but record new progress here.

---

## 2026-06-14 -- continuity and workflow scaffolding

**What changed**
- Committed the Live Verification Engine design doc
  (`docs/DESIGN_LIVE_VERIFICATION.md`) on `donkey-kong-sandbox`: initial draft,
  then terminal+JSON output, effort/usefulness and cost tiers, and the
  proactive/reactive section.
- Opened the epic and feature issues:
  - #4 Epic: Live Verification Engine (status board)
  - #7 single-root-cause aggregator (Tier A)
  - #9 incremental stale-state detector (Tier A)
  - #5 upstream grain tracing (Tier B, flagship, gated)
  - #6 orphan-FK detection (Tier B)
  - #8 UNION-branch attribution
  - #10 static grain-consistency cross-check (proactive, $0)
- Added project conventions, this progress log, CONTRIBUTING, and the GitHub PR
  and issue templates on branch `chore/agent-continuity-workflow` (PR #11 into
  `donkey-kong-sandbox`). CI workflow added separately.

**Finding**
- `sqlglot>=26,<28` is already a core dependency in `pyproject.toml`, so the
  design doc's open question about adding a parser dependency for UNION
  attribution is moot. Correct section 7 in a follow-up.

**Current state**
- `donkey-kong-sandbox`: design doc + the 7 issues.
- `chore/agent-continuity-workflow`: the conventions/workflow docs, in review.
- No package code (`dbt_diagnostics/`) changed yet; no feature implemented yet.

**Next steps**
- After PR #11 merges, point epic #4 at these docs as the status board.
- Start the first feature: #7 (aggregator) -- lowest effort, $0, and it builds
  the test-failure-finding scaffolding the flagship #5 needs.
- Correct design doc section 7 (sqlglot already present) and decide the Tier-B
  cost ceiling and grain-source questions that gate #5.

**Open decisions**
- Tier-B cost ceiling (row-count cap / SAMPLE / per-run query cap / walk depth).
- Grain source: declared uniqueness tests vs. inferred from
  `generate_surrogate_key` args.
- schema_version policy (CONTRIBUTING.md sets additive-only).
- Whether to take on the deferred live invariant-scan epic (design doc 6/9).

**Be careful**
- Do not re-introduce static linting (scope guard in AGENTS.md).
- Do not add a Tier-B probe without a cost gate.
- Do not push directly to `donkey-kong-sandbox` or `main`; use a feature branch
  and a PR.

End of session -- 2026-06-14 continuity and workflow scaffolding

---

## 2026-06-14 -- issue #7 single-root-cause aggregator implemented

**What changed**
- Cut `feat/7-root-cause-aggregator` off `donkey-kong-sandbox` and implemented
  issue #7 (the first Live Verification Engine probe).
- New `dbt_diagnostics/root_cause.py`: collapses Snowflake "object does not
  exist" (002003) errors into one `RootCauseGroup` per missing object, with a
  single live-disambiguated verdict (`never_built` / `exists_now` / `denied` /
  `unverified`). `denied` is decided by `SHOW GRANTS`, not by `table_exists`,
  since `SHOW TABLES` cannot separate "missing" from "invisible to the role".
  Reuses `schema_inspector.table_exists` and `grants.check_role_grants`.
- New `dbt_diagnostics/enrichers/run_identity.py`: recovers the run's role from
  the failing `query_id` via `INFORMATION_SCHEMA.QUERY_HISTORY` (Tier 0), with
  declared-profile (Tier 2) and session (Tier 3) fallbacks; watermark check
  separates "lagging" from "never" with one bounded retry; flags role drift.
- Wired into `main.py` (`cmd_diagnose` + `_try_enrich` build the groups; `--json`
  bumped to `schema_version` 1.1 with an additive `root_cause_groups` key),
  `renderer.py` (new `root_cause_groups` arg), and `report.j2` (new ROOT CAUSE
  section reusing the `lineage_trace` partial).
- Added `tests/test_root_cause.py` (10) and `tests/test_run_identity.py` (8).
- Updated `CHANGELOG.md` `[Unreleased]`.
- workspace stage: pushed to GitHub branch `feat/7-root-cause-aggregator`
  (three commits). applied-to-account: n/a. pushed-to-Mac: no (branch is remote).

**Verification (important caveat)**
- This was authored from a Cortex Code Snowsight sandbox that CANNOT run the
  repo's pytest suite (no PyPI/pytest, no github clone -- proxy allowlist). I
  verified by: `py_compile` on all new/changed Python; a standalone runner that
  executed all 18 new test functions against the real `root_cause` /
  `run_identity` logic (18/18 pass); and a Jinja render of `report.j2` + the
  `lineage_trace` partial (collapsed-group case and empty case both OK).
- NOT yet run on a Mac: the full 336-test baseline. The `--json`
  `schema_version` 1.0 -> 1.1 bump WILL break any existing test that asserts the
  top-level version string -- those assertions must be updated to 1.1 (additive
  key add is intended). Run `pytest dbt_diagnostics/tests -q` locally and fix
  any version-string assertions before merging.

**Next steps**
- On the Mac: pull the branch, run `pytest dbt_diagnostics/tests -q`, fix any
  schema_version assertions, eyeball `dbt-diagnostics demo` for the new ROOT
  CAUSE section, then review PR #14.
- File/triage the follow-up issue: opt-in dbt `on-run-start` identity-stamp hook
  (highest-fidelity role source; out of #7 scope).

**Be careful**
- Do not merge PR #14 from the agent -- owner reviews and merges.
- Do not re-introduce static linting; keep probes Tier A (no warehouse scans).
- The vendored `models.py` / `grants.py` used for the sandbox test-run were NOT
  pushed; the real modules are unchanged.

End of session -- 2026-06-14 issue #7 single-root-cause aggregator implemented

---

## 2026-06-14 -- issue #7 merged (test fix + follow-up cleanup)

**What changed**
- Owner re-ran the suite on the Mac: `pytest dbt_diagnostics/tests -q` ->
  354 passed, 0 failed.
- The only baseline failure was a stale assertion in `tests/test_main.py`
  pinning the top-level `--json` `schema_version == "1.0"`. Updated it to
  `"1.1"` and added a positive assertion for the new additive
  `root_cause_groups` key so the schema change is covered (commit 64ccc84).
- Marked PR #16 ready and squash-merged it into `donkey-kong-sandbox`
  (issue #7 closed).
- Closed issue #19 as a duplicate of #17: the attested-run-identity hook
  follow-up was already filed as #17 by the implementing session.

**Corrections to the prior entry**
- The aggregator PR is #16 (the prior entry said "#14"); now merged.
- The empirical 354-test run also clears the prior entry's caveat -- the new
  modules' assumptions about `models.py` / `grants.py` attributes are valid
  against the real modules (the 18 new tests exercise them and pass).

**Current state**
- `donkey-kong-sandbox`: now includes the #7 aggregator (one squashed commit).
- Open follow-up: #17 -- attested run-identity dbt hook (Tier A, opt-in).

**Next steps**
- Optional: eyeball `dbt-diagnostics demo` for the new ROOT CAUSE section.
- Next epic-#4 feature by build order: #9 (incremental stale-state detector,
  Tier A), then the gated flagship #5.

**Be careful**
- Tier A only; no static linting; keep `--json` schema additive.
- `main` stays stable; only promote `donkey-kong-sandbox` -> `main` at a release.

End of session -- 2026-06-14 issue #7 merged
