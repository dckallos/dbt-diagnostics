---
name: Bug / correctness fix
about: A defect where the tool produces a wrong, unsafe, or misleading result (e.g. a confident cause the evidence does not prove).
title: "fix: "
labels: bug
---

## Summary

<!-- One paragraph: what is wrong and the user-visible consequence. State the
false conclusion the tool can reach, not just the code smell. -->

## Evidence and confidence

<!-- Tag the claim. PROVEN = confirmed against source/docs/a real artifact;
SPECULATIVE = plausible but unverified. SPECULATIVE bugs need a verification
step BEFORE they are fixed. -->

- Status: **PROVEN** | **SPECULATIVE** (confirmed against source on `<branch>`, `<date>`).
- File/line evidence: `path/to/file.py:LINE` -- <what it does wrong>.
- If SPECULATIVE, what would confirm it: <real fixture / live probe / doc cite>.

## Current (wrong) behavior

```python
# path/to/file.py:LINE (current) -- annotate the exact wrong line
```

## Root cause

<!-- The underlying reason, not the symptom. Name the epistemic error if any:
not-visible vs nonexistent, no-grant-row vs no-access, failed-probe vs fact. -->

## Expected behavior

<!-- What a correct, evidence-safe result looks like. -->

## Proposed fix (sketch)

```python
# minimal sketch of the corrected code or query
```

## Acceptance criteria

- [ ] The wrong result no longer occurs.
- [ ] A regression test asserts the CORRECT positive outcome AND the
      unknown/failed degradation -- not merely the absence of the old bug.
- [ ] `--json` additive-only; CHANGELOG `[Unreleased]` updated.

## Test plan

- Tiers: `unit` | `contract` | `robustness` | `e2e` (`--no-live`) | `live` (gated).
- Cases: <happy path, failure path, degradation path>.

## Scope and files touched

- `path/to/file.py`

<!-- List every file so colliding issues can be sequenced and disjoint ones
run as parallel PRs. -->

## Snowflake / portability impact

<!-- Does this encode Snowflake-specific SQL/identifiers/error codes? Note it
for the N7 metadata gateway / N8 adapter seam. -->

## Traceability

- OUTPUT_THREE changes: <n, ...>
- OUTPUT_FOUR findings: <Executive #/Wave-n change #/Section #>
- Parent epic: #4 | #48
- Depends on / blocks: #<n>

## Suggested labels

`bug` (+ `live`, `correctness`, `security`, `snowflake`, `cli`, `config` as apt)
