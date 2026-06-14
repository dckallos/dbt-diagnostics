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
- Implemented issue #7 on branch `feat/7-root-cause-aggregator` (cut from
  `donkey-kong-sandbox`). Opened as a PR for review; NOT merged.
- New `dbt_diagnostics/root_cause.py`: collapses same-signature 002003
  "object does not exist" errors into one `RootCauseGroup` and attaches one
  Tier-A verdict (never_built / exists_now / denied / unverified). The denied
  branch is decided via grants, not a bare `table_exists` False (SHOW TABLES
  cannot tell "absent" from "invisible"). Offline degrades to "unverified" +
  the query to run.
- New `dbt_diagnostics/enrichers/run_identity.py`: recovers the run's role
  from query history (query_id -> INFORMATION_SCHEMA.QUERY_HISTORY.ROLE_NAME),
  with a fidelity ladder (recovered -> declared -> session), a watermark check
  that distinguishes "lagging" from "never", a single bounded retry, and a
  drift warning when recovered != declared.
- Wired into `main.py` (root_cause_groups built live while the connection is
  open, else offline) and surfaced in both outputs: `--json` schema_version
  1.0 -> 1.1 (additive) with a new `root_cause_groups` array; terminal gains a
  ROOT CAUSE section reusing `findings/lineage_trace.j2`. `renderer.render_text`
  takes an optional `root_cause_groups` arg (defaults to none).
- Tests: `tests/test_root_cause.py` + `tests/test_run_identity.py` (18 cases).

**Verification (IMPORTANT -- read before merging)**
- This window ran inside Cortex Code in Snowsight, which CANNOT reach github
  over git or install pytest. Work was authored over the GitHub API.
- The 18 NEW tests were executed locally via a minimal runner (vendored stubs
  for models/grants): 18/18 pass. All new modules pass `py_compile`, and
  `report.j2` was render-tested (46 errors -> one ROOT CAUSE line).
- The full 336-test baseline was NOT run in this environment. You MUST run
  `pytest dbt_diagnostics/tests -q` on the Mac before merging. Likely needing
  updates: any existing test asserting the top-level `--json` `schema_version`
  equals "1.0" (now "1.1"), and any snapshot test of terminal output for runs
  containing 002003 errors (new ROOT CAUSE section).

**Current state**
- `feat/7-root-cause-aggregator` pushed (5 commits: feat module, feat
  wiring+template, feat main/renderer, tests, docs). PR opened into
  `donkey-kong-sandbox`. Not merged.
- `donkey-kong-sandbox` unchanged by this window apart from the branch.

**Next steps**
- Run the full suite on the Mac; reconcile the two test-update risks above.
- Review the 3-way verdict heuristic against a real 002003 run_results.json
  (confirm `adapter_response.query_id` is present on failed nodes; if often
  absent, prioritise the Tier-1 hook follow-up).
- Consider the follow-up issue for the pre-execution dbt hook (attested run
  identity) filed alongside this PR.

**Be careful**
- Do not merge the PR; it is the owner's to review.
- Do not re-introduce static linting; do not add Tier-B scans (scope guard).
- `--json` changes must stay additive.

End of session -- 2026-06-14 issue #7 single-root-cause aggregator implemented
