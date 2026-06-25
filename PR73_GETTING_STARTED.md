# PR #73 getting started

I use this guide for the issue-governance and relay command surface completed in
PR #73. The commands are repository tools; I run them from the repository root.

## Command overview

The CLI exposes eight commands:

```text
snapshot
audit
plan
apply
contract
review-packet
standardize
frontier
```

The actual help output is available with:

```bash
python scripts/triage/triage.py --help
python scripts/triage/triage.py <command> --help
```

Global options such as `--policy` and `--repo` go before the command name.

## 1. Snapshot

`snapshot` reads tracker metadata and writes a digest-bound local snapshot.
It is the only governance command whose normal form needs live GitHub reads.

```bash
python scripts/triage/triage.py snapshot \
  --output output/triage/snapshot.json
```

This command requires a working read-only `gh` identity. It does not call a
GitHub write endpoint.

## 2. Audit

`audit` combines contract/readiness analysis with the existing metadata
findings and emits one digest-bound document that `frontier` can consume
without conversion.

Live form:

```bash
python scripts/triage/triage.py audit \
  --output output/triage/audit.json
```

Offline form:

```bash
python scripts/triage/triage.py audit \
  --snapshot output/triage/snapshot.json \
  --output output/triage/audit.json \
  --json
```

A local semantic-evidence file can be included with
`--semantic-evidence PATH`. `--issues 54,55` limits issue-level output while
retaining repository-wide findings.

## 3. Contract

`contract` audits exactly one issue against issue contract v1.

```bash
python scripts/triage/triage.py contract --issue 54 \
  --snapshot output/triage/snapshot.json \
  --json
```

The result includes the inferred issue kind, governance state, acceptance
coverage, findings, and body digest. The offline form makes no GitHub call.

## 4. Review packet

`review-packet` packages one bounded issue context for local review.

```bash
python scripts/triage/triage.py review-packet --issue 54 \
  --snapshot output/triage/snapshot.json \
  --semantic-evidence output/triage/semantic-evidence.json \
  --output-dir output/triage/issues/54
```

It writes:

```text
output/triage/issues/54/review-packet.json
output/triage/issues/54/contract.json
output/triage/issues/54/proposed-body.md
```

The packet contains the selected issue, direct dependencies, issue-specific
parent excerpts, referenced paths, checked source/test entry points,
uncertainty, and verification commands. It excludes unrelated issue bodies.
The issue body is capped at 30,000 characters and historical progress context
at 4,000 characters; truncation is recorded explicitly.

## 5. Standardize

`standardize` validates a proposed issue body and packages it locally.

```bash
python scripts/triage/triage.py standardize --issue 54 \
  --snapshot output/triage/snapshot.json \
  --proposed-body output/triage/issues/54/proposed-body.md \
  --output-dir output/triage/issues/54 \
  --json
```

It writes the exact proposed text plus `standardization.json`. The command
rejects non-ASCII proposed text. It does not edit GitHub, and issue-body updates
remain forbidden operations.

## 6. Plan

`plan` derives only allowlisted metadata operations and writes an approval-bound
bundle.

```bash
python scripts/triage/triage.py plan \
  --snapshot output/triage/snapshot.json \
  --semantic-evidence output/triage/semantic-evidence.json \
  --output-dir output/triage
```

It writes:

```text
output/triage/snapshot.json
output/triage/audit.json
output/triage/plan.json
output/triage/plan.md
output/triage/approval.template.json
```

The approval template approves nothing. The plan digest changes whenever an
operation, target, request, batch, or precondition changes.

## 7. Frontier

`frontier` has two deterministic modes.

Audit mode selects the highest-value issue still needing governance,
standardization, or semantic review:

```bash
python scripts/triage/triage.py frontier --mode audit \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --json
```

Implementation mode selects only a contract-accepted issue whose implementation
state is `ready`:

```bash
python scripts/triage/triage.py frontier --mode implement \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --json \
  --packet-output output/triage/frontier-worker-packet.json
```

Implementation mode rejects open dependencies, missing merge evidence, cycles,
maintainer decisions, required external evidence, missing repository paths,
active pull request conflicts, overlap conflicts, stale state, and other
readiness blockers.

Ties use the issue number, so identical inputs produce identical coordinator
JSON and digests. I can request an explicit empty result with either form:

```bash
python scripts/triage/triage.py frontier --mode implement \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --empty-selection --json

python scripts/triage/triage.py frontier --mode implement \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --issues none --json
```

An empty frontier returns `selected_issue: null` and does not write a worker
packet. The CLI validates coordinator identity fields, digest formats, types,
bounds, and canonical digest before writing output.

## 8. Apply

`apply` retains the existing approval and execution gates. Dry-run performs a
live read-only preflight and never sends a write request:

```bash
python scripts/triage/triage.py apply --dry-run \
  --plan output/triage/plan.json \
  --approval output/triage/approval.json \
  --plan-sha <exact-plan-sha256> \
  --batch bootstrap
```

Execute mode additionally requires all of the following:

- an exact plan digest in the plan, command, and approval;
- explicit approval of the selected batch and operation IDs;
- exact `--confirm-repo owner/name` confirmation;
- `TRIAGE_ENABLE_GITHUB_WRITES=1`;
- an exclusive local writer lock;
- live preflight and just-in-time verification;
- post-write desired-state verification;
- an execution receipt.

The mutation allowlist remains exactly:

```text
issue.labels.add
issue.labels.remove
issue.milestone.set
issue.milestone.clear
```

Issue creation, closure, title/body updates, label-definition changes,
milestone-definition changes, and Project mutation remain forbidden.

## Codex wrappers

The stable read-only wrappers are:

```bash
bash .codex/bin/action.sh audit --snapshot output/triage/snapshot.json
bash .codex/bin/action.sh frontier audit \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json --json
bash .codex/bin/action.sh frontier implement \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json --json
```

The wrapper validates its mode and dispatches to the same Python CLI. It does
not create a branch, worktree, Codex thread, or GitHub mutation.

## Troubleshooting

### `gh` is unavailable

Use a previously captured snapshot and pass `--snapshot` to `audit`, `plan`,
`contract`, `review-packet`, `standardize`, and `frontier`. Snapshot collection
and `apply --dry-run` still require live read access.

### Snapshot or audit digest mismatch

Use the snapshot and audit from the same run. A changed policy, snapshot,
issue body, or audit payload invalidates the old digest by design.

### Implementation frontier is empty

Inspect `rejected_preview`, issue implementation states, blockers, dependency
merge evidence, decisions, external evidence, paths, and active pull request
conflicts. Do not substitute a fallback issue.

### No worker packet was written

A packet is written only when `selected_issue` is an integer. An explicit or
naturally empty frontier writes no packet.

### Proposed body is rejected

Keep repository-authored text ASCII-only and satisfy the issue-kind contract.
Run `contract` first to see missing sections and acceptance coverage.

### Dry-run reports stale preconditions

Refresh the snapshot and regenerate the plan and approval. Do not reuse an old
approval after the plan digest or live issue metadata changes.
