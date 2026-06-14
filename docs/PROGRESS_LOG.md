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
