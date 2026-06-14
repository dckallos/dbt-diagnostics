# Project conventions and working notes

> Start here. This is the cheapest read in the repo and points to everything
> else. It captures how I work on this project so I can pick the work back up
> cleanly between sessions.

## Operating principle

The repository is the source of truth; notes in a chat or terminal are
disposable. Any decision that matters gets written down here, on the relevant
issue, or in a doc before I move on -- so the state of the project can always be
reconstructed from the repo alone.

Source-of-truth hierarchy (one fact lives in exactly one place):

1. **This file** -- conventions and where to look.
2. **docs/PROGRESS_LOG.md** -- the append-only progress trail. The newest dated
   entry is the current state.
3. **The epic issue** (GitHub) -- the live status board for a body of work.
4. **The design doc** under `docs/` -- the spec for that body of work.
5. **PRs / commits / CHANGELOG.md** -- the work itself and what shipped.

## Reading order

1. This file.
2. The latest entry in `docs/PROGRESS_LOG.md`.
3. The epic issue named in that entry.
4. The one design doc relevant to the task (e.g.
   `docs/DESIGN_LIVE_VERIFICATION.md`).
5. Source files -- only to edit, or when a doc points to them.

Stop reading once there is enough to act.

## Resuming work

1. Pull the latest `donkey-kong-sandbox` before starting.
2. Read the latest `docs/PROGRESS_LOG.md` entry to see where things stand.
3. Decide the next step and confirm scope before any write.

## Wrapping up

Before stopping, leave the repo resumable:

1. Append a new dated entry to `docs/PROGRESS_LOG.md`: what changed, current
   state vs. the remote, the next sensible steps, open decisions, and anything
   to be careful about. End it with an `End of session` marker.
2. Keep the entry short enough to skim cold.

## Conventions (do not violate)

- ASCII-only everywhere (no smart quotes, em dashes, arrows).
- One PR per issue; branch from `donkey-kong-sandbox`; PR back into it.
- Conventional commit subjects (`feat:`, `fix:`, `docs:`, `chore:`,
  `test:`), imperative mood; the body explains WHY.
- Update `CHANGELOG.md` (under `## [Unreleased]`) in any PR that changes
  behavior.
- `--json` `schema_version` is additive-only (see CONTRIBUTING.md).
- See CONTRIBUTING.md for the full Definition of Done and release process.

## Voice and authorship

All commits, PR descriptions, issues, code comments, CHANGELOG entries, and
docs are written in my own first-person voice, as an engineer documenting their
own work. Do not add automated-authorship markers of any kind (no "Generated
with ...", no `Co-Authored-By` trailers, no third-party attribution). Write
plainly and directly.

## Scope guard (the project thesis)

The tool's purpose is **live, database-grounded root-cause analysis**. Two
standing rules protect that focus; reject work that breaks either, even if it
looks convenient:

- **No static linting.** The `lint`/`linters` package was removed on purpose.
  Do not re-add static-analysis rules that duplicate sqlfluff,
  dbt_project_evaluator, or dbt's own contract enforcement. The one allowed
  proactive check is the static grain-*consistency* cross-check (it checks a
  model's own declarations against each other, not generic style).
- **No ungated warehouse-scanning probes.** Tier-A ($0 metadata) probes may run
  freely; Tier-B (data-scanning: COUNT DISTINCT, anti-joins) must be gated by a
  cost ceiling and opt-in. A diagnostic that silently runs an expensive scan is
  a trust violation. See `docs/DESIGN_LIVE_VERIFICATION.md` section 3.1.

Every commit should trace: commit -> PR -> issue -> epic -> design doc.
