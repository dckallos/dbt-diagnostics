# PROGRESS_LOG.md -- canonical append-only trail

> The NEWEST dated entry is the current state. Append; never rewrite history.
> Resumption contract: read the latest entry first, skip items already marked
> done, and never assume you are the only live session.
>
> This log supersedes the historical hand-off files. `docs/HANDOFF_PROMPT.md`
> and `docs/HANDOFF_PROMPT_2.md` are ARCHIVED as of 2026-06-14 -- read for
> history, do not update them. New hand-offs go here.

---

## 2026-06-14 -- continuity + workflow scaffolding

**What changed this window**
- Committed the Live Verification Engine design doc
  (`docs/DESIGN_LIVE_VERIFICATION.md`) on `donkey-kong-sandbox` across commits
  (initial draft -> terminal+JSON -> effort/usefulness + cost tiers ->
  proactive/reactive section 9).
- Opened the epic and feature issues on GitHub:
  - #4 Epic: Live Verification Engine (status board)
  - #7 UC #5 single-root-cause aggregator (Tier A)
  - #9 incremental stale-state detector (Tier A)
  - #5 UC #2 upstream grain tracing (Tier B, flagship, gated)
  - #6 UC #7 orphan-FK detection (Tier B)
  - #8 UNION-branch attribution
  - #10 static grain-consistency cross-check (proactive, $0)
- Added this continuity + workflow scaffolding on branch
  `chore/agent-continuity-workflow` (AGENTS.md, CLAUDE.md, this log,
  CONTRIBUTING.md, .github PR/issue templates + CI), PR'd into
  `donkey-kong-sandbox` for review.

**Finding (resolves an open question)**
- `sqlglot>=26,<28` is ALREADY a core dependency in `pyproject.toml`. The
  design doc section 7 question "accept a new dependency for UNION attribution?"
  is moot -- the parser is already present. Recommend correcting design doc
  section 7 in a follow-up.

**Current state vs. remote**
- `donkey-kong-sandbox`: design doc + 7 issues live.
- `chore/agent-continuity-workflow`: this scaffolding, awaiting PR review/merge.
- No package code (`dbt_diagnostics/`) touched yet. No feature implemented yet.

**First-action options for the next window**
- (a) After this PR merges, update epic #4 to declare itself the status board
  and link AGENTS.md + CONTRIBUTING.md.
- (b) Start the first feature PR: #7 (UC #5 aggregator) -- lowest effort, $0,
  builds the test-failure-finding scaffolding the flagship #5 needs.
- (c) Correct design doc section 7 (sqlglot already present) + decide the
  Tier-B cost ceiling and grain-source questions that gate #5.

**Open decisions**
- Tier-B cost ceiling (row-count cap / SAMPLE / per-run query cap / walk depth).
- Grain source: declared uniqueness tests vs. inferred from
  `generate_surrogate_key` args.
- schema_version policy formalization (CONTRIBUTING.md proposes additive-only).
- Whether to promote the live invariant-scan deferred epic (design doc 6/9).

**Foot-guns (do NOT)**
- Do NOT re-introduce static linting (scope guard in AGENTS.md).
- Do NOT add a Tier-B probe without a cost gate.
- Do NOT push directly to `donkey-kong-sandbox` or `main`; use a feature branch
  + PR.

```
Reading order: AGENTS.md -> docs/PROGRESS_LOG.md (this entry) -> epic #4 ->
docs/DESIGN_LIVE_VERIFICATION.md.
Project: dbt-diagnostics. Branch model: feature branch off
donkey-kong-sandbox, PR back into it; main is stable.
Current state: design doc + issues #4-#10 live on donkey-kong-sandbox;
continuity/workflow scaffolding in PR (branch chore/agent-continuity-workflow).
No package code or features implemented yet.
Gating rule: state your plan and wait for the owner's explicit go (with a
date) before any write.
Thesis / scope guard: live DB-grounded root-cause only. No static linting.
No ungated Tier-B (warehouse-scanning) probes.
Next-action options: (a) merge PR + update epic #4; (b) start feature PR for
#7; (c) correct design doc section 7 + decide Tier-B ceiling and grain source.
Quote the latest `End of window` header back to the owner before proposing a
first action.
```

End of window -- 2026-06-14 continuity + workflow scaffolding
