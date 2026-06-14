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

## 2026-06-14 -- #7 single-root-cause aggregator implemented (PR open)

**What changed**
- Implemented issue #7 on branch `feat/7-root-cause-aggregator` (cut from
  `donkey-kong-sandbox`) and opened a PR back into `donkey-kong-sandbox`.
  PR is NOT merged -- it is the owner's to review.
- New `dbt_diagnostics/root_cause.py`: collapses Snowflake 002003
  "object does not exist" errors into one `RootCauseGroup` per missing object
  and emits a three-way verdict (never_built / exists_now / denied). The
  `denied` branch is decided by SHOW GRANTS, not SHOW TABLES (SHOW TABLES
  cannot separate "absent" from "invisible to this role").
- New `dbt_diagnostics/enrichers/run_identity.py`: recovers the run's role from
  the failing query_id via INFORMATION_SCHEMA.QUERY_HISTORY (Tier 0, ground
  truth), with a fallback ladder (recovered -> declared -> session) and a
  drift warning. Distinguishes "lagging" (history catching up) from
  "not_found" via a watermark compare, with one bounded retry.
- Wired into `main.py` (--json `schema_version` 1.1 + new `root_cause_groups`
  key, additive), `renderer.py` (new optional `root_cause_groups` arg), and
  `templates/report.j2` (ROOT CAUSE section reusing the `lineage_trace`
  partial).
- Tests: `tests/test_root_cause.py`, `tests/test_run_identity.py`.
- Tier A only ($0 metadata). Offline / unconfirmable -> "unverified" + the
  query to run; nothing raises.

**Verification (important caveat)**
- This work was authored from a Snowsight Cortex session whose sandbox CANNOT
  reach github.com or PyPI and has NO pytest installed, so the full suite
  (336 baseline) was NOT run here. What WAS done: `py_compile` on all new/
  changed Python, a Jinja parse of `report.j2`, and the 18 NEW tests executed
  via a minimal stdlib runner against vendored copies of `models.py`/`grants.py`
  -- all 18 pass. The owner MUST run `pytest dbt_diagnostics/tests -q` on the
  Mac before merging and confirm the 336 baseline (now ~354) is green.

**Likely follow-ups for the review pass**
- Existing tests that assert the top-level `--json` `schema_version == "1.0"`
  will need updating to `"1.1"` (intended, additive bump).
- Snapshot/golden tests of `report.j2` output for runs containing 002003
  errors will gain a ROOT CAUSE section -- update expected output.
- A separate follow-up issue is being filed for the Tier-1 "attested identity"
  dbt pre-execution hook (highest-fidelity role capture; out of #7 scope).

**Be careful**
- Do not merge the PR automatically -- owner reviews.
- Keep the JSON schema additive (do not rename/remove 1.0 keys).
- Do not re-introduce static linting; do not add a Tier-B scanning probe.

End of session -- 2026-06-14 #7 single-root-cause aggregator implemented (PR open)
