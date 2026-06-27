# Issue contract v1

Default configured contract ID: `dbt-diagnostics.issue-contract.v1`

Default configured contract version: `1.0`

The active ID and version come from `scripts/triage/policy.toml`
`[governance.contract]` through the typed repo policy adapter. This repository
keeps the values above; another configured consumer can supply its own contract
ID without changing the contract parser.

This document defines the issue contract used by the repository governance and
readiness tooling. The contract is deliberately smaller than a universal issue
template. Every issue has a common core, then one type-specific section set.
Conditional sections apply only when the issue touches the corresponding risk.

The contract serves two different decisions:

1. Governance conformance asks whether the tracker item is structured, linked,
   and internally consistent.
2. Implementation readiness asks whether the proposed work is technically and
   operationally safe to begin.

A conformant issue is not automatically implementation-ready. Deterministic
checks cannot prove semantic completeness. A maintainer or agent must still
inspect the relevant source, callers, tests, and design documents and record the
result as semantic-review evidence.

## Contract principles

- Keep one coherent PR-sized change in one implementation issue.
- State facts, hypotheses, uncertainty, and required external evidence
  separately.
- Use repository paths and tracker references that can be checked.
- Make acceptance criteria observable and testable.
- Preserve offline behavior and cost boundaries when live access is involved.
- Do not claim that a deterministic check proves semantic correctness.
- Do not use issue bodies as mutable automation state.
- Proposed body revisions remain local review artifacts until a maintainer
  explicitly approves the exact edit.

## Common core

I require implementation issues to use these sections or an accepted equivalent heading. Epics use the reduced common core documented in the Epic section below.

### Summary

State the bounded outcome in a few sentences. Name the affected behavior,
artifact, workflow, or decision. Do not embed the full implementation plan in
this section.

### Evidence and confidence

Separate what is proven from what is inferred or unknown. Cite concrete source
files, functions, tests, artifact fixtures, tracker metadata, or external
evidence. Mark unsupported assumptions as hypotheses.

When you cite a source location, prefer a verifiable content anchor over a bare
line number: name the symbol (`path:symbol`) or quote a short snippet
(`path "snippet"`). Line numbers drift as code changes and are not reproducible,
so a bare `path:line` citation is advisory only. The audit re-locates a symbol
or snippet against current file content; it never certifies a line number as
fresh, and only reports a line as definitely stale when it is past the end of
the file.

### Acceptance criteria

Use observable completion conditions. Each criterion should be verifiable by a
test, command, artifact, tracker state, or explicit maintainer decision.

### Focused test plan

Name the focused tests first, then the repository gates. Include positive,
negative, degradation, and regression cases appropriate to the issue. Do not
claim that a mock proves live platform behavior.

### Scope and likely files

Name the subsystem and likely repository paths. This is a boundary, not a
promise that no adjacent caller will be inspected.

### Dependencies and traceability

Name direct dependencies, parent epic, related ownership, superseded work, and
blocked work with explicit issue references. Direct dependencies are the items
that must close and merge before implementation can start.

### Explicit non-goals

Required for implementation issues and strongly recommended for all other
issues. Exclude adjacent work that would make the PR incoherent.

## Conditional core

The following sections are required only when their condition applies.

### Offline behavior

Required for any issue involving Snowflake, live probes, query history,
credentials, or a warehouse call. State what remains useful without credentials
and how unavailable evidence is represented.

### Live behavior and cost tier

Required for live or warehouse-aware work. State whether the work is metadata
only or a data scan, how it is authorized, and what identity or visibility
limits apply. Tier A means metadata-only, not guaranteed free. Tier B remains
explicitly opt-in and bounded.

### Maintainer decisions and blockers

Required when an issue carries `decision-needed` or `blocked`, or when its body
contains an unresolved choice. Name the exact decision and the consequences of
each option. Do not silently choose one in implementation.

### External evidence, permissions, credentials, or fixtures

Required when completion needs a real account, protected environment, real
fixture, publisher setup, license choice, security contact, or other authority
outside the checkout. Missing evidence is a blocker, not a reason to invent a
result.

### Official documentation evidence

Required when an issue depends on external platform behavior, product
documentation, API or CLI contracts, schema guarantees, hosted service rules, or
other official source-of-truth material outside this repository. This is
separate from credentials, permissions, real fixtures, and maintainer decisions:
it preserves the official public documentation that supports a claim, while
those other sections preserve access, authority, or unresolved choice.

The section must name:

- provider;
- official URL;
- supported claim or decision;
- docs version or product version when available;
- retrieval date;
- residual uncertainty.

The deterministic contract check is local-only. It detects conservative known
provider triggers and generic external contract claims, including unknown
products or hosted services. Known-provider checks validate URL hostnames
against known official documentation domains. Provider field values and URL
hostnames are checked independently, so one known URL or known provider mention
does not prove a separate unknown provider or URL host. Unknown providers or
unknown URL hosts require explicit maintainer verification or residual
uncertainty. The check does not fetch URLs, cache pages, use a browser, check
freshness, or prove that the issue interprets the documentation correctly.

For an unknown provider, use the section to preserve the uncertainty instead of
inventing a trusted domain. If the maintainer has verified that the URL is
official, say that in residual uncertainty and keep semantic interpretation
separate. If the source is still unverified and implementation-critical, also
record the unresolved verification in `Maintainer decisions and blockers`; the
contract rejects a critical unknown-provider source that says verification is
required before implementation but has no blocker section.

### Compatibility and canonical JSON implications

Required when work affects the public JSON contract, artifact versions,
compatibility behavior, deprecations, migration, or stable CLI behavior. State
which existing keys and meanings remain stable and which additions are allowed.

### Migration, coexistence, and rollback

Required for refactors and architecture changes. Name the cutover boundary,
whether old and new paths can coexist, how duplicate execution is prevented,
and what a clean rollback means.

### Release relevance and priority

Required for release work or milestone gates. State whether the issue blocks the
initial release, is post-release, or is research. Tracker labels and milestone
assignment must agree with the body.

### Documentation and CHANGELOG obligations

Required when behavior, public commands, contributor workflow, or release
metadata changes. State the expected documentation and CHANGELOG update.

## Issue kinds

The deterministic tool infers one of eight kinds from the title and type label.
A maintainer can correct an inference by fixing the title or label; the body is
not given a hidden type marker.

## Bug or fix

Required in addition to the common core:

- `Current wrong behavior or gap`
- `Root cause or architectural reason`
- `Expected behavior or target outcome`
- `Explicit non-goals`

Recommended:

- `Negative, degradation, and regression coverage`
- `Compatibility and canonical JSON implications`

A root cause may be an explicit hypothesis when proof requires live evidence.
The issue must not present a hypothesis as confirmed behavior.

## Feature or enhancement

Required in addition to the common core:

- `User-visible problem or current gap` or `Trigger or applicability`
- `Expected behavior or target outcome`
- `Explicit non-goals`

Recommended:

- `Negative, degradation, and regression coverage`
- `Offline behavior` when any live capability is involved

The issue should describe the user outcome before prescribing architecture.
Tier-B work must include its cost and authorization boundary.

## Refactor or architecture

Required in addition to the common core:

- `Current wrong behavior or gap`
- `Expected behavior or target outcome`
- `Migration, coexistence, and rollback`
- `Compatibility and canonical JSON implications`
- `Explicit non-goals`

Recommended:

- `Negative, degradation, and regression coverage`
- `Single-PR boundary`

The issue must name the active cutover path. A replacement collector may not run
beside the legacy collector for the same request merely to ease migration.

## Test or verification

Required in addition to the common core:

- `User-visible problem or current gap` or `Current wrong behavior or gap`
- `External evidence, permissions, credentials, or fixtures` or a precise
  `Scope and likely files`
- `Explicit non-goals`

Recommended:

- `Negative, degradation, and regression coverage`

A test issue distinguishes offline proofs from live verification. It must not
turn test infrastructure into an unreviewed product behavior change.

## Spike or decision

Required in addition to the common core:

- `Question to answer`
- `Investigation tasks`
- `Deliverable`
- `Decision criteria` or observable `Acceptance criteria`
- `Explicit non-goals`

Recommended:

- `External evidence, permissions, credentials, or fixtures`

Forbidden:

- A production `Implementation plan` presented as already selected

A spike ends with a recorded go/no-go or bounded architecture decision. It does
not ship runtime behavior.

## Governance or process

Required for governance issues:

- `Summary`
- `Evidence and confidence`
- `Acceptance criteria` or `Decision criteria`
- `Explicit non-goals`
- `Dependencies and traceability`

Recommended:

- `Current wrong behavior or gap`

A governance issue records process, contract, or tracker decisions. It does not
inherit product-test sections such as `Focused test plan`, live/offline fixture
requirements, or product verification coverage unless a separate conditional
risk makes those sections relevant.

## Epic

I use a reduced common core for epics: `Summary` and `Evidence and confidence`, plus these epic-specific sections:

- `Thesis or decision`
- `Initial-release gate or build order`
- `Children and backlog`
- `Maintainer decisions and blockers`
- `Workflow`

Forbidden:

- A `Single-PR boundary`

An epic separates completed work, current gate items, post-release work, and
research. Checked and unchecked tracker references must agree with live state.

## Docs, chore, or release

Required in addition to the common core:

- A concrete `User-visible problem or current gap`, `Deliverable`, or `Scope and
  likely files`
- `Release relevance and priority` or `Dependencies and traceability`
- `Explicit non-goals`

Recommended:

- `Documentation and CHANGELOG obligations`

Release and packaging work must name external publisher, environment, legal, or
security decisions rather than treating them as code-only tasks.

## Acceptance-coverage expectations

The readiness audit looks for evidence that acceptance and test coverage address
these categories when appropriate:

- positive behavior;
- negative behavior;
- degradation or unavailable-evidence behavior;
- regression preservation.

The deterministic check only verifies that the categories are represented. It
cannot prove that the selected cases are technically sufficient. Semantic
review must inspect the current implementation and add hidden failure modes or
corner cases to the review packet.

## Governance states

- `conformant`: deterministic contract and tracker checks pass.
- `needs_contract_revision`: required sections or metadata are missing.
- `stale`: the issue contradicts current tracker or repository state.
- `conflicting`: dependency or ownership metadata conflicts.
- `unsafe`: the body or requested operation violates a hard policy.
- `unknown`: evidence needed for a deterministic conclusion is unavailable.

## Implementation-readiness states

- `ready`: contract accepted, semantic review recorded, direct dependencies
  closed and merged, no unresolved blocker, and one coherent PR is credible.
- `needs_contract_revision`: the issue contract is not yet accepted.
- `needs_semantic_review`: deterministic checks pass but source/test review has
  not established technical sufficiency.
- `needs_decision`: a maintainer choice remains unresolved.
- `blocked`: a dependency, fixture, credential, permission, or authority is
  unavailable.
- `stale`: assumptions or references no longer match live state.
- `overlapping`: another open issue explicitly owns the same change.
- `superseded`: live tracker evidence says another item replaced this issue.
- `unsafe`: implementation would violate a repository safety boundary.
- `unknown`: available evidence is insufficient to select another state.

`ready` is intentionally hard to reach. A deterministic parser never promotes an
issue to `ready` without explicit semantic-review evidence.

## Canonical headings

The parser accepts a small set of aliases for existing tracker prose, but new or
revised issue bodies should prefer these headings:

```text
## Summary
## User-visible problem or current gap
## Evidence and confidence
## Current wrong behavior or gap
## Root cause or architectural reason
## Expected behavior or target outcome
## Trigger or applicability
## Acceptance criteria
## Focused test plan
## Negative, degradation, and regression coverage
## Scope and likely files
## Explicit non-goals
## Dependencies and traceability
## Maintainer decisions and blockers
## Offline behavior
## Live behavior and cost tier
## External evidence, permissions, credentials, or fixtures
## Compatibility and canonical JSON implications
## Migration, coexistence, and rollback
## Release relevance and priority
## Documentation and CHANGELOG obligations
```

Use only the sections that apply to the issue kind and conditions. A spike,
epic, bug, and release chore should not have the same body shape.

## Local audit and standardization

Audit one live issue:

```bash
python scripts/triage/triage.py contract --issue 55
```

Audit from an offline snapshot:

```bash
python scripts/triage/triage.py contract --issue 55 \
  --snapshot output/triage/snapshot.json
```

Create a bounded review packet:

```bash
python scripts/triage/triage.py review-packet --issue 55 \
  --snapshot output/triage/snapshot.json \
  --semantic-evidence output/triage/semantic-evidence.json \
  --output-dir output/triage/issues/55
```

Validate a proposed replacement body locally:

```bash
python scripts/triage/triage.py standardize --issue 55 \
  --snapshot output/triage/snapshot.json \
  --proposed-body proposed.md \
  --output-dir output/triage/issues/55
```

`standardize` never edits GitHub. Its output is a review artifact. The process
stops before tracker mutation and requires explicit approval for the exact body
text through the maintainer's normal GitHub workflow.

When `review-packet` or `standardize` sees a known-provider, unknown-provider,
or generic external contract claim, it includes or requires
`Official documentation evidence` in the same local-only flow. A placeholder
section still blocks acceptance until the exact body records real documentation
evidence and residual uncertainty.
