---
name: Epic
about: An umbrella tracking a body of work across many issues
title: "[Epic] "
labels: epic
---

<!--
ASCII only. No AI-authorship markers. An epic body is a LIVE status board:
keep it reconciled with actual issue/PR state. Stale checkboxes (showing
closed issues as open, or removed code as present) are a known failure mode
-- update this body whenever a child issue closes. Delete guidance before submitting.
-->

## Epic: <name>

Design doc: `docs/<DESIGN>.md`. Research: `docs/<RESEARCH>.md` (if any).

## Thesis

The one-paragraph charter. For correctness epics, state the epistemic
principles this epic enforces (e.g. evidence identity, status, provenance,
and confidence are first-class; not-visible != nonexistent; failed probe !=
negative fact).

## Status (YYYY-MM-DD)

Reconcile against the tracker every time this is edited.

- Built/merged: #... (PR #...)
- In progress: #...
- Stale-body check done: yes/no

## Scope

What is in, what is explicitly out (scope guard).

## Build order / child issues

List children as checkboxes; check them as they CLOSE.

- [ ] #... -- <one line>
- [ ] #... -- <one line>

## Waves / sequencing

Group children into waves that respect dependencies and keep concurrent
issues file-disjoint (one PR per issue).

```text
Wave A (parallel, file-disjoint): #..., #...
Wave B (after A):                 #...
```

## Cross-cutting decisions

- **OPEN** -- ...
- **RESOLVED** -- ...

## Workflow (per AGENTS.md)

ASCII-only; one PR per issue; branch off `donkey-kong-sandbox`; conventional
commits; CHANGELOG on behavior change; additive `--json`; docs follow code.
