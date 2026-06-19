---
name: Epic
about: An umbrella tracking a body of work. The live status board reconciled against open/closed child issues.
title: "[Epic] "
labels: epic
---

## Epic: <name>

Design doc: [`docs/<DOC>.md`](https://github.com/dckallos/dbt-diagnostics/blob/donkey-kong-sandbox/docs/<DOC>.md)

### Thesis

<!-- The one-paragraph charter this epic defends. -->

### Status (`<date>`)

<!-- Reconcile against REALITY, not intent. List merged/closed children as
closed; do not present completed work as an unchecked build step (an
OUTPUT_FOUR Section 6.4 drift failure). -->

### Build order / children

<!-- Checkboxes mirror real issue state. -->

- [ ] #<n> -- `type:` <one-line scope> [deps]
- [x] #<n> -- <closed child> (CLOSED, PR #<m>)

### Review-driven additions (gated)

<!-- Only changes the red-team stood behind become children; rejected items are
verification tasks at most. Reference OUTPUT_THREE change numbers + OUTPUT_FOUR
findings. -->

### Cross-cutting / open decisions

- **OPEN** -- <decision that blocks children>
- **RESOLVED** -- <decision + where recorded>

### Workflow (per AGENTS.md)

ASCII-only; one PR per issue; branch off `donkey-kong-sandbox`; conventional
commits; CHANGELOG on behavior change; docs follow code.
