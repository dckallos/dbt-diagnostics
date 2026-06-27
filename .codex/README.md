# Local Codex environment

This repository checks in a Codex environment so every Codex-created worktree
starts from the same safe baseline. Setup and default actions are
credential-free. They do not load `.env`, parse a dbt profile, import the
Snowflake connector, or run a warehouse query.

The Codex app reads `.codex/environments/environment.toml`. That file stays
small; one stable dispatcher owns the command surface:

```bash
bash .codex/bin/action.sh help
```

## Local prerequisites

- A real git clone of `dckallos/dbt-diagnostics`.
- Python 3.11 or newer. Python 3.12 is preferred because it matches current CI.
- `git`.
- GitHub CLI (`gh`) for live issue context and governance snapshots.

For issue and Project work, authenticate locally:

```bash
gh auth login
gh auth refresh -h github.com -s project
gh auth status
```

No GitHub credential is needed to install dependencies or run offline tests.

## Setup

Codex runs the setup script when it creates a new worktree. Manual invocation is
also supported:

```bash
bash .codex/bin/action.sh setup
bash .codex/bin/action.sh doctor
```

Setup performs the following work:

1. Prefers Python 3.12, then 3.11, with newer stable Python versions as fallbacks.
2. Creates an isolated `.venv` in the worktree.
3. Installs this package editable with the `dev` extra.
4. Installs only Codex development tools listed in
   `.codex/requirements-tools.txt`.
5. Runs `pip check`, verifies the installed CLI, and compiles repository Python.
6. Uses a dependency fingerprint and process lock, making repeated and
   concurrent setup safe.
7. Recreates only a Codex-managed environment when Python or live-extra mode
   changes; a user-managed virtual environment is never deleted.

Live dependencies are opt-in:

```bash
CODEX_INSTALL_LIVE=1 bash .codex/bin/action.sh setup
```

Installing live dependencies does not authorize a live test. A real Snowflake
run still requires an issue that calls for it, explicit maintainer approval,
least-privileged credentials, and the issue's bounded test plan.

## App actions

| Action | Stable command | Purpose |
| --- | --- | --- |
| Context | `bash .codex/bin/action.sh context [issue]` | Combine a live issue with branch, worktree, referenced paths, and the latest progress entry. |
| Doctor | `bash .codex/bin/action.sh doctor` | Check Python, venv, dependencies, git, GitHub CLI, and known release-gate prerequisites without mutation. |
| Check | `bash .codex/bin/action.sh check` | Validate the Codex command layer, git hygiene, ASCII/authorship guards, compilation, fast offline tests, and compatibility gate. |
| Tests (offline) | `bash .codex/bin/action.sh offline` | Run every test not marked `live`, including the chaos tier. |
| Full pytest | `bash .codex/bin/action.sh full` | Run the exact repository command `pytest -q`. |
| Compile | `bash .codex/bin/action.sh compile` | Force-compile package, tests, scripts, and Codex helpers. |
| Issue audit | `bash .codex/bin/action.sh audit [--issues N,...]` | Read live tracker metadata and run the issue-governance audit. |
| Package | `bash .codex/bin/action.sh package` | Build one wheel and sdist, inspect them, install the wheel, and smoke-test the CLI. |

The Issue audit action is read-only. It requires a local `gh` identity but never
calls a GitHub write endpoint. Additional governance shell actions are exposed
through the stable dispatcher without adding app-menu buttons: `frontier` and
`project-plan`.

## Local hooks

This repository includes project-local Codex hooks in `.codex/hooks.json`.
Codex loads them only after the project `.codex/` layer is trusted. Review and
trust changed hooks with `/hooks` before relying on them.

The hook commands delegate to `.codex/hooks/run_hook.sh`. The launcher resolves
the git root, requires the repository-controlled interpreter, and then runs the
selected hook script:

```bash
.codex/hooks/run_hook.sh <hook>.py <EventName>
```

If the git root, `.venv/bin/python`, or hook script is unavailable, the
launcher emits valid event-specific hook JSON and fails closed for the
operation being evaluated.

The commands in `.codex/hooks.json` also resolve the git root before invoking
the launcher, because Codex may run hooks from the session working directory
rather than the repository root. If that first root lookup fails before the
launcher can run, the configured command emits event-specific fail-closed JSON
itself.

They are local safety checks only:

- `PreToolUse` blocks direct GitHub metadata mutation commands and known unsafe
  command shapes before tool execution.
- `PermissionRequest` denies escalation for known unsafe command shapes.
- `Stop` blocks finalization when protected Codex or governance files changed
  without a digest-valid, passing `output/codex/quality-receipt.json` whose
  deterministic `freshness_bound_protected_paths` field includes every changed
  protected path. The receipt must also be newer than those protected files.

Hooks inspect the hook payload, command text, local git status, and the local
quality receipt. They do not run live Snowflake, call GitHub write endpoints,
or inspect secrets. Hook failures emit valid JSON and fail closed for the
operation being evaluated.

The normal `codex-quality` action records two protected-path fields:

- `semantically_checked_protected_paths` lists protected files that were
  actually scanned by deterministic quality checks.
- `freshness_bound_protected_paths` lists existing protected files from local
  git status, or from explicit `--path` values in targeted runs, that are bound
  to the receipt timestamp. This field proves `codex-quality` ran after those
  paths changed; it does not claim the files were semantically scanned.

## Issue governance workflow

The full planning surface is available directly:

```bash
python scripts/triage/triage.py snapshot
python scripts/triage/triage.py snapshot \
  --output output/triage/snapshot.json
python scripts/triage/triage.py audit
python scripts/triage/triage.py audit --issues 54,68
python scripts/triage/triage.py contract --issue 54
python scripts/triage/triage.py review-packet --issue 54 \
  --output-dir output/triage/issues/54
python scripts/triage/triage.py standardize --issue 54 \
  --proposed-body output/triage/issues/54/proposed-body.md \
  --output-dir output/triage/issues/54
python scripts/triage/triage.py plan --output-dir output/triage
python scripts/triage/triage.py project-plan \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json --json
python scripts/triage/triage.py backlog-synthesis \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json --json
python scripts/triage/triage.py frontier --mode audit --json
python scripts/triage/triage.py frontier --mode implement --json
```

For credential-free use, pass `--snapshot output/triage/snapshot.json` to the
commands that inspect tracker state. `audit.json` written by `plan` can be
passed directly to `frontier --audit-file`, `project-plan --audit-file`, or
`backlog-synthesis --audit-file`. An `audit --issues ... --output` file is
partial; use it only with a matching scoped frontier, not with full
`project-plan` or `backlog-synthesis` artifacts.

`plan` writes a normalized snapshot, a full readiness audit, a digest-bound
metadata plan, a human-readable summary, and an approval template that approves
nothing. `contract`, `review-packet`, and `standardize` write local files only.

The stable read-only governance wrappers are:

```bash
bash .codex/bin/action.sh frontier audit --json
bash .codex/bin/action.sh frontier implement --json
bash .codex/bin/action.sh project-plan \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json --json
```

An empty implementation frontier is valid and reports `selected_issue: null`.
These wrappers do not create a branch, worktree, Codex thread, or GitHub
mutation.

A later approved session must run a live read-only preflight before a metadata
write is eligible:

```bash
python scripts/triage/triage.py apply --dry-run \
  --plan output/triage/plan.json \
  --approval output/triage/approval.json \
  --plan-sha <sha> \
  --batch bootstrap
```

Issue creation, issue closure, issue-body updates, label-definition changes,
milestone-definition changes, Project creation, and Project mutation are not
supported operations. See `docs/ISSUE_GOVERNANCE.md` for the complete approval
and execution gates.

## Starting issue work without stale context

Run this before editing:

```bash
bash .codex/bin/action.sh context 54
bash .codex/bin/action.sh context 54 --comments
bash .codex/bin/action.sh context 54 --json
```

The command is read-only and writes no context cache. It combines the current
GitHub issue with local branch and worktree state, repository paths named by the
issue, and the latest dated progress-log entry. With no issue argument, it
infers an issue number from a branch such as `fix/54-object-unavailable`; when
no issue can be inferred, it prints local context and the next safe command.

## Test and release utilities

```bash
# Normal implementation gate: excludes live and high-volume chaos tests.
bash .codex/bin/action.sh fast

# Every credential-free test, including chaos.
bash .codex/bin/action.sh offline

# Exact current repository test command.
bash .codex/bin/action.sh full

# Focused marker or file runs.
bash .codex/bin/test.sh contract
bash .codex/bin/test.sh -q dbt_diagnostics/tests/test_runtime_error.py

# Re-run only previous credential-free failures.
bash .codex/bin/action.sh last-failed

# Run the compatibility schema gate by itself.
bash .codex/bin/action.sh compat

# Build and verify installable artifacts.
bash .codex/bin/action.sh package
```

## Overrides

- `CODEX_PYTHON=/path/to/python3.12`: choose the bootstrap interpreter.
- `CODEX_VENV_DIR=/path/to/venv`: use a different virtual-environment path.
- `CODEX_INSTALL_LIVE=1`: install the `dev,live` extras.
- `CODEX_SETUP_FORCE=1`: refresh dependencies even when the fingerprint matches.
- `CODEX_GITHUB_REPO=dckallos/dbt-diagnostics`: identify the repository when no
  usable `origin` remote exists.
- `CODEX_ISSUE=54`: provide the issue number for the Context action.

The root `AGENTS.md` remains authoritative for scope, voice, issue and PR
traceability, CHANGELOG behavior, JSON compatibility, and Tier-A/Tier-B rules.
