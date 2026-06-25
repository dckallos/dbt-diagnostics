# spike: add a governance/process issue kind to the contract (decision)

## Summary

Decide whether the contract needs a dedicated `governance` (or `process`) issue
kind, or whether such issues should instead be tagged via the disposition
vocabulary. Today a process/governance fixture is forced into
`test_verification` purely by its `test:` title prefix.

## Evidence and confidence

`infer_issue_kind` maps the `test:` prefix to `test_verification`
(`scripts/triage/contract.py`; `scripts/triage/policy.toml` `[type_inference.prefixes]`),
so #74 -- a governance dogfood -- is treated as a test issue and must satisfy
live/offline/test-plan sections that fit awkwardly. There is no governance kind.
Confidence high; verified against source.

## Current wrong behavior or gap

Governance/process issues are mis-kinded and made to carry product-test contract
sections that do not match their intent.

## Acceptance criteria (decision)

- Decide: new kind vs. disposition tag. Record the choice and rationale.
- If a new kind: define its required/recommended sections and forbidden
  sections, with positive and negative classification tests.
- A regression case: existing `test:` issues that are genuine product tests
  still classify as `test_verification`.

## Focused test plan

If a kind is added: parametrized `infer_issue_kind` tests for the new prefix/label
and for non-regression of existing kinds; contract-audit tests for the new
section set.

## Scope and likely files

- `scripts/triage/contract.py`
- `scripts/triage/policy.toml`
- `scripts/triage/test_contract.py`

## Explicit non-goals

- No change to product issue kinds beyond classification.

## Dependencies and traceability

- Relates to the forest-synthesis issue (disposition vocabulary).
- Surfaced by the #74 governance dogfood.
