# feat: read-only GitHub Projects and order-of-ops planner (no mutation)

## Summary

Let the toolchain PLAN a GitHub Project board and flag order-of-operations
problems, emitting a desired-state spec the maintainer applies by hand. This
keeps the user-friendly Projects layer the maintainer wants without breaking the
read-only scope guard.

## Evidence and confidence

Creating or maintaining a Project is a GitHub mutation, which the scope guard
forbids the toolchain from performing (`AGENTS.md`, the read-only governance
pointer, and the skills' "never mutate" rule). A read-only home already exists:
`scripts/triage/policy.toml` `[project]` (`enabled = false`) and the
`[planning]` / `[desired]` staging tables, where bodies and state are explicitly
forbidden. Confidence high; verified against source.

## Current wrong behavior or gap

There is no way to project the backlog into a board view or surface
order-of-operations conflicts without a human assembling it manually.

## Acceptance criteria

- A positive case: the planner emits a desired Project structure (columns,
  issue placement, ordering) as JSON from the audit, deterministically.
- A negative case: a dependency ordered before its blocker is flagged.
- A regression case: with `[project] enabled = false`, the planner still only
  emits a plan and never calls the GitHub API.
- The emitted artifact contains no issue body or state changes.

## Focused test plan

Unit-test the planner over a crafted audit: column assignment, ordering, and a
dependency-inversion flag. Assert the output is a plan object and that no
network/mutation entry point is reachable.

## Scope and likely files

- `scripts/triage/frontier.py` or a new `scripts/triage/projects.py`
- `scripts/triage/policy.toml` (`[project]` / `[planning]`)
- corresponding `test_*.py`

## Explicit non-goals

- No `gh project` writes; the maintainer (or one authorized writer session)
  applies the plan.
- No issue creation, edit, label, or milestone changes.

## Dependencies and traceability

- Relates to the forest-synthesis issue (order-of-ops signals come from there).
- Parent: governance toolchain epic.
