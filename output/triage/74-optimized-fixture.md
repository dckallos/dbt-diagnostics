## Summary

Beta-test the Codex governance toolchain by running the issue-governance
lifecycle end to end against this very issue, then have Codex report what to
optimize next in the `.agents` and `.codex` scaffolding and how. This issue is
the recurring governance dogfood fixture: each re-run should both exercise the
lifecycle and produce a fresh, ranked set of optimization recommendations.

The recommendations below are deliberately open-ended. The candidate areas are
examples, not a checklist. Codex should discover, verify against source, and
rank optimizations on its own, may add areas not listed here, and may argue that
a listed area is not worth doing. Do not treat this issue as a fixed work order.

## Evidence and confidence

Confidence: medium. The toolchain is exercised on every re-run, so its current
behavior is observable directly rather than assumed.

- The disposition step lives in `.agents/skills/issue-governance/SKILL.md`
  "disposition hypothesis" and gates whether standardization proceeds.
- Deterministic disposition is a fixed map in
  `scripts/triage/readiness.py:recommended_disposition`, derived in
  `scripts/triage/readiness.py:audit_issue`.
- Coverage detection is `scripts/triage/contract.py:acceptance_coverage`.
- Offline issue access resolves through
  `.codex/scripts/task_context.py:resolve_snapshot_path`.
- The draft anchor self-check is `.codex/scripts/anchor_check.py`.

Every claim Codex adds must carry a content anchor (`path:symbol` or
`path "snippet"`); do not cite bare line numbers and do not invent anchors.

## Current wrong behavior or gap

There is no standing, repeatable way to ask the toolchain to critique and
improve itself. Optimization findings have come from ad-hoc review rather than
from a fixture that produces ranked recommendations on each run, so improvements
are easy to lose between sessions.

## Acceptance criteria

- Positive: a clean re-run produces a disposition of `keep`, a contract-conformant
  proposed body, and a ranked list of optimization recommendations for `.agents`
  and `.codex`, each tied to a verifiable source anchor.
- Negative: any recommendation whose anchor does not resolve in current source is
  dropped or marked unverified rather than asserted.
- Degradation: when `gh` is unavailable, the run still completes from a snapshot
  and says so, rather than failing or silently guessing.
- Regression: the run performs no GitHub mutation, no code implementation, and no
  cross-issue changes; prior governance behavior is unchanged.

## Focused test plan

Run the issue-governance lifecycle on this issue only, covering the positive
(clean keep + recommendations), negative (unresolvable-anchor), degradation
(offline snapshot) and regression (no-mutation) cases above. Confirm the draft
anchor self-check reports zero unresolved anchors before the gate, and that the
deterministic gate accepts the body.

## Scope and likely files

In scope (areas Codex may inspect; not exhaustive, not a checklist):

- `.agents/skills/issue-governance/SKILL.md`
- `.codex/scripts/task_context.py`
- `.codex/scripts/anchor_check.py`
- `scripts/triage/readiness.py`
- `scripts/triage/contract.py`
- `scripts/triage/policy.toml`

Out of scope: implementing the recommendations in this run.

## Explicit non-goals

- No GitHub mutation by the toolchain; the maintainer applies any accepted body.
- No code implementation, refactor, or dependency change during the run.
- No cross-issue work (deduplication, splitting, ordering) inside this per-issue run.
- No prescription of a single "correct" optimization path; ranking and approach
  are left to Codex's judgment.
- No warehouse-scanning probes.
- No deterministic-gate or workflow-file changes.

## Negative, degradation, and regression coverage

Negative, degradation, and regression cases are enumerated in the acceptance
criteria above and exercised by the focused test plan: unresolved-anchor
handling (negative), offline snapshot fallback (degradation), and the
no-mutation invariant (regression).

## Dependencies and traceability

- Parent: the repository-governance track (home still to be decided; not a
  product epic).
- Related: the proposed follow-up issues under
  `output/triage/proposed-issues/`.
- This issue depends on nothing and blocks nothing; it is a standing fixture.

## Offline behavior

When `gh` is unauthenticated or absent, read this issue from a snapshot.
Generate one with `python scripts/triage/triage.py snapshot --output
output/triage/snapshot.json`; `.codex/scripts/task_context.py:resolve_snapshot_path`
then discovers it automatically. The lifecycle is otherwise fully offline.

## Live behavior and cost tier

Tier A only: metadata and local file reads. No warehouse access and no scanning
probes are permitted by this fixture.

## External evidence, permissions, credentials, or fixtures

None required beyond read access to the public issue. Applying the resulting
proposed body to GitHub is a manual maintainer step performed outside the run.
