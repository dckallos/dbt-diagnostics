# Issue governance

I use this tooling to inspect the live GitHub tracker, detect metadata drift, and
produce an approval-bound plan before any metadata write is considered.

The normal workflow is read-only:

```bash
python scripts/triage/triage.py snapshot
python scripts/triage/triage.py audit
python scripts/triage/triage.py contract --issue 54
python scripts/triage/triage.py review-packet --issue 54 \
  --output-dir output/triage/issues/54
python scripts/triage/triage.py standardize --issue 54 \
  --proposed-body output/triage/issues/54/proposed-body.md \
  --output-dir output/triage/issues/54
python scripts/triage/triage.py backlog-synthesis \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --output output/triage/backlog-synthesis.json
python scripts/triage/triage.py synthesis-review-packet \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --backlog-synthesis output/triage/backlog-synthesis.json \
  --output output/triage/synthesis-review-packet.json
python scripts/triage/triage.py backlog-review-validate \
  --packet output/triage/synthesis-review-packet.json \
  --verdict output/triage/backlog-review-verdict.json \
  --json
python scripts/triage/triage.py plan --output-dir output/triage
python scripts/triage/triage.py project-plan \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json --json
python scripts/triage/triage.py frontier --mode audit --json
python scripts/triage/triage.py frontier --mode implement --json
```

The tool does not create issues, rewrite issue bodies, close issues, create
labels, create milestones, create Projects, or change repository settings.

## Quick start

The stable wrappers under `.codex/bin/` run the same commands with the repo's
virtualenv and route status to stderr, so `--json` stdout stays valid JSON.

```bash
# One-time: create the credential-free virtualenv the wrappers use.
bash .codex/bin/setup.sh

# Read-only audit of the whole tracker (live; needs an authenticated gh).
bash .codex/bin/action.sh audit --json | jq .
bash .codex/bin/action.sh audit                       # human-readable

# Audit only specific issues.
bash .codex/bin/action.sh audit --issues 68,69,70,54 --json \
  | jq '.issues[] | {issue_number, governance_state, implementation_state}'

# Capture a snapshot once, then audit it offline (no further GitHub reads).
python scripts/triage/triage.py snapshot --output output/triage/snapshot.json
bash .codex/bin/action.sh audit --snapshot output/triage/snapshot.json --json

# Frontier selection (read-only).
bash .codex/bin/action.sh frontier audit --json | jq '{selected_issue, candidates}'
python scripts/triage/triage.py plan --snapshot output/triage/snapshot.json \
  --output-dir output/triage/plan
bash .codex/bin/action.sh frontier implement \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/plan/audit.json --json

# Advisory Project layout (read-only).
bash .codex/bin/action.sh project-plan \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/plan/audit.json --json
```

Notes:

- `snapshot` and a live `audit` read the tracker through `gh`; without `gh` on
  the PATH they fail, so generate the snapshot where `gh` is available and use
  the `--snapshot` path elsewhere.
- The implementation frontier requires the readiness audit to cover every issue
  it will rank. A partial `--audit-file` built with `--issues` is rejected
  unless `frontier` is run with the same `--issues` scope.
- These commands never mutate GitHub. The only write path is `apply`, which
  additionally requires `--execute`, an exact-repository confirmation, and
  `TRIAGE_ENABLE_GITHUB_WRITES=1`.

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

`scripts/triage/repo_config.py` is the typed adapter boundary for the
repository-local parts of that policy. It validates `policy.toml` and supplies
repository identity, the default and protected branches, progress-log path,
contract ID/version, path citation roots, protected Codex/governance surfaces,
hook wiring, quality receipt path, product/package checks, compatibility schema
sets, official-documentation provider policy, and worker-packet verification
commands to the local tooling.

Policy configuration is not an authorization model. It cannot add issue bodies,
request payloads, operation plans, PR merge instructions, workflow dispatches,
or tracker mutation targets to read-only artifacts. Mutation-shaped keys and
forbidden operation IDs are rejected before wrappers or core code continue.

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

The audit writes one digest-bound readiness document that is directly
consumable by `frontier --audit-file`. It includes contract conformance,
implementation-readiness state, dependency and overlap facts, semantic-review
status, and the existing metadata-governance findings.

The metadata checks remain subject to policy flags:

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

### Project plan

```bash
python scripts/triage/triage.py project-plan \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json --json
bash .codex/bin/action.sh project-plan \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json --json
```

`project-plan` emits the advisory GitHub Project layout from an existing
snapshot and readiness audit. The stable wrapper uses the repository virtualenv
and keeps `--json` stdout clean. It writes no GitHub metadata, emits no
operation plan, and does not replace the approval-gated `apply` path.

### Contract

```bash
python scripts/triage/triage.py contract --issue 54
python scripts/triage/triage.py contract --issue 54 \
  --snapshot output/triage/snapshot.json --json
```

I use `contract` to audit exactly one issue against contract v1. It emits the
inferred issue kind, governance state, acceptance-coverage checks, findings,
and a body digest. With `--snapshot`, it performs no GitHub call.

When the issue text clearly relies on an external provider contract, such as a
hosted API, CLI behavior, schema guarantee, platform rule, product
documentation, package-manager rule, or CI-service behavior, the contract
requires `Official documentation evidence`. This applies even when the provider
is unknown or not in the known-provider list. The check is deterministic and
local: it parses the issue body, matches conservative known-provider and
generic external-contract triggers, and validates URL hostnames against known
official documentation domains. It checks provider field values and URL
hostnames independently, so one known provider mention cannot mask a separate
unknown provider or URL host. It does not retrieve URLs, cache web pages, check
freshness, or certify that the documentation was interpreted correctly.

Unknown documentation providers and unknown URL hosts are allowed only when the
issue preserves the verification state. If I have verified that the URL is
official, I record that fact in residual uncertainty and still leave
interpretation for review. If the source is unverified and critical before
implementation, I also record that unresolved verification under
`Maintainer decisions and blockers`.

### Review packet

```bash
python scripts/triage/triage.py review-packet --issue 54 \
  --snapshot output/triage/snapshot.json \
  --semantic-evidence output/triage/semantic-evidence.json \
  --output-dir output/triage/issues/54
```

The command writes only local files:

```text
output/triage/issues/54/review-packet.json
output/triage/issues/54/contract.json
output/triage/issues/54/proposed-body.md
```

The packet is bounded to one issue, direct dependencies, issue-specific parent
excerpts, referenced paths, checked source and test entry points, uncertainty,
and verification commands. It does not embed the full tracker.

If official documentation evidence is required and missing, the proposed body
contains a local placeholder section. The packet does not fetch documentation or
turn documentation URLs into executable operations.

### Standardize

```bash
python scripts/triage/triage.py standardize --issue 54 \
  --snapshot output/triage/snapshot.json \
  --proposed-body output/triage/issues/54/proposed-body.md \
  --output-dir output/triage/issues/54
```

`standardize` validates an ASCII local body and writes that exact text plus a
digest-bound `standardization.json`. It never calls a GitHub write endpoint and
cannot add an issue-body operation to a plan.

### AI-assisted section drafting (assist layer)

`review-packet` writes `proposed-body.md` with the deterministic placeholder
("Unknown. I could not establish ... maintainer review is required.") for any
section it cannot establish, and the contract audit rejects a body that still
contains it. The deterministic tool is unchanged: it still emits placeholders
and gates.

The `issue-governance` skill adds an optional assist layer on top. When sections
are missing, the agent reads `contract.json` (the missing sections) and
`review-packet.json` (the bounded repository context), drafts only the
placeholder sections from cited source files, and writes them back into
`proposed-body.md`. The agent then runs `standardize` to confirm the contract
passes and presents the placeholder-to-draft diff for maintainer review.

This layer is assistive and non-authoritative. It must:

- draft only placeholder sections and never rewrite established content;
- cite sources with verifiable anchors (`path:symbol` or `path "snippet"`),
  never a bare `path:line`, so the draft passes the audit's citation checks;
- keep proven and inferred separate -- hypothesis-label anything it cannot
  ground and list residual open questions, never fabricating acceptance facts,
  test results, or decisions to clear the gate;
- include `Official documentation evidence` when the issue relies on external
  platform behavior, and record provider, official URL, supported claim,
  version context, retrieval date, and residual uncertainty without fetching the
  page during standardization;
- for unknown providers, either record maintainer verification in residual
  uncertainty or, when verification is required before implementation, also add
  the unresolved verification to `Maintainer decisions and blockers`;
- prefix each drafted section with
  `> Draft (machine-authored; needs maintainer verification)`;
- stop before any GitHub mutation. The maintainer reviews the diff and applies
  the edit; the deterministic audit remains the source of truth.

### Frontier

```bash
python scripts/triage/triage.py frontier --mode audit \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json --json
python scripts/triage/triage.py frontier --mode implement \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json --json \
  --packet-output output/triage/frontier-worker-packet.json
```

Audit mode selects the highest deterministic issue that still needs governance
or semantic-review work. Implement mode selects only an accepted issue whose
readiness state is `ready`; it rejects unresolved dependencies, missing merge
evidence, cycles, decisions, external blockers, missing paths, active pull
request conflicts, overlap, and other readiness blockers.

Selection is deterministic. Ties use the issue number. `--empty-selection` or
`--issues none` explicitly returns `selected_issue: null`. That is a valid
coordinator result, and no worker packet is written for an empty frontier.

The coordinator and optional worker packet are digest-validated before they are
written. The frontier command never creates a branch, worktree, Codex thread,
or GitHub mutation.

### Backlog synthesis

```bash
python scripts/triage/triage.py backlog-synthesis \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --output output/triage/backlog-synthesis.json
```

`backlog-synthesis` emits a read-only candidate-signal report for cross-issue
maintainer review. It consumes a snapshot plus readiness audit, surfaces
semantic disposition hypotheses when present, and emits deterministic signals
for likely duplicates, explicit overlap, split candidates, and dependency-order
inversions.

The command writes only a local artifact and validates the artifact before
printing or writing it. The report has no `operations` payload, no issue bodies,
no tracker state changes, and no GitHub mutation path. Its contract is
documented in `docs/BACKLOG_SYNTHESIS_SIGNALS_SCHEMA_V1.md`.

### Synthesis Review Packet

```bash
python scripts/triage/triage.py synthesis-review-packet \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --backlog-synthesis output/triage/backlog-synthesis.json \
  --output output/triage/synthesis-review-packet.json
```

`synthesis-review-packet` turns local deterministic artifacts into a bounded v1
review packet. It consumes a snapshot, readiness audit, backlog-synthesis
report, and optional project-plan artifact. The command validates each source,
checks digest lineage, builds the packet, validates the packet, and then prints
or writes JSON.

The command is offline when local artifacts are supplied. It does not fetch
GitHub, collect comments, run subprocesses for tracker state, emit executable
operations, or add an apply path. `--json` stdout is reserved for packet JSON;
status output goes to stderr when `--json` is used.

### Backlog Review Validate

```bash
python scripts/triage/triage.py backlog-review-validate \
  --packet output/triage/synthesis-review-packet.json \
  --verdict output/triage/backlog-review-verdict.json \
  --json
```

`backlog-review-validate` validates a local packet plus verdict pair before
maintainer review. It loads only the supplied JSON files, validates the packet,
validates the verdict, and then validates packet-bound lineage and references:
packet digest, source snapshot digest, readiness-audit digest,
backlog-synthesis digest, evidence IDs, near-miss IDs, and omission IDs.

The command exits nonzero for hard errors and zero for valid pairs, including
warning-only packet freshness. Warning-only freshness is surfaced as a
machine-readable warning finding, and the pair remains valid only when the
verdict preserves the warning in `packet_reviewability`, `uncertainty`, or
`required_maintainer_checks`.

Hard-stale packets, non-reviewable packets, invalid-lineage packets, unknown
packet-bound refs, executable operation shapes, GitHub request payloads, issue
write payloads, metadata mutations, workflow dispatches, PR merge instructions,
approval batches, and anything directly consumable by `triage.py apply` are
hard validation errors.

The command does not call GitHub, refresh old packets, collect comments, run
tracker retrieval subprocesses, call browsers or LLMs, dispatch workflows,
generate an apply plan, or integrate with `apply`.

### Backlog Review Skill

Use `$backlog-review` after generating a local `synthesis-review-packet` when a
bounded LLM review is useful. The skill reads the packet and schema docs only,
keeps warning-only freshness visible to the maintainer, validates verdict JSON
with `backlog-review-validate`, and emits advisory output without GitHub
mutation or executable apply payloads.

## Bounded LLM backlog review workflow

This is the full operator flow for the bounded LLM review layer. GitHub remains
the source of truth. The local artifacts are bounded evidence snapshots, not
live tracker state, and LLM verdicts are advisory. The maintainer decides what
to do with any candidate verdict.

```text
snapshot.json
  -> audit.json
  -> project-plan.json
  -> backlog-synthesis.json
  -> synthesis-review-packet.json
  -> backlog-review skill / backlog-review-verdict.json
  -> backlog-review-validate
  -> maintainer decision
  -> optional future explicitly approved write path or manual maintainer action
```

The diagram shows the complete review flow when the operator also emits an
advisory Project layout. `project-plan` is optional for packet generation:
`synthesis-review-packet` requires `snapshot`, `audit-file`, and
`backlog-synthesis`, and can additionally consume `--project-plan` when that
context is useful.

### Generate the local artifacts

Capture the live tracker once:

```bash
python scripts/triage/triage.py snapshot \
  --output output/triage/snapshot.json
```

Generate the readiness audit from that snapshot:

```bash
python scripts/triage/triage.py audit \
  --snapshot output/triage/snapshot.json \
  --output output/triage/audit.json
```

Generate deterministic backlog synthesis signals:

```bash
python scripts/triage/triage.py backlog-synthesis \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --output output/triage/backlog-synthesis.json
```

Generate the advisory Project layout when useful:

```bash
python scripts/triage/triage.py project-plan \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --output output/triage/project-plan.json
```

Generate the bounded review packet:

```bash
python scripts/triage/triage.py synthesis-review-packet \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --backlog-synthesis output/triage/backlog-synthesis.json \
  --output output/triage/synthesis-review-packet.json
```

When the Project layout should be part of the packet evidence, add:

```bash
  --project-plan output/triage/project-plan.json
```

Use `--issues` to bound the packet to selected issue numbers. Use
`--max-age-hours` only to make the hard review-age threshold stricter. Use
`--allow-stale-offline-packet` only when a hard-stale, non-reviewable artifact
is needed for offline inspection.

### Use backlog-review

Invoke `$backlog-review` with one local packet, for example:

```text
$backlog-review output/triage/synthesis-review-packet.json
```

The skill reads `AGENTS.md`, the packet, and the packet/verdict schema docs. It
does not read the full tracker, all open issue bodies, GitHub comments,
arbitrary GitHub state, retrieval indexes, or semantic search output by
default. It can produce either an advisory Markdown maintainer handoff or a
`backlog-review-verdict` JSON artifact.

Validate any verdict JSON before treating it as ready for maintainer review:

```bash
python scripts/triage/triage.py backlog-review-validate \
  --packet output/triage/synthesis-review-packet.json \
  --verdict output/triage/backlog-review-verdict.json \
  --json
```

The maintainer reviews candidate verdicts, evidence refs, diagnostic refs,
uncertainty, freshness warnings, and required maintainer checks. The maintainer
decides; verdict JSON never decides.

### Freshness and reviewability

24 hours is the default freshness-warning threshold, not the default stale
cliff. 168 hours / 7 days is the default hard LLM-review threshold unless the
caller intentionally makes it stricter with `--max-age-hours`.

Warning-only packets have `stale: false`. They have
`llm_review_allowed: true`. They may be reviewed only when warnings are visible
to the maintainer, and the warning must remain present in the handoff or
verdict `packet_reviewability`, `uncertainty`, or
`required_maintainer_checks`.

Hard-stale packets have `stale: true`. They are not LLM-reviewable, stop the
`backlog-review` skill, and fail integrated verdict validation. Packets with
`llm_review_allowed: false` are not valid LLM inputs. Invalid source lineage or
digest mismatch is a hard failure regardless of age.

The safe response to old source artifacts is to regenerate the local source
artifacts. Packet and verdict tooling must not refresh old packets by fetching
GitHub implicitly.

### Budget, omissions, and refs

The serialized byte budget is the hard deterministic packet gate. Token
estimates are advisory telemetry. Issue comments are omitted in v1, and full
issue bodies are not embedded in the default bounded review flow. Packet
omissions include copied `backlog-synthesis.omissions[]` entries and
packet-level omissions such as `issue-comments-not-collected` and
`full-issue-bodies-not-embedded`. Omissions are explicit local artifact
evidence, not permission to fetch unbounded context automatically.

Diagnostic IDs flow through the artifacts unchanged:

```text
backlog-synthesis.near_misses[].near_miss_id
  -> synthesis-review-packet.near_misses[].near_miss_id
  -> backlog-review-verdict.verdicts[].near_miss_refs[]

backlog-synthesis.omissions[].omission_id, when copied into the packet
  -> synthesis-review-packet.omissions[].omission_id
  -> backlog-review-verdict.verdicts[].omission_refs[]

synthesis-review-packet.omissions[].omission_id, including packet-level omissions
  -> backlog-review-verdict.verdicts[].omission_refs[]
```

The refs are exact packet-provided strings, not model-generated guesses. Each
`backlog-review-verdict.verdicts[].omission_refs[]` entry must cite an exact
`synthesis-review-packet.omissions[].omission_id` value, whether that omission
came from backlog synthesis or from the packet builder. The model must not
invent or recompute diagnostic IDs. Diagnostic refs do not authorize writes.
Omission refs do not authorize fetching comments, embedding full issue bodies,
retrieval, GitHub writes, or apply operations, and do not replace
freshness/staleness or integrated validation gates.

Schema details live in:

- `docs/SYNTHESIS_REVIEW_PACKET_SCHEMA_V1.md`
- `docs/BACKLOG_REVIEW_VERDICT_SCHEMA_V1.md`
- `docs/BACKLOG_SYNTHESIS_SIGNALS_SCHEMA_V1.md`
- `docs/PROJECT_PLAN_SCHEMA_V1.md`

### What not to do

- Do not prompt with the full raw snapshot by default.
- Do not fetch issue comments in v1.
- Retrieval is not authoritative.
- Do not let LLM output carry executable operations.
- `future_apply_recommendations` are not executable operations.
- Do not feed verdict JSON into `triage.py apply`.
- Do not refresh old packets implicitly from packet or verdict tooling.
- Packets or verdicts must not create tracker writes.

### Offline forms

Every tracker-reading command except `snapshot` accepts an explicit snapshot.
The following sequence is credential-free:

```bash
python scripts/triage/triage.py audit \
  --snapshot output/triage/snapshot.json \
  --output output/triage/audit.json
python scripts/triage/triage.py frontier --mode audit \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json --json
```

`apply --dry-run` is intentionally different: it performs a live read-only
preflight against current issue metadata, but it does not write. Execute mode
retains the approval, exact repository confirmation, environment, lock,
just-in-time verification, and receipt gates documented below.

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
