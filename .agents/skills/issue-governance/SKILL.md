---
name: issue-governance
description: Audit or standardize exactly one dbt-diagnostics issue against contract v1 without mutating GitHub. Use for contract checks, bounded review packets, readiness evidence, and local proposed-body validation.
---

Input: exactly one issue number and, when offline, an explicit tracker snapshot.

## Scope: one issue, no cross-issue reasoning

This skill nitpicks exactly one issue. It never loads the whole backlog and never
decides anything that requires comparing issues. Cross-issue judgment
(deduplication, splitting, ordering, project structure) is out of scope and is
left to the deterministic synthesis pass and the maintainer.

When you report recommended decisions, do not propose local multi-Python-version
runs (for example running the suite under both 3.11 and 3.12). Use the single
controlled `.venv`; multi-version coverage is CI's responsibility.

## 1. Load only what this issue needs

1. Read `AGENTS.md`, `docs/ISSUE_CONTRACT_V1.md`, and
   `docs/ISSUE_GOVERNANCE.md`.
2. Run the deterministic contract audit:
   `python scripts/triage/triage.py contract --issue <issue>`.
   For offline work, add `--snapshot output/triage/snapshot.json`. If `gh` is
   unavailable or unauthenticated, generate that snapshot once with
   `python scripts/triage/triage.py snapshot --output output/triage/snapshot.json`;
   `context` and the triage commands then fall back to it automatically.
3. Load only the issue, direct dependencies, relevant parent excerpt,
   referenced paths, direct callers, tests, and design docs. Do not preload the
   whole repository.

## 2. Disposition hypothesis (cheap, single-issue only)

Before drafting anything, record a disposition hypothesis based ONLY on this
issue's own text and the paths it names:

- `keep` -- the issue is real and should be standardized; continue.
- `likely-duplicate-of #N` -- the body itself points at another issue.
- `likely-split` -- the body describes more than one coherent PR.
- `likely-wont-do` -- the body describes work the scope guard rejects.

Write the hypothesis and its evidence into the semantic-evidence JSON. If the
hypothesis is anything other than `keep`, STOP and escalate to the maintainer;
do not standardize an issue whose existence is in question. You may not confirm a
duplicate or a merge yourself -- that is a cross-issue decision.

## 3. Record evidence, not impressions

Record facts and uncertainty in local semantic-evidence JSON. Do not claim
semantic sufficiency from headings or labels. Every source claim must carry a
content anchor (`path:symbol` or `path "snippet"`), never a bare `path:line`.

## 4. Draft, then self-verify, then gate (bounded loop)

1. Generate a bounded local packet:
   `python scripts/triage/triage.py review-packet --issue <issue>`.
2. Revise `proposed-body.md` locally, drafting ONLY missing or placeholder
   sections. Do not rewrite sections that already conform.
3. Optional fast pre-check. The authoritative anchor gate is `standardize`
   (step 4): it resolves every `path:symbol` / `path "snippet"` in the proposed
   body and blocks acceptance on an unresolved or past-EOF anchor, so a separate
   manual anchor check is no longer required. For a quicker local loop you may
   still run the focused draft checker first:
   `python .codex/scripts/anchor_check.py output/triage/issues/<issue>/proposed-body.md`
   Never invent a symbol, line, or snippet to satisfy a section.
4. Validate with the deterministic gate. `standardize` checks sections,
   coverage, title AND content anchors; it returns exit 0 only when the contract
   is accepted and every `path:symbol` / `path "snippet"` resolves (an
   unresolved or past-EOF anchor blocks acceptance):
   `python scripts/triage/triage.py standardize --issue <issue> --proposed-body <path>`.
5. Repair loop: if the gate reports errors, read the findings, repair the draft,
   and repeat from step 3. Bound this to 3 iterations. The gate is the oracle:
   the LAST thing you run before declaring success or handing off must be a
   passing `standardize` on the FINAL body. If you edit the body after a passing
   run, you must re-run `standardize`; never present or apply a body that has
   changed since its last green gate.

## 5. Stop conditions and escalation

Stop and present to the maintainer when ANY of these holds:

- the gate passes with only acceptable warnings (success);
- a required section cannot be grounded without fabricating a fact;
- the same finding survives two repair passes;
- the disposition hypothesis is not `keep`.

The deterministic gate is the oracle. Iterate your draft against it; never edit
the gate, loosen the contract, or fabricate content to force a pass. Stop before
any GitHub mutation and present the exact proposed body and the reasons.

Never create, edit, close, label, milestone, or move a GitHub item. Never add an
issue-body write operation to a plan or allowlist.
