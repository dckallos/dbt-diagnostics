---
name: issue-governance
description: Audit or standardize exactly one dbt-diagnostics issue against contract v1 without mutating GitHub. Use for contract checks, bounded review packets, readiness evidence, and local proposed-body validation.
---

Input: exactly one issue number and, when offline, an explicit tracker snapshot.

1. Read `AGENTS.md`, `docs/ISSUE_CONTRACT_V1.md`, and
   `docs/ISSUE_GOVERNANCE.md`.
2. Run the deterministic contract audit:
   `python scripts/triage/triage.py contract --issue <issue>`.
3. For offline work, add
   `--snapshot output/triage/snapshot.json`.
4. Load only the issue, direct dependencies, relevant parent excerpt,
   referenced paths, direct callers, tests, and design docs.
5. Record facts and uncertainty in local semantic-evidence JSON. Do not claim
   semantic sufficiency from headings or labels.
6. Generate a bounded local packet with:
   `python scripts/triage/triage.py review-packet --issue <issue>`.
7. Revise `proposed-body.md` locally only when needed, then validate it with:
   `python scripts/triage/triage.py standardize --issue <issue> --proposed-body <path>`.
8. Stop before any GitHub mutation. Present the exact proposed body and reasons
   for maintainer review.

Never create, edit, close, label, milestone, or move a GitHub item. Never add an
issue-body write operation to a plan or allowlist.
