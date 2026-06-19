---
name: Chore / maintenance
about: Build, release, dependency, or repo-hygiene work with no change to diagnostic behavior.
title: "chore: "
labels: chore
---

## Summary

<!-- The maintenance task and why it is worth doing now. -->

## Evidence and confidence

- Status: **PROVEN** (the current state being changed).
- Today: <current mechanism -- e.g. hand-driven release, missing pin>.

## Scope / deliverables

- [ ] <coupled deliverables; keep them in one PR if they must land together>

## Config / command (code)

```yaml
# the workflow/config/manifest change (if a workflow file, see the note below)
```

```bash
# any one-time maintainer setup that CI cannot perform
```

## Acceptance criteria

- [ ] The task is done and verifiable.
- [ ] No tool behavior or `--json` `schema_version` change.
- [ ] CHANGELOG `[Unreleased]` if anything user-facing shifts.

## Constraints / process note

<!-- The agent token CANNOT modify `.github/workflows/*`. For workflow changes,
this issue delivers the file content; the maintainer commits it by hand. -->

## Scope and files touched

- `<paths>`

## Traceability

- OUTPUT_FOUR findings: <if applicable>
- Parent epic: <#4 | #48 | standalone>
- Depends on: #<n>

## Suggested labels

`chore` (+ `ci`, `release`, `docs`)
