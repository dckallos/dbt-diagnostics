# Branch-protection governance

This directory is the version-controlled source of truth for the GitHub
branch-protection policy on `dckallos/dbt-diagnostics`. The policy is applied
from a maintainer's local terminal with `gh`; nothing here runs in CI or from
the agent. Keeping the bodies and scripts in the repo means the policy can be
reviewed, diffed, and rolled back like any other change.

Tracking issue: #30.

## What the policy is

Both `donkey-kong-sandbox` (default / integration) and `main` (release) get the
same classic branch-protection config (`policy.<branch>.json`):

- Require a pull request before merging (`required_approving_review_count: 0`).
- Require the `test` status check to pass, and be up to date (`strict: true`).
- Require linear history (matches the squash-merge convention).
- Require conversation resolution before merging.
- Block force pushes and branch deletion.
- `enforce_admins: false` -- the repo owner keeps a break-glass path.
- `restrictions: null` -- push-restriction lists are org-only; not applicable to
  a user repo.

### Why the two branches are identical

This is a solo-maintained repo. A non-zero required-approval count would
deadlock the only maintainer (you cannot approve your own PR), and with
`enforce_admins: false` an admin bypasses approvals anyway. So review-count
asymmetry between `main` and `donkey-kong-sandbox` would be cosmetic. The
protections that actually bite -- PR required, CI green, linear history, no
force-push, no deletion -- apply equally to both.

`main` still matters because promoting `donkey-kong-sandbox -> main` is the
release event (version bump + PyPI publish, at the maintainer's choice). Keeping
identical guardrails on `main` ensures a release can only land through a green
PR. The files are kept separate so `main` can diverge later (e.g. enabling
`required_signatures` or `require_last_push_approval`) without touching the
integration branch.

## Prerequisites

- `gh` authenticated as a repo admin: `gh auth login`.
- `jq` (used by the export script to pretty-print snapshots).

## Usage

Dry-run first -- prints the target and JSON body, changes nothing:

```
./scripts/governance/apply-branch-protection.sh --dry-run
```

Apply to both branches (auto-exports the current state first):

```
./scripts/governance/apply-branch-protection.sh
```

Apply to one branch only:

```
./scripts/governance/apply-branch-protection.sh --branch main
```

Snapshot the current live policy into `exports/` (the committed before-state):

```
./scripts/governance/export-branch-protection.sh
```

Roll back to the last snapshot (deletes protection if the branch was previously
unprotected, otherwise restores the saved config):

```
./scripts/governance/rollback-branch-protection.sh --dry-run   # preview
./scripts/governance/rollback-branch-protection.sh
```

## Files

- `policy.donkey-kong-sandbox.json` -- protection body for the integration branch.
- `policy.main.json` -- protection body for the release branch.
- `apply-branch-protection.sh` -- idempotent apply (`PUT` replaces the whole
  config); exports current state before changing anything.
- `export-branch-protection.sh` -- write current live protection to
  `exports/<branch>.json`; records `null` when a branch is unprotected.
- `rollback-branch-protection.sh` -- restore from `exports/`.
- `exports/` -- generated before-state snapshots (created on first run).

## exports/ vs policy files

Two kinds of JSON live here and must not be confused:

- `policy.<branch>.json` -- the DESIRED state. Editing one of these and
  re-applying is how you change the live policy.
- `exports/<branch>.json` -- a HISTORICAL before-state snapshot written by the
  apply/export scripts. `null` means the branch was unprotected at snapshot
  time. Rollback restores whatever is in the snapshot; a snapshot never defines
  policy. Do not hand-edit a snapshot to change rules -- edit the matching
  `policy.<branch>.json` instead.

A snapshot is only trustworthy if it was taken with working admin credentials.
If `gh` auth is broken when a snapshot is written, treat that `exports/` file as
suspect and re-run `export-branch-protection.sh` once `gh auth status` is green.

## Changing the policy

Edit the relevant `policy.<branch>.json`, open a PR into
`donkey-kong-sandbox`, and after merge run `apply-branch-protection.sh`. The PR
is the review record; the apply step makes the live repo match what merged.
