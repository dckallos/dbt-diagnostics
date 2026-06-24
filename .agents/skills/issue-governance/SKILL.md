---
name: issue-governance
description: Audit or standardize exactly one dbt-diagnostics issue against contract v1 without mutating GitHub. Use for issue review packets, readiness evidence, and local proposed-body validation.
---

Input: exactly one issue number and, when offline, an explicit tracker snapshot.

1. Read `AGENTS.md`, `docs/ISSUE_CONTRACT_V1.md`, and
   `docs/ISSUE_GOVERNANCE.md`.
2. Run the deterministic contract audit:
   `python scripts/triage/triage.py contract --issue <issue>`.
3. Load only the issue, direct dependencies, relevant parent excerpt,
   referenced paths, direct callers, tests, and design docs.
4. Record facts and uncertainty in local semantic-evidence JSON. Do not claim
   semantic sufficiency from headings or labels.
5. Generate a bounded packet with `review-packet`.
6. Revise `proposed-body.md` locally only when needed.
7. Re-audit it with `standardize`.
8. Stop before any GitHub mutation. Present the exact proposed body and reasons
   for maintainer review.

Never create, edit, close, label, milestone, or move a GitHub item. Never add an
issue-body write operation to a plan or allowlist.
