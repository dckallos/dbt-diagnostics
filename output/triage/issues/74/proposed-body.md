## Summary

Beta-test the new Codex skills and read-only governance toolchain that now lives
under `.agents/` and `.codex/`, and decide what is still needed before it is
production-ready. This issue is deliberately the test fixture: it gets pulled
through the full governance lifecycle so we can watch each stage behave on a
real, slightly nonconformant issue.

This issue intentionally does NOT satisfy the v1 issue contract. The gaps are the
point -- they give the conform / draft / standardize flow something real to do.
Please do not pre-fix them before the test runs.

## Evidence and confidence

> Draft (machine-authored; needs maintainer verification)

Proven:

- The issue-governance skill requires the deterministic contract audit,
  review-packet generation, local proposed-body validation, and stopping before
  any GitHub mutation. Source:
  `.agents/skills/issue-governance/SKILL.md` "Stop before any GitHub mutation."
- The relay-coordinator skill is read-only and bounded to frontier selection
  and handoff, not implementation or tracker mutation. Source:
  `.agents/skills/relay-coordinator/SKILL.md` "never for implementation or GitHub mutation."
- The Codex wrapper dispatches stable actions through `.codex/bin/action.sh`,
  and the audit/frontier wrappers call `scripts/triage/triage.py` through the
  repository virtualenv. Sources: `.codex/bin/action.sh` "audit)" and
  `.codex/bin/triage-frontier.sh` "frontier --mode".
- The deterministic issue contract writes unresolved placeholder text until a
  human or assist layer supplies real section content, and the contract audit
  rejects any remaining placeholder. Sources:
  `scripts/triage/contract.py:UNRESOLVED_PLACEHOLDER`,
  `scripts/triage/contract.py:propose_normalized_body`, and
  `scripts/triage/test_contract.py:test_proposed_body_is_conformant_once_placeholders_are_resolved`.
- The readiness audit and frontier are separate gates. A conformant issue still
  needs source-aware semantic evidence before implementation can be selected.
  Sources: `scripts/triage/readiness.py:audit_all_issues`,
  `scripts/triage/frontier.py:implementation_frontier_candidates`, and
  `docs/CODEX_RELAY.md` "Issue standardization happens before this relay."
- File citations are supposed to be content-verifiable. Source:
  `scripts/triage/common.py:parse_file_references`.

Observed in this dogfood run:

- `python scripts/triage/triage.py contract --issue 74` inferred
  `test_verification` and reported missing required sections.
- `python scripts/triage/triage.py audit --issues 74` reported
  `needs_contract_revision` and a missing path for `.agents/.codex`.
- `bash .codex/bin/action.sh context 74` failed in this session because local
  `gh` is not authenticated, while direct deterministic triage reads of the
  public issue succeeded.

Uncertain until maintainer verification:

- Whether the conformed body should be applied to the live issue.
- Whether the current wrapper behavior around unauthenticated public reads is
  intentional.
- Whether the full gate has passed on both Python 3.11 and Python 3.12.

## Current wrong behavior or gap

> Draft (machine-authored; needs maintainer verification)

This issue is intentionally a slightly nonconformant fixture, but the live body
is currently not implementation-ready under contract v1. It omits the formal
evidence, acceptance, test-plan, traceability, offline/live, and external
evidence sections that the deterministic audit requires for a `test` issue with
`tier-a` context.

The issue also references `.agents/.codex` as though it were a repository path.
The individual roots `.agents/` and `.codex/` exist, but the combined path does
not, so the readiness audit reports a missing repository path. This is useful
dogfood feedback for `scripts/triage/common.py:referenced_paths` and
`scripts/triage/readiness.py:audit_all_issues`.

The wrapper path is partially blocked in this session: `doctor` works, but
`context 74` rejects unauthenticated `gh` before reaching the public issue read.
That makes the direct Python command path the practical read-only route here.

## Acceptance criteria

> Draft (machine-authored; needs maintainer verification)

- Positive coverage: `python scripts/triage/triage.py contract --issue 74`
  reports the current live issue as `needs_contract_revision`, and
  `python scripts/triage/triage.py review-packet --issue 74 --semantic-evidence output/triage/issues/74/semantic-evidence.json --output-dir output/triage/issues/74`
  writes `contract.json`, `review-packet.json`, and `proposed-body.md`.
- Positive coverage: after the placeholder sections are drafted,
  `python scripts/triage/triage.py standardize --issue 74 --proposed-body output/triage/issues/74/proposed-body.md --output-dir output/triage/issues/74`
  exits successfully and writes `standardization.json` with
  `github_mutation: false`.
- Negative coverage: no tool in this lifecycle writes the issue body, title,
  state, labels, milestone, Project item, branch, worktree, or pull request.
  The forbidden body/title mutation guard remains covered by
  `scripts/triage/test_triage.py:test_metadata_mutation_allowlist_is_exact_and_body_updates_are_forbidden`.
- Degradation coverage: if local `gh` authentication is unavailable, the run
  records the blocked wrapper command, uses read-only deterministic commands or
  an explicit snapshot, and does not invent live tracker evidence.
- Regression coverage: the placeholder rejection, content-anchor parsing,
  readiness audit, and frontier coverage gates continue passing their focused
  tests before the issue is treated as production-ready.
- The report records the proposed implementation choices, the Python 3.11 and
  Python 3.12 full-gate results, and any brittle or underspecified lifecycle
  behavior found during dogfooding.

## Focused test plan

> Draft (machine-authored; needs maintainer verification)

Focused governance commands:

- `bash .codex/bin/action.sh doctor`
- `bash .codex/bin/action.sh context 74`
- `python scripts/triage/triage.py contract --issue 74`
- `python scripts/triage/triage.py audit --issues 74`
- `python scripts/triage/triage.py review-packet --issue 74 --semantic-evidence output/triage/issues/74/semantic-evidence.json --output-dir output/triage/issues/74`
- `python scripts/triage/triage.py standardize --issue 74 --proposed-body output/triage/issues/74/proposed-body.md --output-dir output/triage/issues/74`
- `bash .codex/bin/action.sh frontier audit --issues 74 --json`
- `bash .codex/bin/action.sh frontier implement --issues 74 --json`

Focused regression tests:

- `pytest -q scripts/triage/test_contract.py scripts/triage/test_readiness.py scripts/triage/test_frontier.py scripts/triage/test_triage.py`
- `python -m compileall -q dbt_diagnostics scripts/triage`

Repository gate:

- `bash .codex/bin/action.sh full`

The focused suite should explicitly cover positive, negative, degradation, and
regression behavior for placeholder rejection, local-only standardization,
content-anchored file references, read-only relay selection, and unauthenticated
wrapper degradation.

## Scope and likely files

- In scope: exercising the read-only governance lifecycle end to end from my
  local Codex session, and recording what each stage does on a real issue.
- Non-goals: any GitHub mutation performed by the tooling; warehouse or live
  probes; changing the deterministic gates; modifying `.github/workflows/*`.

## Explicit non-goals

> Draft (machine-authored; needs maintainer verification)

- Do not mutate GitHub from the deterministic toolchain or from this issue
  governance pass.
- Do not change `.github/workflows/*`.
- Do not add Snowflake, warehouse, live probe, or data-scanning behavior.
- Do not relax the deterministic gates just to make this fixture pass.
- Do not replace maintainer review of the proposed body with an automated issue
  write.
- Do not use this dogfood issue to ship unrelated product behavior.

## Dependencies and traceability

> Draft (machine-authored; needs maintainer verification)

- Direct dependencies: none found in the live issue body or review packet.
- Parent epic: none recorded. My implementation recommendation is to track this
  governance/tooling stream under a new dedicated repository-governance epic
  rather than under product epics #4, #48, or #68.
- Related design and process docs:
  `docs/ISSUE_CONTRACT_V1.md`, `docs/ISSUE_GOVERNANCE.md`,
  `docs/CODEX_RELAY.md`, and `docs/FRONTIER_SCHEMA_V1.md`.
- Source surfaces:
  `.agents/skills/issue-governance/SKILL.md`,
  `.agents/skills/relay-coordinator/SKILL.md`, `.codex/bin/action.sh`,
  `.codex/bin/common.sh`, `scripts/triage/triage.py`,
  `scripts/triage/contract.py`, `scripts/triage/readiness.py`,
  `scripts/triage/frontier.py`, and `scripts/triage/common.py`.
- Tests:
  `scripts/triage/test_contract.py`, `scripts/triage/test_readiness.py`,
  `scripts/triage/test_frontier.py`, and `scripts/triage/test_triage.py`.

## Offline behavior

> Draft (machine-authored; needs maintainer verification)

Without authenticated tracker access, the lifecycle can still validate local
code, parse an explicit snapshot, inspect generated packets, draft placeholder
sections, and run `standardize` against `proposed-body.md`. It cannot prove that
the live issue body, labels, comments, Project state, or pull-request conflicts
are current unless a fresh snapshot or live read is available.

Unavailable evidence is represented as uncertainty in
`output/triage/issues/74/semantic-evidence.json` and as readiness blockers or
warnings in the audit output. The local proposed body remains a review artifact
until the maintainer applies it by hand.

## Live behavior and cost tier

> Draft (machine-authored; needs maintainer verification)

This issue is `tier-a` repository-governance work. The live operations are
GitHub tracker metadata reads through `gh` or the connected GitHub app; they do
not call Snowflake, inspect warehouse data, or run Tier-B scans. The
deterministic commands used here are read-only for GitHub issue metadata, and
`standardize` writes only local files under `output/triage/issues/74/`.

Any eventual live issue-body update is outside the toolchain and is performed
manually by the maintainer after reviewing the exact proposed body.

## External evidence, permissions, credentials, or fixtures

> Draft (machine-authored; needs maintainer verification)

- Maintainer review is required before applying
  `output/triage/issues/74/proposed-body.md` to GitHub.
- The repository can verify Python support from `pyproject.toml`
  "requires-python = \">=3.11\"".
- This session saw Python 3.11.11, Python 3.12.9, and a Python 3.12.9 virtualenv,
  and `bash .codex/bin/action.sh full` passed under both Python versions.
- Local ChatGPT/Codex account state is outside the checkout. The repo can record
  whether commands passed, but it cannot prove the account mode from source.
- No Snowflake account, warehouse credential, protected fixture, or external
  data sample is required for this issue.

## Additional context retained from the current issue

### Test setup (where this runs)

I (the maintainer) am running these tests on my local machine using the local
Codex app, signed in with my ChatGPT Pro account (no OpenAI API key). The
driving, drafting, and any eventual GitHub writes happen from my local Codex
session. The toolchain itself stays read-only and never writes to GitHub; I
apply any conformed issue body by hand after reviewing it.

### Components under test

- Skills: `.agents/skills/issue-governance/SKILL.md` and the
  `.agents/skills/relay-coordinator` skill.
- Wrappers: `.codex/bin/action.sh` (actions: `context`, `audit`, `frontier`,
  `check`, `full`).
- Deterministic toolchain:
  - `scripts/triage/common.py:parse_file_references`
  - `scripts/triage/readiness.py:audit_all_issues`
  - `scripts/triage/contract.py:propose_normalized_body`
  - `scripts/triage/frontier.py:implementation_frontier_candidates`

(References above use verifiable symbol anchors on purpose, to dogfood the new
content-anchor checks rather than bare line numbers.)

### How this is scoped

The work is split into what I do and what I expect Codex to do. My steps are
exact commands. The Codex side is described as outcomes, not a recipe: choose the
approach, the commands, and the implementation yourself. If a better path exists
than what is implied here, take it and tell me why. The goal of this beta is
partly to see how much Codex can design on its own, so I am deliberately leaving
the "how" open.

### My actions (maintainer, local)

1. Stand up the environment and authenticate Codex against my ChatGPT Pro account:

   ```bash
   bash .codex/bin/action.sh setup
   bash .codex/bin/action.sh doctor
   codex login            # browser OAuth; choose "Continue with Google"
   codex login status     # confirm ChatGPT-plan auth, not an API key
   ```

2. Point Codex at this issue and let it run the lifecycle (it chooses the how):

   ```bash
   codex --profile task "Work issue #74: run the .agents/.codex governance lifecycle end to end, conform this issue to contract v1, decide the implementation, and report findings."
   ```

3. Run the local gate (CI parity) before trusting any result:

   ```bash
   bash .codex/bin/action.sh full
   ```

4. Review the placeholder-to-draft diff, then apply the conformed body to GitHub
   by hand (the tooling never writes):

   ```bash
   gh issue edit 74 --body-file output/triage/issues/74/proposed-body.md
   ```

5. Make the production-readiness decisions listed below.

### Lifecycle commands (reference)

Exact governance commands available to Codex (and to me). Codex decides the
sequence and may deviate; nothing here writes to GitHub.

```bash
# Live context for this issue (capture a snapshot first if working offline)
bash .codex/bin/action.sh context 74

# Read-only audits
python scripts/triage/triage.py contract --issue 74
python scripts/triage/triage.py audit --issues 74

# Review packet -> writes contract.json, review-packet.json, proposed-body.md
python scripts/triage/triage.py review-packet --issue 74 \
  --output-dir output/triage/issues/74

# After drafting the missing sections into proposed-body.md, validate the contract
python scripts/triage/triage.py standardize --issue 74 \
  --proposed-body output/triage/issues/74/proposed-body.md

# Read-only frontier selection
python scripts/triage/triage.py frontier --mode implement
```

### Codex's expected actions (design left to Codex)

Treat these as the outcomes I want, not a script. You decide how to achieve them.

- Pull this issue and conform it to contract v1: surface the intentional gaps,
  draft only the missing sections from cited source using verifiable anchors
  (`path:symbol` or `path "snippet"`, never a bare `path:line`), mark each draft
  as machine-authored and needing verification, and get `standardize` to pass
  without fabricating acceptance facts, test results, or decisions.
- Decide the implementation details for any follow-on work this issue implies. I
  am intentionally not prescribing them -- propose the design, the boundaries,
  and the tests yourself.
- Carry the issue through the rest of the lifecycle you judge relevant (readiness
  audit, frontier selection, worker packet, and ultimately a PR) and report where
  the tooling or skills helped or got in the way.
- Flag anything that felt underspecified, brittle, or production-blocking as you
  go -- that feedback is a primary deliverable of this beta.

### Production-readiness decisions (the decision part)

- [ ] Decide where the issue-governance work itself is tracked. No parent epic
      exists for the toolchain today; the product epics are #4, #48, and #68.
- [ ] Decide whether the AI-drafting assist layer stays skill-only or gains a
      deterministic harness.
- [ ] Confirm `bash .codex/bin/action.sh full` (CI parity) passes for the
      toolchain on Python 3.11 and 3.12.
- [ ] Reconcile the label taxonomy: labels referenced in
      `scripts/triage/policy.toml` that are not yet real labels in this repo.
- [ ] Record the dogfooding result in `docs/PROGRESS_LOG.md`.

### Intentional contract gaps (do not pre-fix before the test)

This body omits a formal Evidence-and-confidence block, observable acceptance
criteria, a focused test plan, and a dependencies/traceability section on
purpose, so the conform-and-draft flow has real work to surface.

## Contract audit notes

The following coverage categories remain explicit review items:
- positive
- negative
- degradation
- regression
