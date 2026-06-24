# Issue governance

I use this tooling to inspect the live GitHub tracker, detect metadata drift, and
produce an approval-bound plan before any metadata write is considered.

The normal workflow is read-only:

```bash
python scripts/triage/triage.py snapshot
python scripts/triage/triage.py audit
python scripts/triage/triage.py plan --output-dir output/triage
```

The tool does not create issues, rewrite issue bodies, close issues, create
labels, create milestones, create Projects, or change repository settings.

## Source of truth

The tool follows this order:

1. Live GitHub issue, pull-request, label, milestone, and configured Project
   metadata.
2. `scripts/triage/policy.toml` for stable process rules and explicitly approved
   desired metadata.
3. Repository files for path checks and `docs/PROGRESS_LOG.md` drift checks.

The policy is not a mirror of the tracker. I do not copy issue titles or bodies
into it. Live metadata is captured in a timestamped snapshot and bound to the
plan with SHA-256 digests.

`docs/PROGRESS_LOG.md` is historical context, not a substitute for the live
tracker. The audit reports when tracker updates are newer than its latest dated
entry or when a declared-open item is already closed.

## Command surface

### Snapshot

```bash
python scripts/triage/triage.py snapshot
python scripts/triage/triage.py snapshot \
  --output output/triage/snapshot.json
```

A snapshot contains:

- all issues and pull requests returned by the repository tracker endpoint;
- expanded metadata for open pull requests;
- labels and label usage;
- milestones and assignment counts;
- closed tracker items referenced by open issues;
- recently closed tracker items;
- configured GitHub Project V2 metadata, when an exact Project identity is
  enabled in policy;
- a content digest that excludes only the generation timestamp.

Snapshot collection uses GitHub REST GET requests and an optional read-only
GraphQL Project query. It does not perform a write.

### Audit

```bash
python scripts/triage/triage.py audit
python scripts/triage/triage.py audit --issues 54,68
python scripts/triage/triage.py audit --json
python scripts/triage/triage.py audit \
  --snapshot output/triage/snapshot.json
```

The audit checks, subject to policy flags:

- case-insensitive duplicate labels;
- labels named in policy but absent from the live repository;
- title-prefix and label alignment;
- missing issue or pull-request references;
- unchecked checklist entries that point at closed tracker items;
- dependencies that point at already closed tracker items;
- referenced repository paths that do not exist in the checkout;
- dependency cycles using only dependency-bearing relationship headings;
- release-gate issue milestone assignments;
- open pull-request base branches;
- configured Project visibility;
- progress-log date and declared-state drift.

`--issues` filters issue-specific findings. Repository-wide findings still
print because they can affect the selected issues.

An audit exits nonzero only when it finds an error. Warnings are review items,
not an automatic write instruction.

### Plan

```bash
python scripts/triage/triage.py plan --output-dir output/triage
python scripts/triage/triage.py plan \
  --snapshot output/triage/snapshot.json \
  --output-dir output/triage
```

The plan command writes:

```text
output/triage/snapshot.json
output/triage/audit.json
output/triage/plan.json
output/triage/plan.md
output/triage/approval.template.json
```

Every operation has:

- a deterministic operation ID;
- a batch;
- an exact repository and issue target;
- before and after metadata;
- live preconditions;
- an exact REST method, path, and JSON body;
- a reason;
- a destructive flag.

The plan SHA-256 covers the complete normalized plan. Editing an operation,
target, request, batch, or precondition changes the digest and invalidates an
existing approval.

The generated approval template approves no batch and no operation.

## Supported and forbidden operations

The initial writer allowlist is intentionally narrow:

```text
issue.labels.add
issue.labels.remove
issue.milestone.set
issue.milestone.clear
```

The planner and validator reject, among other things:

```text
issue.create
issue.close
issue.reopen
issue.body.update
issue.title.update
label.create
label.delete
label.rename
milestone.create
milestone.close
project.create
```

Issue text is not a supported mutation payload. GitHub request bodies are JSON
sent through standard input to `gh api`; issue text and other metadata are never
interpolated into a shell command.

## Batches

`policy.toml` assigns selected issue numbers to `bootstrap`, `canary`, or
`remaining`. Unlisted operations use `planning.default_batch`.

Batches are review units, not approval. An approval file must name both the
batch and each operation ID that is authorized. An approval may cover several
batches, but one invocation processes only the selected batch.

## Approval and dry run

Copy the template to a separate file and fill only the approved values:

```json
{
  "schema_version": 1,
  "repository": "dckallos/dbt-diagnostics",
  "plan_sha256": "<exact plan digest>",
  "approved_batches": ["bootstrap"],
  "approved_operation_ids": ["op1:<exact operation digest>"],
  "allow_destructive": false,
  "approved_by": "<maintainer>",
  "approved_at": "<UTC timestamp>"
}
```

Then run the mandatory read-only preflight:

```bash
python scripts/triage/triage.py apply --dry-run \
  --plan output/triage/plan.json \
  --approval output/triage/approval.json \
  --plan-sha <sha> \
  --batch bootstrap
```

Dry run reads each live issue again. It reports an operation as:

- `ready` when its relevant preconditions still match;
- `noop` when the desired metadata is already present;
- `stale` when the issue state or relevant metadata changed;
- `unsupported` when the operation is outside the allowlist.

Any stale or unsupported operation blocks the batch. Dry run never calls a
GitHub write endpoint.

## Real execution gate

A real writer session is deliberately harder to invoke:

```bash
TRIAGE_ENABLE_GITHUB_WRITES=1 \
python scripts/triage/triage.py apply --execute \
  --plan output/triage/plan.json \
  --approval output/triage/approval.json \
  --plan-sha <sha> \
  --batch bootstrap \
  --confirm-repo dckallos/dbt-diagnostics
```

All of these must agree:

- embedded plan digest;
- command-line plan digest;
- approval plan digest;
- repository in the plan and approval;
- approved batch;
- approved operation IDs;
- destructive-operation permission;
- exact `--confirm-repo` value;
- `TRIAGE_ENABLE_GITHUB_WRITES=1`;
- live preflight state.

The writer uses an exclusive lock and verifies each desired state after the
request. A successful run writes a receipt under `output/triage/receipts/` by
default. The lock prevents two local writer sessions from running at once; it
does not replace live preconditions.

I do not enable the write gate in ordinary Codex setup or actions.

## GitHub authentication

Snapshot, audit, plan, and apply preflight use the local `gh` identity. The
credential-free repository setup does not log in, load a token, or change GitHub
configuration.

Use:

```bash
gh auth status
```

before a live snapshot. The selected identity needs read access to the tracker.
A real execute session additionally needs the exact issue-write permissions for
the approved operations.

## Project metadata

Project auditing remains disabled until `policy.toml` records an exact owner,
owner type, and Project number. Enabling it adds a read-only GraphQL snapshot.
The tool does not create a Project or mutate Project fields.

## Policy changes

A policy change is reviewable code. In particular:

- adding `[[desired.issue]]` is an explicit desired-state decision;
- changing the release milestone changes which assignments are proposed;
- changing epic headings changes release-gate derivation;
- changing batch membership changes rollout grouping, not desired metadata;
- enabling Project reads requires an exact Project identity.

Run the focused tests after every change:

```bash
pytest -q scripts/triage/test_triage.py
python -m compileall -q scripts/triage
```

The default pytest configuration includes these tests.
