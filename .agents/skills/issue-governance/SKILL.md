---
name: issue-governance
description: Audit exactly one dbt-diagnostics issue with the supported read-only governance CLI. Use for focused issue findings and local review; never mutate GitHub.
---

Input: exactly one issue number and, when offline, an explicit tracker snapshot.

1. Read `AGENTS.md`, `docs/ISSUE_CONTRACT_V1.md`, and
   `docs/ISSUE_GOVERNANCE.md`.
2. Run the focused audit:
   `python scripts/triage/triage.py audit --issues <issue>`.
3. For offline work, add
   `--snapshot output/triage/snapshot.json`.
4. Load only the issue, direct dependencies, relevant parent excerpt,
   referenced paths, direct callers, tests, and design docs.
5. Record semantic facts and uncertainty separately from deterministic audit
   findings. Do not claim semantic sufficiency from headings or labels.
6. Draft any proposed issue-body text as a local file for maintainer review.
7. Stop before any GitHub mutation. Present the exact proposed text and reasons.

PR #73 does not expose standalone `contract`, `review-packet`, or `standardize`
CLI commands. Never create, edit, close, label, milestone, or move a GitHub item.
Never add an issue-body write operation to a plan or allowlist.
