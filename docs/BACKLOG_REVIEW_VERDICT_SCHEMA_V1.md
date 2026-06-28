# Backlog review verdict schema v1

Schema version 1 is the stable JSON contract for the read-only
`backlog-review-verdict` artifact produced from a validated
`synthesis-review-packet`. The machine-readable JSON Schema is
`docs/backlog-review-verdict-schema-v1.json`.

The verdict is advisory. It is not an apply plan, not an approval bundle, not an
operation list, and not a GitHub request payload. The flow is:

```text
synthesis-review-packet -> advisory verdict -> maintainer decision
```

The maintainer decides whether to close, merge, split, reorder, edit, or leave
tracker items unchanged.

## Determinism

For identical verdict content:

- collection fields are emitted as arrays, using empty arrays rather than null;
- packet evidence, near-miss, and omission references are exact packet IDs;
- the verdict digest is SHA-256 over canonical JSON excluding only
  `backlog_review_verdict_digest`.

Changing verdicts, packet-reviewability metadata, future apply recommendations,
uncertainty, maintainer checks, safety flags, or source digests changes
`backlog_review_verdict_digest`.

## Required fields

- `schema_version`: integer `1`.
- `repository`: `owner/name`.
- `generated_at`: verdict generation timestamp.
- `source_packet_digest`: source packet digest.
- `source_snapshot_digest`: source packet snapshot digest.
- `source_audit_digest`: source packet readiness-audit digest.
- `source_backlog_synthesis_digest`: source packet backlog-synthesis digest.
- `packet_reviewability`: packet freshness and reviewability summary.
- `verdicts`: advisory verdict items.
- `future_apply_recommendations`: advisory future action descriptions.
- `uncertainty`: bounded caveats and no-action rationales.
- `required_maintainer_checks`: checks the maintainer must perform before
  acting.
- `safety`: read-only safety declaration.
- `backlog_review_verdict_digest`: SHA-256 digest.

## Packet reviewability

`packet_reviewability` preserves the packet facts needed for maintainer
visibility and later integrated validation:

- `source_packet_digest`
- `source_snapshot_digest`
- `source_audit_digest`
- `source_backlog_synthesis_digest`
- `freshness_status`
- `freshness_warnings`
- `packet_stale`
- `llm_review_allowed`
- `invalid_lineage`

Warning-only packets remain reviewable only when the warning remains visible in
the verdict. A verdict can preserve the warning in `packet_reviewability`,
`uncertainty`, or `required_maintainer_checks`.

Hard-stale packets, packets with `llm_review_allowed: false`, and packets with
invalid lineage are not valid LLM verdict inputs.

## Verdict items

Each verdict item has:

- `verdict_id`: stable verdict-local ID.
- `verdict_type`: non-empty advisory verdict type.
- `issue_numbers`: sorted positive issue or pull-request numbers.
- `recommendation`: advisory recommendation text.
- `confidence`: `low`, `medium`, or `high`.
- `evidence_refs`: exact packet `evidence_id` strings.
- `near_miss_refs`: exact packet `near_miss_id` strings.
- `omission_refs`: exact packet `omission_id` strings.
- `rationale`: bounded rationale.
- `risks`: bounded risk strings.
- `required_maintainer_checks`: verdict-local maintainer checks.
- `future_apply_recommendation_ref`: optional reference to an advisory future
  apply recommendation.

Verdicts require evidence refs unless `verdict_type` is
`insufficient-evidence`. An empty `verdicts` array is valid only when
`uncertainty` includes a `no_actionable_candidates` rationale.

## Packet-bound references

When a source packet is supplied to the validator:

- `source_packet_digest` must match
  `synthesis-review-packet.synthesis_review_packet_digest`;
- source snapshot, audit, and backlog-synthesis digests must match
  `synthesis-review-packet.source_artifacts`;
- every `evidence_ref` must match a packet
  `evidence_items[].evidence_id`;
- every `near_miss_ref` must match a packet
  `near_misses[].near_miss_id`;
- every `omission_ref` must match a packet `omissions[].omission_id`.

Near-miss and omission refs are exact strings from the packet. The validator
does not invent, recompute, normalize, or infer diagnostic IDs from prose.

## Future apply recommendations

`future_apply_recommendations` are advisory only. They can describe a possible
maintainer action, rationale, and review context, but they must not contain an
operation ID, request method, request path, request body, approval batch, or
anything directly consumable by `triage.py apply`.

The existing `triage.py apply` path remains separate and is not integrated with
this schema.

## Safety

The safety object is part of the contract and must keep these exact values:

- `read_only`: `true`.
- `github_api_calls`: `false`.
- `github_mutations`: `false`.
- `contains_executable_operations`: `false`.
- `contains_github_request_payloads`: `false`.
- `contains_issue_write_payloads`: `false`.
- `future_apply_recommendations_are_advisory`: `true`.
- `maintainer_decides`: `true`.
- `llm_verdicts_are_advisory`: `true`.

## Forbidden shape

Forbidden shape checks are recursive. A verdict must not carry `operations`,
GitHub request payloads, apply operations, operation IDs, approval batches,
request method/path/body structures, issue title/body/state update payloads,
label updates, milestone updates, Project updates, close/reopen requests,
comments, issue `state` mutation targets, unbounded issue `body` content, or a
full tracker snapshot at any depth.

Use packet-bound `evidence_refs`, `near_miss_refs`, and `omission_refs` instead
of embedding full evidence bodies or diagnostic payloads.

## Validation

`scripts/triage/frontier.py:validate_backlog_review_verdict` validates the
standalone read-only verdict envelope, required keys, field types, safety
flags, forbidden mutation shape, advisory future apply recommendations, empty
verdict rationale, and canonical verdict digest.

`scripts/triage/frontier.py:validate_backlog_review_verdict_against_packet`
first validates the verdict and the source packet, then checks exact source
digests, evidence refs, near-miss refs, omission refs, and #96 freshness
semantics against the supplied packet.

The integrated operator-facing packet plus verdict validation gate is tracked
separately by #100.
