# Backlog synthesis signals schema v1

Schema version 1 is the stable JSON contract for the read-only backlog
synthesis signal report emitted by the `backlog-synthesis` command. The
machine-readable JSON Schema is
`docs/backlog-synthesis-signals-schema-v1.json`.

The report is advisory. It gives a maintainer or a stronger review model a
bounded set of candidate duplicate, overlap, split, semantic-disposition, and
ordering signals. It does not authorize, describe, or carry a GitHub mutation
payload.

## Determinism

For identical snapshot and readiness-audit inputs:

- issue dispositions are ordered by ascending issue number;
- signal arrays are ordered by signal type, issue numbers, and summary;
- tracker-number arrays are sorted positive integers;
- missing collections are empty arrays, not null;
- the backlog-synthesis digest is SHA-256 over canonical JSON excluding only
  the `backlog_synthesis_digest` field itself.

`generated_at` comes from the source snapshot. Reusing an unchanged snapshot and
audit therefore yields byte-stable backlog-synthesis JSON.

## Required fields

- `schema_version`: integer `1`.
- `repository`: `owner/name`.
- `generated_at`: snapshot timestamp.
- `snapshot_digest`: deterministic snapshot digest.
- `audit_digest`: deterministic readiness-audit digest.
- `issue_dispositions`: per-issue mechanical and semantic disposition view.
- `signals`: deterministic candidate signals.
- `safety`: read-only safety declaration.
- `backlog_synthesis_digest`: SHA-256 digest.

## Issue dispositions

Each issue disposition has:

- `issue_number`: positive integer.
- `mechanical_disposition`: the readiness audit's existing
  `recommended_disposition`.
- `semantic_hypothesis`: semantic-review disposition hypothesis, or null.
- `recommended_disposition`: the semantic hypothesis when supplied, otherwise
  the mechanical disposition.
- `semantic_evidence_status`: `provided` or `unknown`.
- `evidence`: semantic-disposition evidence strings.

The synthesis report does not change the readiness audit's mechanical map. The
override is local to this advisory synthesis artifact.

## Signals

Each signal has:

- `signal_type`: non-empty string.
- `issue_numbers`: sorted positive issue or pull-request numbers.
- `confidence`: `low`, `medium`, or `high`.
- `summary`: non-empty human-readable summary.
- `evidence`: evidence strings suitable for maintainer review.
- `details`: structured data for deterministic consumers.

Current signal types are:

- `semantic-disposition`: a per-issue semantic hypothesis was supplied.
- `explicit-overlap`: the readiness audit found explicit ownership overlap.
- `likely-duplicate`: open issues have highly similar titles and shared audit
  context.
- `split-candidate`: issue text contains deterministic split-marker language.
- `dependency-inversion`: project-plan ordering puts an issue before a direct
  dependency.

Signals are candidates. The maintainer decides whether to close, split, merge,
reorder, or leave issues unchanged.

## Safety

The safety object is part of the contract and must keep these exact values:

- `read_only`: `true`.
- `github_api_calls`: `false`.
- `github_mutations`: `false`.
- `contains_issue_content`: `false`.
- `contains_state_changes`: `false`.
- `verdicts_are_advisory`: `true`.

The top-level `operations` key is forbidden. Signal details must not include
issue `body` or tracker `state` fields.

## Validation

`scripts/triage/frontier.py:validate_backlog_synthesis_report` validates
required keys, field types, read-only safety fields, forbidden mutation shape,
and the canonical digest. It returns an empty list for a valid report and a
list of specific error strings for malformed or stale reports.
