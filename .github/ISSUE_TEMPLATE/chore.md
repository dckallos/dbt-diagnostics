---
name: Chore / maintenance
about: Build, release, governance, dependency, or repo-hygiene work with no diagnostic behavior change (conventional commit -- chore:)
title: "chore: "
labels: chore
---

<!--
ASCII only. No AI-authorship markers. NOTE: the agent token cannot modify
.github/workflows/*; workflow changes are handed to the maintainer to commit.
Delete guidance comments before submitting.
-->

## Summary

What maintenance work this is and why it is needed now.

## Motivation

The concrete pain or risk (manual release step, missing gate, dependency
drift, governance not version-controlled, etc.).

## Scope / tasks

- [ ] ...
- [ ] ...

```text
# commands / config / policy JSON involved
```

```yaml
# proposed workflow or config (maintainer-applied if under .github/workflows/)
```

## Out of scope

What this deliberately does NOT touch (so it stays one coherent PR).

## Acceptance criteria / Definition of Done

- [ ] ...
- [ ] No tool behavior or `--json` `schema_version` change (or state the
      additive change explicitly).
- [ ] CHANGELOG `[Unreleased]` entry if anything observable changes.

## Dependencies / manual setup

Anything that must be done by hand (admin token, PyPI trusted publisher,
branch protection, a workflow file the agent cannot push).

## Traceability

- Parent epic (if any): #
- Relates to: #

## Suggested labels

`chore`, `ci`, `cleanup`, `dependencies`
