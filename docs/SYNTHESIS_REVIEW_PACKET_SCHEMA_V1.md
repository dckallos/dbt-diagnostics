# Synthesis review packet schema v1

Schema version 1 is the stable JSON contract for the read-only
`synthesis-review-packet` artifact consumed by bounded LLM backlog review. The
machine-readable JSON Schema is `docs/synthesis-review-packet-schema-v1.json`.

The packet is advisory evidence. It is not a verdict, not an operation plan,
not an approval bundle, and not an apply payload. It binds selected facts from
an existing tracker snapshot, readiness audit, backlog-synthesis report, and
optional project-plan artifact into one bounded review surface.

## Determinism

For identical source artifacts and packet scope:

- collection fields are emitted as arrays, using empty arrays rather than null;
- the packet records the source artifact digests it was built from;
- the packet records both the source timestamp and the packet timestamp;
- the synthesis-review-packet digest is SHA-256 over canonical JSON excluding
  only the `synthesis_review_packet_digest` field itself.

The digest covers packet scope, evidence, omissions, budget telemetry,
staleness, safety flags, and source artifact digests. Changing any of those
values changes the packet digest.

## Required Fields

- `schema_version`: integer `1`.
- `repository`: `owner/name`.
- `generated_at`: packet generation timestamp.
- `source_generated_at`: timestamp from the source snapshot or selected source
  artifact.
- `source_artifacts`: digest chain for the source inputs.
- `packet_scope`: bounded review task and selected scope.
- `candidate_sets`: candidate issue groups for review.
- `evidence_items`: bounded evidence excerpts with evidence IDs.
- `near_misses`: explicit candidate exclusions or weak matches.
- `omissions`: evidence intentionally omitted from the packet.
- `comments_included`: always `false` for v1.
- `comment_evidence_status`: always `not_collected` for v1.
- `budget`: serialized byte size, byte limits, and advisory token estimates.
- `staleness`: source age and reviewability flags.
- `safety`: read-only safety declaration.
- `synthesis_review_packet_digest`: SHA-256 digest.

## Source Artifacts

`source_artifacts` always includes:

- `snapshot_digest`
- `audit_digest`
- `backlog_synthesis_digest`

It may include:

- `project_plan_digest`

All digests are lowercase SHA-256 strings. The packet is valid only for the
exact source artifacts identified by those digests.

## Candidate Sets And Evidence

`candidate_sets`, `evidence_items`, `near_misses`, and `omissions` are bounded
arrays. Empty arrays are valid and explicit.

Evidence items use `evidence_id` to make later verdict citations stable. Issue
body text is allowed only as a bounded excerpt field on an evidence item, not as
an unbounded `issue.body` object. The packet must not embed the full tracker
snapshot.

## Comments

Issue comments are not collected in v1. A valid v1 packet has:

- `comments_included: false`
- `comment_evidence_status: not_collected`
- `safety.contains_issue_comments: false`

If comments matter for a review, the packet records that as an omission instead
of fetching or embedding comments.

## Budget

The byte budget is authoritative:

- `target_bytes`: `204800`
- `hard_bytes`: `307200`

`serialized_bytes` must not exceed `hard_bytes`. The validator also recomputes
the packet's actual canonical serialized byte length and rejects packets whose
real size exceeds `hard_bytes`, even if `serialized_bytes` under-reports size.

Token estimates are advisory telemetry:

- `estimated_tokens`
- `target_estimated_tokens`: `50000`
- `hard_estimated_tokens`: `75000`
- `token_estimate_method`
- `budget_warnings`

The validator checks token estimate types and constants, but it does not reject
a packet merely because `estimated_tokens` exceeds the token target or hard
token estimate. Packet creation must use the serialized byte budget as the
deterministic gate.

`budget_warnings` is an array of advisory warning codes. It is empty when the
packet is at or below target byte and token thresholds. It includes
`serialized_bytes_exceeds_target_bytes` when the final serialized packet exceeds
the target byte size but remains at or below the hard byte size. It includes
`estimated_tokens_exceeds_target` when the deterministic token estimate exceeds
the target token count. These warnings do not make a packet invalid by
themselves.

## Staleness

`staleness` includes:

- `source_generated_at`
- `evaluated_at`
- `source_age_hours`
- `warning_age_hours`
- `max_age_hours`
- `freshness_status`
- `freshness_warnings`
- `stale`
- `llm_review_allowed`

The default freshness warning age is 24 hours. Crossing that threshold does not
make the packet stale. A warning-only packet uses:

- `freshness_status: warning`
- `freshness_warnings: ["source_age_exceeds_warning_age"]`
- `stale: false`
- `llm_review_allowed: true`

The default hard LLM-review age is 168 hours. `--max-age-hours` may make that
hard threshold stricter, but it may not make packets older than 168 hours
reviewable by default.

Boundary semantics are inclusive at the threshold: exactly 24 hours is still
`fresh`, exactly 168 hours is still reviewable with warning metadata, and only a
source age greater than the hard threshold is `stale`.

A stale packet is not LLM-reviewable. If `stale` is `true`,
`llm_review_allowed` must be `false`. The default
`validate_synthesis_review_packet()` path rejects stale packets for LLM review.
The CLI can emit a hard-stale packet only for offline inspection when
`--allow-stale-offline-packet` is supplied, and that artifact must remain
`llm_review_allowed: false`.

Source digest or lineage mismatch is not represented as a successful packet
status. Packet creation fails before output when source artifacts disagree.

## Safety

The safety object is part of the contract and must keep these exact values:

- `read_only`: `true`.
- `github_api_calls`: `false`.
- `github_mutations`: `false`.
- `contains_executable_operations`: `false`.
- `contains_full_tracker_snapshot`: `false`.
- `contains_issue_comments`: `false`.
- `comments_included`: `false`.
- `llm_verdicts_are_advisory`: `true`.

The packet does not read GitHub, write GitHub, execute commands, or authorize a
mutation.

## Forbidden Shape

Forbidden shape checks are recursive. The packet must not carry `operations`,
GitHub request payloads, apply operations, issue title/body update payloads,
label updates, milestone updates, Project updates, close/reopen requests, issue
`state` mutation targets, issue comments, unbounded issue `body` content, or a
full tracker snapshot at any depth.

Use bounded evidence excerpts with `evidence_id` instead of embedding
`issue.body`.

## Validation

`scripts/triage/frontier.py:validate_synthesis_review_packet` validates
required keys, field types, source digests, comments status, budget constants,
self-reported and actual byte-budget enforcement, freshness/staleness
consistency, read-only safety fields, recursive forbidden mutation shape, and
the canonical packet digest. It returns an empty list for a valid reviewable
packet and a list of specific error strings for malformed or stale packets.
Its explicit offline-stale mode permits only non-reviewable stale inspection
artifacts.
