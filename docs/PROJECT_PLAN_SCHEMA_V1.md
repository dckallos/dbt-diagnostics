# Project plan schema v1

Schema version 1 is the stable JSON contract for the read-only GitHub Project
desired-state plan emitted by the `project-plan` command. The machine-readable
JSON Schema is `docs/project-plan-schema-v1.json`.

The project plan is advisory. It is a local artifact for maintainer review and
does not authorize, describe, or carry a GitHub mutation payload.

## Determinism

For identical snapshot, readiness-audit, and policy inputs:

- columns are emitted in the configured readiness-state order, followed by any
  extra readiness states sorted by column id;
- items are ordered by column rank, then ascending issue number;
- dependency and parent issue-number arrays are sorted positive integers;
- missing item collections are empty arrays, not null;
- the project-plan digest is SHA-256 over canonical JSON excluding only the
  `project_plan_digest` field itself.

`generated_at` comes from the source snapshot. Reusing an unchanged snapshot,
audit, and policy therefore yields byte-stable project-plan JSON.

## Required fields

- `schema_version`: integer `1`.
- `repository`: `owner/name`.
- `generated_at`: snapshot timestamp.
- `snapshot_digest`: deterministic snapshot digest.
- `audit_digest`: deterministic readiness-audit digest.
- `project`: configured Project identity summary.
- `columns`: desired Project columns.
- `items`: desired issue placement.
- `ordering_conflicts`: dependency-order warnings.
- `safety`: read-only safety declaration.
- `project_plan_digest`: SHA-256 digest.

## Project

`project` always includes:

- `enabled`: boolean.

When configured, it may also include:

- `owner_type`: string or integer.
- `owner`: string or integer.
- `number`: string or integer.

## Columns

Each column has:

- `id`: non-empty string readiness-state id.
- `name`: non-empty display name.
- `position`: positive integer.

## Items

Each item has:

- `issue_number`: positive integer.
- `title`: string or null.
- `url`: string or null.
- `column_id`: non-empty string matching the target column id.
- `direct_dependencies`: array of positive issue or pull-request numbers.
- `parent_epics`: array of positive issue numbers.
- `release_gate`: boolean.
- `dependency_impact`: non-negative integer.
- `position`: positive integer across the full plan.
- `column_position`: positive integer within the target column.

Items must not include issue content or tracker state. In particular, `body` and
`state` are forbidden item keys.

## Ordering Conflicts

Each ordering conflict has:

- `code`: non-empty string, currently `dependency-inversion`.
- `issue_number`: positive integer.
- `dependency_issue_number`: positive integer.
- `issue_position`: positive integer.
- `dependency_position`: positive integer.
- `message`: non-empty string.

## Safety

The safety object is part of the contract and must keep these exact values:

- `read_only`: `true`.
- `github_api_calls`: `false`.
- `github_mutations`: `false`.
- `project_writes_supported`: `false`.
- `metadata_operations_supported`: `false`.
- `contains_issue_content`: `false`.
- `contains_state_changes`: `false`.

The top-level `operations` key is forbidden. A project plan is not an approval
bundle and must not be consumed as one.

## Empty Plan

An empty project plan is valid when its input audit has no issue entries:

```json
{
  "items": [],
  "ordering_conflicts": []
}
```

The complete object still includes repository, timestamp, digests, columns,
safety flags, project configuration, and its own digest.

## Validation

`scripts/triage/frontier.py:validate_project_plan` validates required keys,
field types, read-only safety fields, forbidden mutation shape, and the
canonical digest. It returns an empty list for a valid plan and a list of
specific error strings for malformed or stale plans.
