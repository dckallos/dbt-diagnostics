---
name: Spike / investigation
about: Time-boxed research to produce a go/no-go decision and a scoped follow-up. No production code ships from a spike.
title: "spike: "
labels: spike
---

## Question to answer

<!-- One sentence. A spike resolves a decision; it does not implement. -->

## Why this is a spike (not an implementation)

<!-- What is unknown/risky enough that coding first would be premature
(e.g. a protocol version boundary, a portability contract, a reliability
cliff). -->

## Evidence and confidence

- Status: **SPECULATIVE** until the investigation closes.
- Prior signal: <OUTPUT_FOUR finding / research doc / external source>.

## Investigation tasks

- [ ] <enumerate the concrete things to read, run, or measure>
- [ ] Reproduce the concern with a minimal probe (cite the command/code).

## Probe / reproduction (code)

```bash
# the exact command(s) or minimal script that produce the evidence
```

```python
# or a minimal isolated check
```

## Deliverable

<!-- A written go/no-go with citations, and if "go", a scoped follow-up issue.
The decision must be recorded in the repo (doc/issue), not just in chat. -->

## Acceptance criteria

- [ ] The question is answered with first-party citations or reproduced evidence.
- [ ] An explicit, justified consume/defer (or design) decision is recorded.
- [ ] If "go", a follow-up implementation issue is filed referencing this one.
- [ ] No production runtime code added in this issue.

## Scope and files touched

- `docs/...` (findings), test/throwaway probe only.

## Traceability

- OUTPUT_THREE changes: <n, ...>
- OUTPUT_FOUR findings: <...>
- Parent epic: #4 | #48
- Relates to: #<n>

## Suggested labels

`spike` (+ `architecture`, `portability`, `compat`, `research`)
