# feat: deterministic cross-issue disposition and order-of-operations synthesis

## Summary

Add a read-only synthesis pass that turns the per-issue readiness records into a
backlog-level view: likely duplicates, split/merge candidates, obsolete issues,
and order-of-operations conflicts. The per-issue skill cannot see across issues
by design, so this is where "should this issue exist / in what order?" is
answered, for a maintainer or a stronger model to act on.

## Evidence and confidence

The lifecycle today can only conform an issue to the contract. The disposition
verb is a fixed map keyed by `implementation_state`
(`scripts/triage/readiness.py` `recommended_disposition`), and `superseded` is
only reachable for an already-closed issue
(`scripts/triage/readiness.py` `audit_issue`, the `state != "open"` branch). An
open, conformant, dependency-clean issue always collapses to `ready`; there is
no `close-as-duplicate`, `split`, `merge`, or `wont-do` verb for an open issue.
The aggregation substrate already exists
(`scripts/triage/frontier.py` `audit_frontier_candidates` and
`implementation_frontier_candidates` consume the whole-backlog audit). Confidence
high; verified against source.

## Current wrong behavior or gap

On a real backlog the agent polishes issues but never reduces issue count: it
will draft a clean body for an issue that should have been closed as a
duplicate.

## Acceptance criteria

- A positive case: given a snapshot with two near-identical issues, the
  synthesis pass emits a `likely-duplicate` pairing with evidence.
- A negative case: unrelated issues produce no spurious duplicate or merge
  suggestion.
- A per-issue `disposition` hypothesis supplied in semantic-evidence is surfaced
  read-only and overrides the mechanical map; absent one, the mechanical map is
  unchanged (regression).
- A degradation case: with no semantic-evidence the pass still runs and reports
  `unknown` rather than failing.
- The pass performs no GitHub mutation.

## Focused test plan

Unit-test the synthesis over crafted audits: duplicate pair, split candidate,
order-of-operations conflict (a dependency ranked after its dependent), and the
empty/clean control. Confirm the mechanical disposition map is unchanged when no
hypothesis is supplied.

## Scope and likely files

- `scripts/triage/frontier.py` (new synthesis entry point)
- `scripts/triage/readiness.py` (read-only `disposition` passthrough)
- `scripts/triage/test_frontier.py`

## Explicit non-goals

- No GitHub mutation; recommendations only.
- The per-issue `issue-governance` skill is not given cross-issue context.

## Dependencies and traceability

- Parent: governance toolchain epic (decide tracker home; see D5 issue).
- Relates to the per-issue disposition hypothesis added to
  `.agents/skills/issue-governance/SKILL.md`.
