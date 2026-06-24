# Frontier coordinator schema v1

Schema version 1 is the stable JSON contract for the read-only coordinator. The
machine-readable JSON Schema is `docs/frontier-schema-v1.json`.

## Determinism

For identical snapshot and audit inputs:

- candidates are ordered by descending deterministic score, then ascending
  issue number;
- arrays containing tracker numbers or paths are sorted;
- absent collections are empty arrays, not null;
- `selected_issue` is an integer or null;
- `suggested_branch` and `suggested_next_command` are strings or null;
- the coordinator digest is SHA-256 over canonical JSON excluding only the
  `coordinator_digest` field itself.

`generated_at` comes from the source snapshot. Reusing an unchanged snapshot
therefore yields byte-stable coordinator JSON.

## Required fields

- `schema_version`: integer `1`.
- `mode`: `audit` or `implement`.
- `repository`: `owner/name`.
- `generated_at`: snapshot timestamp.
- `snapshot_digest`: deterministic snapshot digest.
- `audit_digest`: deterministic audit digest.
- `selected_issue`: selected issue number or null.
- `issue_contract_digest`: accepted body digest or null.
- `governance_state`: governance state or null.
- `implementation_state`: readiness state or null.
- `selection_reason`: deterministic explanation.
- `parent_epics`: sorted issue numbers.
- `direct_dependencies`: sorted direct dependency numbers.
- `blockers`: sorted blocker descriptions.
- `required_decisions`: sorted decision descriptions.
- `required_external_evidence`: sorted external requirements.
- `referenced_paths`: sorted repository paths.
- `suggested_branch`: local suggestion or null.
- `suggested_next_command`: read-only context command or null.
- `candidate_count`: eligible candidate count.
- `rejected_count`: rejected candidate count.
- `coordinator_digest`: SHA-256 digest.

Selected results also include `score` and `score_components`. Implementation
results may include a bounded `rejected_preview` for review; it is not the full
audit.

## Empty frontier

An empty frontier is explicit:

```json
{
  "schema_version": 1,
  "mode": "implement",
  "selected_issue": null,
  "selection_reason": "frontier is empty",
  "parent_epics": [],
  "direct_dependencies": [],
  "blockers": [],
  "required_decisions": [],
  "required_external_evidence": [],
  "referenced_paths": [],
  "suggested_branch": null,
  "suggested_next_command": null
}
```

The complete object includes repository, timestamp, digests, counts, and its own
digest. Consumers must not substitute a fallback issue.

## Worker packet relationship

The coordinator result selects an issue. The optional worker packet is a
separate bounded schema with the issue body, accepted contract facts, relevant
parent/dependency excerpts, source/test entry points, unresolved uncertainty,
verification commands, and branch/worktree state. It does not embed the full
tracker or every issue body.
