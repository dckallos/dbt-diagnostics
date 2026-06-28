# Backlog synthesis signals schema v1

Schema version 1 is the stable JSON contract for the read-only backlog
synthesis signal report emitted by the `backlog-synthesis` command. The
machine-readable JSON Schema is
`docs/backlog-synthesis-signals-schema-v1.json`.

The report is advisory. It gives a maintainer or a stronger review model a
bounded set of candidate duplicate, overlap, split, semantic-disposition, and
ordering signals, plus explicit near-miss and omission diagnostics for bounded
review. It does not authorize, describe, or carry a GitHub mutation payload.

## Determinism

For identical snapshot and readiness-audit inputs:

- issue dispositions are ordered by ascending issue number;
- signal arrays are ordered by signal type, issue numbers, and summary;
- near-miss arrays are ordered by deterministic `near_miss_id`;
- omission arrays are ordered by deterministic `omission_id`;
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
- `near_misses`: deterministic advisory diagnostics for considered weak matches.
- `omissions`: deterministic advisory diagnostics for intentionally omitted
  evidence surfaces.
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

## Near misses

Near misses are not verdicts and do not lower the threshold for positive
signals. They record deterministic weak matches that were considered but not
promoted to `signals`.

Each near miss has:

- `near_miss_id`: deterministic ID in the form
  `near-miss-{near_miss_type_slug}-{zero_padded_issue_numbers}-{reason_category_slug}`.
- `near_miss_type`: non-empty diagnostic type.
- `issue_numbers`: sorted unique positive issue or pull-request numbers.
- `score`: non-negative deterministic score.
- `reason_not_signaled`: human-readable reason the item stayed diagnostic-only.
- `shared_evidence`: bounded evidence strings.
- `details`: structured deterministic context, including
  `reason_category`.

The current v1 duplicate near-miss ID for issues 1 and 2 below the title
similarity threshold is:

`near-miss-possible-duplicate-001-002-title-similarity-below-threshold`

Duplicate near misses require meaningful shared context, such as shared
referenced paths, parent epics, issue kind, or title tokens. Unrelated pairs do
not emit near misses.

## Omissions

Omissions record intentional limits in the advisory report instead of embedding
unbounded tracker material. Each omission has:

- `omission_id`: deterministic ID in the form
  `omission-{omission_type_slug}`.
- `omission_type`: non-empty omission type.
- `reason`: human-readable omission reason.
- `details`: structured deterministic context, including
  `reason_category`.

The v1 report always includes:

`omission-no-issue-body-in-signals`

This omission states that the read-only signal report excludes full issue body
text. Split-marker diagnostics may inspect issue text from the provided local
snapshot, but the report does not embed the full issue body.

## Safety

The safety object is part of the contract and must keep these exact values:

- `read_only`: `true`.
- `github_api_calls`: `false`.
- `github_mutations`: `false`.
- `contains_issue_content`: `false`.
- `contains_state_changes`: `false`.
- `verdicts_are_advisory`: `true`.

The top-level `operations` key is forbidden. Signal details must not include
issue `body` or tracker `state` fields. Near-miss and omission details are
subject to the same recursive read-only forbidden-shape checks and must not
carry GitHub request payloads, executable operations, issue body/state update
payloads, label/milestone/Project changes, close/reopen requests, or comments.

## Validation

`scripts/triage/frontier.py:validate_backlog_synthesis_report` validates
required keys, field types, near-miss and omission array shapes, deterministic
ID consistency, ID uniqueness, sorted issue-number arrays, read-only safety
fields, forbidden mutation shape, and the canonical digest. Changing near
misses or omissions changes `backlog_synthesis_digest`. It returns an empty
list for a valid report and a list of specific error strings for malformed or
stale reports.
