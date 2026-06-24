# Issue governance and readiness

I use this tooling to inspect the live tracker, apply the versioned issue
contract, record semantic-review evidence, and select one bounded next item. The
normal workflow is read-only. Proposed issue-body revisions are local files,
not GitHub mutations.

The canonical contract is `docs/ISSUE_CONTRACT_V1.md`.

## Source of truth

The tooling and review process use this order:

1. Live GitHub issue, pull request, label, milestone, comment, and configured
   Project metadata.
2. The current governance implementation on the active governance branch.
3. Repository source, tests, `AGENTS.md`, `CONTRIBUTING.md`, and design docs.
4. `docs/PROGRESS_LOG.md` only as historical continuity context.
5. Generated audit files and prior reports only as non-authoritative leads.

A stale progress entry never overrides live tracker state. A local snapshot is a
reproducible input, not a substitute for a later refresh.

## Safety boundary

The current command layer does not mutate GitHub.

It does not:

- create, close, reopen, or edit issues or pull requests;
- change issue titles or bodies;
- add issue-body mutation to an allowlist;
- create, delete, or rename labels or milestones;
- change Projects, branches, releases, protection, secrets, environments, or
  workflows;
- create a worktree as a side effect of an audit or frontier command.

The retained `apply` command validates approval artifacts for backward
compatibility, but actual execution is deliberately unavailable. `--dry-run`
performs validation only. `--execute` and its compatibility alias are rejected.

Issue text and user-controlled content are never interpolated into a shell
command. The live snapshot transport uses argument arrays and JSON decoding.

## Command surface

```bash
python scripts/triage/triage.py snapshot
python scripts/triage/triage.py contract --issue 55
python scripts/triage/triage.py audit
python scripts/triage/triage.py review-packet --issue 55 \
  --output-dir output/triage/issues/55
python scripts/triage/triage.py standardize --issue 55 \
  --proposed-body proposed.md \
  --output-dir output/triage/issues/55
python scripts/triage/triage.py frontier --mode audit --json
python scripts/triage/triage.py frontier --mode implement --json
```

All commands accept an offline snapshot where applicable. This is the normal
mode for tests and reproducible review:

```bash
python scripts/triage/triage.py audit \
  --snapshot output/triage/snapshot.json \
  --semantic-evidence output/triage/semantic-evidence.json \
  --output-dir output/triage
```

## Live snapshot

A live snapshot requires the GitHub CLI and an authenticated read identity:

```bash
gh auth status
python scripts/triage/triage.py snapshot \
  --output output/triage/snapshot.json
```

The snapshot command uses read-only REST GET requests. It captures:

- issues and pull requests in the tracker namespace;
- labels and milestones;
- comments when `--comments` is requested;
- referenced closed items and open pull request metadata where available;
- configured Project metadata only when an exact Project identity is enabled;
- a deterministic content digest that ignores only the generation timestamp.

If `gh` is unavailable, the tool does not pretend to have refreshed GitHub. Use
an explicitly supplied snapshot and record the transport limitation in the
review report.

## Contract audit

`contract` audits one issue body and its metadata against contract v1. It
reports:

- inferred issue kind;
- required, conditional, recommended, and forbidden section findings;
- malformed or duplicated headings;
- title and type-label consistency;
- acceptance-coverage categories;
- body and contract digests.

A contract audit proves only deterministic structure. It cannot establish that
the diagnosis, acceptance criteria, migration plan, or tests are semantically
complete.

## Governance and readiness audit

`audit` produces repository-wide and per-issue results. The deterministic layer
checks, where evidence is available:

- title, issue kind, labels, and milestone;
- required and conditional sections;
- tracker references and repository paths;
- direct dependencies, parent epics, supersession, and graph cycles;
- closed, duplicate, stale, or contradictory references;
- release-gate and milestone drift;
- explicit ownership overlap;
- active pull request conflicts;
- one-PR scope warning signals;
- represented positive, negative, degradation, and regression coverage;
- unresolved decisions and external blockers;
- stale progress-log claims;
- deterministic ordering and hashes.

The report keeps governance conformance and implementation readiness separate.
The readiness states are documented in `docs/ISSUE_CONTRACT_V1.md`.

## Semantic-review evidence

Python owns durable tracker facts and deterministic checks. It does not claim to
prove semantic sufficiency. A source-aware reviewer records evidence in a local
JSON file and reruns the audit.

A semantic-evidence entry may include:

- source and test claims checked;
- relevant files and callers inspected;
- missing edge cases or tests;
- known false assumptions;
- unresolved maintainer decisions;
- external evidence or workflow authority required;
- overlap conflicts;
- dependency merge evidence;
- accepted contract status;
- a final readiness recommendation and confidence.

The deterministic auditor refuses to promote an issue to `ready` merely because
its headings are complete. `ready` requires explicit semantic-review evidence
and all deterministic blockers to be clear.

## Single-issue audit and improvement loop

For one issue:

1. Refresh or load the issue, direct dependencies, parent epic, referenced
   tracker items, labels, milestone, comments when needed, and repository paths.
2. Run deterministic contract and metadata checks.
3. Inspect only the relevant source, callers, tests, and design documents needed
   to verify the claims and discover hidden failure modes.
4. Record facts, uncertainty, readiness states, source evidence, and any
   maintainer decisions in semantic-evidence JSON.
5. Generate a bounded packet with `review-packet`.
6. Revise `proposed-body.md` locally when the contract needs correction.
7. Run `standardize` against the proposed body.
8. Repeat until all fixable findings are resolved or the remaining items are
   explicit decisions or external blockers.
9. Stop before GitHub mutation and request review of the exact proposed text.

A review packet contains:

```text
output/triage/issues/<number>/review.json
output/triage/issues/<number>/review.md
output/triage/issues/<number>/proposed-body.md
output/triage/issues/<number>/contract-audit.json
```

The proposed body uses explicit placeholders for unknown facts. It does not
invent source evidence, credentials, decisions, or fixture availability.

## Across-issues audit queue

The audit frontier chooses the highest-value issue that still needs governance
or semantic review. It uses only compact audit records and deterministic scores;
it does not load every issue body into an agent thread.

```bash
python scripts/triage/triage.py frontier --mode audit --json \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json
```

Audit priority favors, in order:

- unsafe or contradictory state;
- stale release-gate state;
- explicit ownership overlap;
- contract revision;
- unresolved decisions or blockers;
- missing semantic review;
- dependency impact and release relevance;
- stable issue-number tie-breaking.

After one issue is reviewed, update semantic evidence, rerun the audit, and
recompute the frontier.

## Implementation frontier

The implementation frontier consumes accepted contracts and readiness results.
It does not standardize issues.

```bash
python scripts/triage/triage.py frontier --mode implement --json \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --packet-output output/triage/frontier-worker-packet.json
```

An implementation candidate must have:

- an accepted governance contract;
- implementation state `ready`;
- no dependency cycle;
- all direct dependencies closed;
- recorded merge evidence for dependency code when dependencies exist;
- no unresolved decision;
- no required external evidence still missing;
- no missing required repository path;
- no active pull request conflict;
- no explicit overlap conflict;
- no remaining readiness blocker.

When no issue satisfies the rules, the command returns an explicit no-selection
result. It never guesses.

The coordinator schema and relay workflow are documented in
`docs/CODEX_RELAY.md` and `docs/FRONTIER_SCHEMA_V1.md`.

## Plan and apply compatibility commands

`plan` remains available so existing automation does not break. It writes a
read-only plan with zero operations and the current audit digest.

`apply --dry-run` validates:

- plan digest;
- repository identity;
- approval identity and timestamp;
- selected batch;
- exact operation IDs;
- operation allowlist;
- absence of issue-body mutation.

There are no supported write operations in this implementation. Any non-empty
operation list, issue-body request, or execution request is rejected.

## Generated files

Generated output belongs under `output/triage/` and is ignored. It is not a
source of truth and should not be shipped in the package.

Repository-authored files must remain ASCII. Generated JSON and Markdown are
written deterministically and checked for ASCII before completion.

## Verification

Run the focused governance suite:

```bash
pytest -q scripts/triage
python -m compileall -q scripts/triage
```

Run the repository gate after governance changes:

```bash
pytest -q
python -m compileall -q dbt_diagnostics scripts .codex
bash -n .codex/bin/*.sh
```

A repeated audit or frontier run over identical inputs must produce identical
semantic JSON bytes once volatile timestamps are excluded from the input
snapshot.
