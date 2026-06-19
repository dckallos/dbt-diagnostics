---
name: Docs
about: Documentation that follows code (design docs, watch lists, progress log, contributor guidance). Docs never lead code.
title: "docs: "
labels: docs
---

## Summary

<!-- What doc is added/changed and why. Per AGENTS.md, docs FOLLOW code: do not
describe unlanded work in past tense. -->

## Evidence and confidence

- Status: **PROVEN** (the code/state being documented already exists) or clearly
  marked as target-state ("to be removed, tracked by #N").

## Content to record

- [ ] <item / why it matters / trigger to act / source link>

## Example entry (code/markup)

```markdown
<!-- the shape of the doc entry, e.g. a WATCH.md row or a PROGRESS_LOG entry -->
```

## Acceptance criteria

- [ ] The doc exists and is linked from the right place (DESIGN.md / AGENTS.md / CONTRIBUTING.md).
- [ ] No runtime/code behavior change.
- [ ] No claim describes unlanded work as done.

## Scope and files touched

- `docs/...` | `dbt_diagnostics/compat/...`

## Traceability

- OUTPUT_FOUR findings: <if applicable, e.g. Section 6.4 tracker drift>
- Parent epic: <#4 | #48 | standalone>
- Relates to: #<n>

## Suggested labels

`docs` (+ `compat`, `tier-4`)
