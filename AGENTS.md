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

1. Maintain exactly one dated entry per PR in `docs/PROGRESS_LOG.md`. Add it at
   session end if no entry exists for the PR; otherwise edit that PR entry in
   place. Keep all updates for the same PR in that single cohesive entry: what
   changed, current state vs. the remote, the next sensible steps, open
   decisions, and anything to be careful about. End the entry with an
   `End of session` marker.
2. Keep the entry short enough to skim cold.

## Conventions (do not violate)

- ASCII-only everywhere (no smart quotes, em dashes, arrows).
- One PR per issue; branch from `donkey-kong-sandbox`; PR back into it.
- Every implementation PR body must include exactly one GitHub auto-close line
  for the implemented issue, preferably `Closes #<issue>`. A bare `Issue: #N`,
  `Refs #N`, parent-epic reference, dependency reference, or related-issue
  reference is not enough. Keep close keywords limited to the implemented issue.
- Conventional commit subjects (`feat:`, `fix:`, `docs:`, `chore:`,
  `test:`), imperative mood; the body explains WHY.
- Update `CHANGELOG.md` (under `## [Unreleased]`) in any PR that changes
  behavior.
- `--json` `schema_version` is additive-only (see CONTRIBUTING.md).
- Distinguish public compatibility from internal cleanup. Additive-only applies to
  stable public JSON/artifact contracts within a major version; it is not a
  general instruction to keep obsolete internal code, duplicate helpers,
  wrappers, fixtures, docs, or tests.
- Prefer replacement or consolidation before adding a parallel implementation.
  Before adding a new helper, class, module, command, validator, fixture, or
  wrapper, identify the existing owner of that behavior and either modify it,
  replace it, or explain why no existing owner is safe to change.
- When a change supersedes an existing path, remove or simplify the obsolete
  branch, helper, fixture, docs section, or test in the same PR unless a
  documented compatibility, migration, rollback, or public-contract reason
  requires coexistence.
- Every implementation handoff must include a cleanup/deletion ledger:
  paths deleted or simplified, existing paths modified instead of duplicated,
  parallel paths intentionally retained, and why any low-deletion/high-addition
  diff was still appropriate.
- For nontrivial Python changes, especially validators, planners, JSON
  artifacts, command handlers, architecture boundaries, or
  compatibility-sensitive code, read `docs/CODE_STANDARDS.md` before editing.
  Prefer typed domain objects and small validator/builder classes for stable
  artifact shapes; keep raw `dict[str, Any]` handling at IO boundaries, keep
  domain logic independent of IO, and prove public JSON compatibility with
  tests.
- Any PR touching Python, governance artifacts, hooks, wrappers, JSON, policy,
  or CLI output must comply with `docs/CODE_STANDARDS.md` or explicitly call out
  the exact exception in the final report.
- For governance, Codex, hook, wrapper, policy, artifact, or CLI changes, list
  every consumer of each changed value before editing. A configurable value must
  either be honored by every consumer in the same PR or rejected at load time
  with a clear deferred-support error.
- Keep write-safety classification shared. GitHub mutation, unsafe shell, and
  read-only artifact boundaries must use one code-owned classifier or one shared
  test table across hooks, policy validation, packets, wrappers, and receipts.
- Prefer structured parsing over substring checks for commands, issue sections,
  official-doc fields, paths, URLs, and policy values. Regression tests must
  include negated wording, falsey malformed config, compound shell commands,
  dangerous text used as inert data, extensionless configured files, and
  disabled-but-retained sections when those cases apply.
- When implementation depends on third-party CLI or platform behavior, verify it
  from official docs or local `--help` output before coding and preserve the
  relevant semantics in tests.
- **Docs follow code, never lead it.** Design docs describe the target state
  and are annotated as such (e.g. "to be removed, tracked by #N") until the
  corresponding PR merges. `PROGRESS_LOG.md` is updated only after a PR
  merges or at session end -- never before. `CHANGELOG.md` is written in the
  PR itself (shipped with the code). No document may describe current state
  using past tense for work that has not yet landed on `donkey-kong-sandbox`.
- See CONTRIBUTING.md for the full Definition of Done and release process.

## Voice and authorship

All commits, PR descriptions, issues, code comments, CHANGELOG entries, and
docs are written in my own first-person voice, as an engineer documenting their
own work. Do not add automated-authorship markers of any kind (no "Generated
with ...", no `Co-Authored-By` trailers, no third-party attribution). Write
plainly and directly.

## Review guidelines

For Codex/GitHub reviews of protected Codex or governance changes, treat these
as high-priority review risks:

- packet-only and bounded-review input boundary drift;
- `.agents/skills/**` and `.codex/agents/**` instruction drift;
- `.codex/config.toml`, `.codex/agents/**`, hooks, wrappers, and policy
  semantic-scan coverage;
- forbidden GitHub comments/reviews/mutation paths from repo-local tooling;
- forbidden issue body/title/state writes, labels, milestones, Projects, workflow
  dispatches, PR merges, apply payloads, operation lists, request payloads, or
  anything consumable by `triage.py apply`;
- reviewer independence erosion, including
  same-context self-review being described as independent review;
- stale Codex GitHub review evidence that does not match the current PR head;
- path containment, non-UTF-8 filenames, JSON non-finite numbers, timestamp
  freshness, secret redaction around truncation boundaries, command execution,
  and read-only artifact integrity.

## Execution environments and agent notes

### Local Codex app (preferred for implementation)

- I use Codex from a real git clone or Codex-created worktree. The repository's
  `.codex` environment creates an isolated `.venv` and exposes credential-free
  setup, doctor, compile, test, and check commands.
- Codex must work only in the local checkout directory where the session
  started. Do not create or use external worktrees, alternate clones, or
  implementation directories outside this checkout unless I explicitly change
  this rule in a later instruction.
- I run `bash .codex/bin/action.sh doctor` at the start of a worktree and
  `bash .codex/bin/action.sh context <issue-number>` before issue work. The latter
  reads the live issue and local checkout without writing another stale cache.
- The default setup installs only development dependencies. I set
  `CODEX_INSTALL_LIVE=1` only for explicitly approved Snowflake work, and I do
  not run a live test merely because the connector is installed.
- I use the single controlled `.venv` that the `.codex` environment builds at
  the repository root. I do not point `CODEX_VENV_DIR` at an alternate or
  temporary virtual environment, and I do not spin up ad-hoc venvs to test other
  Python versions. Local runs use that one `.venv`; multi-version (3.11/3.12)
  coverage is CI's responsibility, not a local Codex action.
- I treat GitHub metadata commands as read-only unless the task explicitly
  authorizes mutations. One metadata-writer session owns an approved batch.
- A direct maintainer request in the current chat may delegate one exact GitHub
  operator action, including applying an approved `proposed-body.md`, only
  outside issue-governance/issue-work outputs, triage artifacts, plans, and
  allowlists. Before running it, restate the target, command, and artifact;
  receive explicit approval; run only that command; verify; report.
- Local Codex can edit workflow files in the checkout, but workflow, secret,
  environment, release, and branch-protection changes still require maintainer
  review and the appropriate GitHub permissions.

### Legacy Snowsight/Cortex coding agent

- The GitHub API token used by that coding agent CANNOT modify files under
  `.github/workflows/*` (the token lacks the `workflows` permission). Any push
  touching a workflow file fails with 404/403. When CI config must change, the
  agent hands the maintainer the new `ci.yml` content to commit by hand.
- That workspace is a Snowsight Workspace (a git-backed stage), not a local
  clone, and the agent has no local `git` remote. It operates on GitHub via the
  API (get/create/update file, push_files, PRs). Do not assume uncommitted
  changes carry across a branch switch in the UI; commit or push first.
- That environment auto-injects an authorship marker ("Co-authored with CoCo")
  into code files. This repo's voice rule forbids it, so the agent strips the
  marker before pushing. The CI guard rejects the marker on
  `*.py`/`*.sql`/`*.ipynb` as a backstop.

## Issue governance (read-only; pointer)

This is the only file Codex always loads, so the non-negotiable governance rules
live here even when no skill is invoked:

- The triage toolchain (`scripts/triage/`) and its skills are **read-only**. They
  audit, score, draft, and plan; they never create, edit, close, label,
  milestone, or move a GitHub item, and no plan or allowlist may add an
  issue-body write. The maintainer applies any change outside the triage
  toolchain; a current-session direct operator delegation is allowed only under
  the Local Codex app rules above.
- Per-issue runs handle **one issue at a time**; the per-issue `issue-governance`
  skill never reasons across issues. Cross-issue judgment (deduplication,
  splitting, merging, ordering, project structure) is reserved for a dedicated,
  read-only cross-issue synthesis pass that emits candidate verdicts with
  evidence for the maintainer to act on. Today that pass is the maintainer; a
  planned `backlog-synthesis` skill (target state, tracked by #81 under epic #85)
  will perform it once it lands. Like the rest of the toolchain it never creates,
  edits, closes, labels, milestones, or moves a GitHub item; the maintainer
  applies any verdict by hand.
- Every source claim in issue text or evidence carries a content anchor
  (`path:symbol` or `path "snippet"`), never a bare `path:line`. Do not invent a
  symbol, line, or snippet to satisfy a section.
- For the full lifecycle use the `issue-governance` skill and
  `docs/ISSUE_GOVERNANCE.md` / `docs/ISSUE_CONTRACT_V1.md`. These are loaded on
  demand, not automatically.

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
