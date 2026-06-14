# AGENTS.md -- entry point for any AI agent working on dbt-diagnostics

> Read this file FIRST, every window. It is the cheapest read in the repo and
> tells you exactly how much more to read. It is model-neutral: it applies
> whether you are Claude, ChatGPT, or any other agent with repo access.

## Operating principle (read before acting)

**The repository is the memory; the chat is disposable.** No durable decision
may live only in a conversation -- it must land as a commit, an issue, a PR, or
a doc. Any agent resuming this work reconstructs state from these artifacts,
not from chat history. If you decide something that matters, write it down here
or on the relevant GitHub issue before you end the turn.

Source-of-truth hierarchy (one fact lives in exactly one place):

1. **AGENTS.md** (this file) -- entry point + ritual + conventions.
2. **docs/PROGRESS_LOG.md** -- the append-only "where are we" trail. The newest
   dated entry is the current state.
3. **The epic issue** (GitHub) -- the live status board for a body of work.
4. **The design doc** under `docs/` -- the spec for that body of work.
5. **PRs / commits / CHANGELOG.md** -- the work itself and what shipped.

## Reading order (stay token-efficient)

1. This file.
2. The latest entry in `docs/PROGRESS_LOG.md`.
3. The epic issue named in that entry.
4. The ONE design doc relevant to your task (e.g.
   `docs/DESIGN_LIVE_VERIFICATION.md`).
5. Source files -- only to edit, or when a doc tells you to.

Stop reading as soon as you know enough to act.

## Session-open ritual

1. `git pull` the latest `donkey-kong-sandbox` (this repo is often committed to
   from remote; your local copy may be stale).
2. Read the latest `docs/PROGRESS_LOG.md` entry and quote its `End of window`
   header back to the owner before proposing your first action.
3. State your plan and wait for the owner's explicit go (with a date) before any
   write or state-mutating action.

## Session-close ritual

Before signing off, produce two artifacts:

1. A new dated entry appended to `docs/PROGRESS_LOG.md` containing: what changed
   this window; current state vs. the remote; first-action options for the next
   window; open decisions; foot-guns to avoid; and an explicit `End of window`
   marker as the final line.
2. A paste-ready hand-off prompt as the last fenced block in that entry
   (reading order, current epic/issue, branch, last commit, next-action
   options, guardrails). Keep it under ~50 lines.

## Conventions (do not violate)

- ASCII-only everywhere (no smart quotes, em dashes, arrows).
- One PR per issue; branch from `donkey-kong-sandbox`; PR back into it.
- Conventional commit subjects (`feat:`, `fix:`, `docs:`, `chore:`,
  `test:`), imperative mood; the body explains WHY.
- Update `CHANGELOG.md` in any PR that changes behavior.
- `--json` `schema_version` is additive-only (see CONTRIBUTING.md).
- See CONTRIBUTING.md for the full Definition of Done.

## On-target scope guard (the project thesis)

The tool's thesis is **live, database-grounded root-cause analysis**. Two
standing rules protect it; reject work that breaks either, even if locally
tempting:

- **No static linting.** We deliberately removed the `lint`/`linters` package.
  Do not re-add static-analysis rules that duplicate sqlfluff /
  dbt_project_evaluator / dbt's own contract enforcement. The one allowed
  proactive check is the static grain-*consistency* cross-check (it checks a
  model's own declarations against each other, not generic style).
- **No ungated warehouse-scanning probes.** Tier-A ($0 metadata) probes may run
  freely; Tier-B (data-scanning: COUNT DISTINCT, anti-joins) must be gated by a
  cost ceiling and opt-in. A diagnostic that silently runs an expensive scan is
  a trust violation. See `docs/DESIGN_LIVE_VERIFICATION.md` section 3.1.

Every commit should trace: commit -> PR -> issue -> epic -> design doc.
