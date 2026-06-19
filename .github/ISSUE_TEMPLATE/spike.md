---
name: Spike / research
about: A time-boxed investigation that ends in a written go/no-go, not shipped runtime code (conventional commit -- spike: or docs:)
title: "spike: "
labels: spike
---

<!--
ASCII only. No AI-authorship markers. A spike produces a DECISION and a
scoped follow-up, not runtime behavior. If you find yourself shipping a
class nothing uses, stop -- that is a spike result ("defer"), not a feature.
Delete guidance comments before submitting.
-->

## Question

The single decision this spike must answer (e.g. "What must a real
warehouse-neutral adapter contract cover, and is it worth building before
the Snowflake contract is fully exposed?").

## Why now

What is blocked or at risk until this is answered. Cite the review trail.

## Background

What we already know, with citations (first-party docs, schemas, prior
issues/PRs). Distinguish PROVEN facts from assumptions.

## Investigation plan

- [ ] ...
- [ ] Enumerate the concrete unknowns (versions, boundaries, capabilities).
- [ ] Run isolated checks where possible (compile/import probes, doc reads,
      recorded-row contract tests) -- state what each does and does NOT prove.

```text
# commands / probes to run, and what a pass/fail of each would mean
```

## Options under consideration

For each option: what it buys, what it costs, what breaks.

```text
option A: ...
option B: ...
```

## Deliverable

- A written go/no-go recorded in `docs/...` (and/or `compat/WATCH.md`) with
  citations.
- If "go": a scoped implementation issue with the gates spelled out.
- If "defer": the trigger that should reopen it.

## Acceptance criteria

- [ ] The question is answered with an explicit, justified decision (not
      left implicit).
- [ ] First-party citations for every load-bearing claim.
- [ ] No runtime/code behavior change in this issue.
- [ ] Follow-up issue filed (if "go") or trigger recorded (if "defer").

## Scope and files touched

- `docs/...` (decision record only)

## Traceability

- OUTPUT_THREE change(s): #
- OUTPUT_FOUR finding(s):
- Parent epic: #4 | #48
- Relates to: #

## Suggested labels

`spike`, `research` / `architecture` / `portability` / `compat`
