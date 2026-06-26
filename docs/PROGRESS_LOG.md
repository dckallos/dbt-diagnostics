# Progress log

> The newest dated entry is the current state. Append; do not rewrite history.
> When resuming, read the latest entry first and skip items already done.
>
> This log replaces the older hand-off notes. `docs/HANDOFF_PROMPT.md` and
> `docs/HANDOFF_PROMPT_2.md` are kept for history as of 2026-06-14 -- read them
> for background, but record new progress here.

---

## 2026-06-14 -- continuity and workflow scaffolding

**What changed**
- Committed the Live Verification Engine design doc
  (`docs/DESIGN_LIVE_VERIFICATION.md`) on `donkey-kong-sandbox`: initial draft,
  then terminal+JSON output, effort/usefulness and cost tiers, and the
  proactive/reactive section.
- Opened the epic and feature issues:
  - #4 Epic: Live Verification Engine (status board)
  - #7 single-root-cause aggregator (Tier A)
  - #9 incremental stale-state detector (Tier A)
  - #5 upstream grain tracing (Tier B, flagship, gated)
  - #6 orphan-FK detection (Tier B)
  - #8 UNION-branch attribution
  - #10 static grain-consistency cross-check (proactive, $0)
- Added project conventions, this progress log, CONTRIBUTING, and the GitHub PR
  and issue templates on branch `chore/agent-continuity-workflow` (PR #11 into
  `donkey-kong-sandbox`). CI workflow added separately.

**Finding**
- `sqlglot>=26,<28` is already a core dependency in `pyproject.toml`, so the
  design doc's open question about adding a parser dependency for UNION
  attribution is moot. Correct section 7 in a follow-up.

**Current state**
- `donkey-kong-sandbox`: design doc + the 7 issues.
- `chore/agent-continuity-workflow`: the conventions/workflow docs, in review.
- No package code (`dbt_diagnostics/`) changed yet; no feature implemented yet.

**Next steps**
- After PR #11 merges, point epic #4 at these docs as the status board.
- Start the first feature: #7 (aggregator) -- lowest effort, $0, and it builds
  the test-failure-finding scaffolding the flagship #5 needs.
- Correct design doc section 7 (sqlglot already present) and decide the Tier-B
  cost ceiling and grain-source questions that gate #5.

**Open decisions**
- Tier-B cost ceiling (row-count cap / SAMPLE / per-run query cap / walk depth).
- Grain source: declared uniqueness tests vs. inferred from
  `generate_surrogate_key` args.
- schema_version policy (CONTRIBUTING.md sets additive-only).
- Whether to take on the deferred live invariant-scan epic (design doc 6/9).

**Be careful**
- Do not re-introduce static linting (scope guard in AGENTS.md).
- Do not add a Tier-B probe without a cost gate.
- Do not push directly to `donkey-kong-sandbox` or `main`; use a feature branch
  and a PR.

End of session -- 2026-06-14 continuity and workflow scaffolding

---

## 2026-06-14 -- issue #7 single-root-cause aggregator implemented

**What changed**
- Cut `feat/7-root-cause-aggregator` off `donkey-kong-sandbox` and implemented
  issue #7 (the first Live Verification Engine probe).
- New `dbt_diagnostics/root_cause.py`: collapses Snowflake "object does not
  exist" (002003) errors into one `RootCauseGroup` per missing object, with a
  single live-disambiguated verdict (`never_built` / `exists_now` / `denied` /
  `unverified`). `denied` is decided by `SHOW GRANTS`, not by `table_exists`,
  since `SHOW TABLES` cannot separate "missing" from "invisible to the role".
  Reuses `schema_inspector.table_exists` and `grants.check_role_grants`.
- New `dbt_diagnostics/enrichers/run_identity.py`: recovers the run's role from
  the failing `query_id` via `INFORMATION_SCHEMA.QUERY_HISTORY` (Tier 0), with
  declared-profile (Tier 2) and session (Tier 3) fallbacks; watermark check
  separates "lagging" from "never" with one bounded retry; flags role drift.
- Wired into `main.py` (`cmd_diagnose` + `_try_enrich` build the groups; `--json`
  bumped to `schema_version` 1.1 with an additive `root_cause_groups` key),
  `renderer.py` (new `root_cause_groups` arg), and `report.j2` (new ROOT CAUSE
  section reusing the `lineage_trace` partial).
- Added `tests/test_root_cause.py` (10) and `tests/test_run_identity.py` (8).
- Updated `CHANGELOG.md` `[Unreleased]`.
- workspace stage: pushed to GitHub branch `feat/7-root-cause-aggregator`
  (three commits). applied-to-account: n/a. pushed-to-Mac: no (branch is remote).

**Verification (important caveat)**
- This was authored from a Cortex Code Snowsight sandbox that CANNOT run the
  repo's pytest suite (no PyPI/pytest, no github clone -- proxy allowlist). I
  verified by: `py_compile` on all new/changed Python; a standalone runner that
  executed all 18 new test functions against the real `root_cause` /
  `run_identity` logic (18/18 pass); and a Jinja render of `report.j2` + the
  `lineage_trace` partial (collapsed-group case and empty case both OK).
- NOT yet run on a Mac: the full 336-test baseline. The `--json`
  `schema_version` 1.0 -> 1.1 bump WILL break any existing test that asserts the
  top-level version string -- those assertions must be updated to 1.1 (additive
  key add is intended). Run `pytest dbt_diagnostics/tests -q` locally and fix
  any version-string assertions before merging.

**Next steps**
- On the Mac: pull the branch, run `pytest dbt_diagnostics/tests -q`, fix any
  schema_version assertions, eyeball `dbt-diagnostics demo` for the new ROOT
  CAUSE section, then review PR #14.
- File/triage the follow-up issue: opt-in dbt `on-run-start` identity-stamp hook
  (highest-fidelity role source; out of #7 scope).

**Be careful**
- Do not merge PR #14 from the agent -- owner reviews and merges.
- Do not re-introduce static linting; keep probes Tier A (no warehouse scans).
- The vendored `models.py` / `grants.py` used for the sandbox test-run were NOT
  pushed; the real modules are unchanged.

End of session -- 2026-06-14 issue #7 single-root-cause aggregator implemented

---

## 2026-06-14 -- issue #7 merged (test fix + follow-up cleanup)

**What changed**
- Owner re-ran the suite on the Mac: `pytest dbt_diagnostics/tests -q` ->
  354 passed, 0 failed.
- The only baseline failure was a stale assertion in `tests/test_main.py`
  pinning the top-level `--json` `schema_version == "1.0"`. Updated it to
  `"1.1"` and added a positive assertion for the new additive
  `root_cause_groups` key so the schema change is covered (commit 64ccc84).
- Marked PR #16 ready and squash-merged it into `donkey-kong-sandbox`
  (issue #7 closed).
- Closed issue #19 as a duplicate of #17: the attested-run-identity hook
  follow-up was already filed as #17 by the implementing session.

**Corrections to the prior entry**
- The aggregator PR is #16 (the prior entry said "#14"); now merged.
- The empirical 354-test run also clears the prior entry's caveat -- the new
  modules' assumptions about `models.py` / `grants.py` attributes are valid
  against the real modules (the 18 new tests exercise them and pass).

**Current state**
- `donkey-kong-sandbox`: now includes the #7 aggregator (one squashed commit).
- Open follow-up: #17 -- attested run-identity dbt hook (Tier A, opt-in).

**Next steps**
- Optional: eyeball `dbt-diagnostics demo` for the new ROOT CAUSE section.
- Next epic-#4 feature by build order: #9 (incremental stale-state detector,
  Tier A), then the gated flagship #5.

**Be careful**
- Tier A only; no static linting; keep `--json` schema additive.
- `main` stays stable; only promote `donkey-kong-sandbox` -> `main` at a release.

End of session -- 2026-06-14 issue #7 merged

---

## 2026-06-16 -- schema-version detection + defensive handling merged; audit

**What changed (since 2026-06-14)**
- PR #22 merged: artifact schema version auto-detection (`schema_version.py`,
  22 tests, `--json` schema_version bumped 1.1 -> 1.2 additive). Closes #20.
- PR #26 merged: defensive artifact handling (`ArtifactLoadError`, shape
  guards in `_diagnose_all` and `DagWalker`, 11 robustness tests). Closes #24.
- Issues closed: #20, #21 (duplicate of #20), #24.
- Issue #25 filed: remove `linters/` package (resolves scope-guard
  contradiction). Audit complete; type_hazard regex to be salvaged as a
  post-failure enricher.
- PR #27 opened (draft): chaos + property test tiers (issue #23). Cannot push
  workflow files (missing `workflows` scope). Needs local reconciliation
  against the post-#26 core.
- Project audit performed: AGENTS.md now has a "docs follow code" convention
  rule to prevent design-doc drift.

**Current state**
- `donkey-kong-sandbox` HEAD: 78540e4 (includes #7 + #22 + #26).
- Workspace is one commit behind (has #22 but not #26). Sync needed.
- Open issues: #4 (epic), #5, #6, #8, #9, #10, #12, #15, #23, #25.
- Open PR: #27 (draft, test tiers).

**Next steps**
- Land #25 (remove linters/) -- unblocks #8 and resolves the last scope-guard
  contradiction.
- Decide PR #27 fate: reconcile against post-#26, push workflow files
  manually, or strip to essentials (see audit notes).
- Decide Tier-B cost ceiling and grain source to unblock #5 and #6.
- Add labels to issues (priority, tier, status).

**Open decisions**
- Tier-B cost ceiling: row-count cap / SAMPLE / per-run query cap / walk depth.
- Grain source: declared uniqueness tests only (conservative) vs. also infer
  from `generate_surrogate_key` args (broader but riskier).
- PR #27 scope: keep full (chaos + property + tooling + CI) or strip to just
  the injectors and property tests without CI/tooling changes?

**Be careful**
- Do not merge PR #27 without running the suite locally against post-#26.
- Do not update design doc section 2 past-tense until #25 actually lands.
- Do not re-introduce static linting.

End of session -- 2026-06-16 audit and catch-up

---

## 2026-06-16 -- branch-protection policy as code

**What changed**
- Opened issue #32 (chore) to track codifying branch protection.
- On branch `chore/branch-protection-policies` (off `donkey-kong-sandbox`), added
  `scripts/governance/`: `policy.donkey-kong-sandbox.json`, `policy.main.json`,
  and idempotent `apply-`, `export-`, `rollback-` shell scripts plus a README.
- CHANGELOG `[Unreleased]` notes the governance scripts.

**Decisions (mine, this session)**
- Classic branch protection (not rulesets): single user repo, matches the
  existing CONTRIBUTING example, trivial per-branch export/rollback.
- Solo maintainer -> `required_approving_review_count: 0` (a non-zero count
  would deadlock the only merger).
- `enforce_admins: false` on both branches -> owner break-glass.
- `main` policy == `donkey-kong-sandbox` policy by design; files split so `main`
  can diverge later (e.g. signed commits) without touching the integration branch.

**Current state**
- Scripts committed on `chore/branch-protection-policies`; PR opened into
  `donkey-kong-sandbox` (`Closes #32`).
- Policy is NOT yet live on GitHub: the agent cannot set branch protection (no
  MCP endpoint; no `gh`/token in the sandbox). Live state before this work:
  both branches report `protected: false`.

**Next steps**
- Operator runs `./scripts/governance/apply-branch-protection.sh --dry-run`, then
  without `--dry-run`, from a local `gh` admin session. The first real run writes
  before-state snapshots into `scripts/governance/exports/`.
- Merge the PR after CI `test` is green.

**Be careful**
- Re-running `apply-` is safe (PUT replaces the whole config); `rollback-` needs a
  prior `export-` snapshot to restore from.
- `restrictions` must stay `null` (push-restriction lists are org-only).

End of session -- 2026-06-16 branch-protection policy as code

---

## 2026-06-25 -- triage governance correctness pass and next-step handoff

**What changed (branch chore/issue-governance; working tree, validate via CI)**
- Nine read-only correctness fixes to the issue-governance toolchain under
  `scripts/triage/`, each verified against source and reproduced before fixing:
  1. PR-aware dependency resolution (`readiness.py`): dependencies that name a
     pull request resolve against the PR map, not just the issue map.
  2. Inbound `Blocks: #N` enforced as a real inbound block, not an
     informational `related` reference (`readiness.py`).
  3. Scoped Conventional Commit prefixes (`fix(cli):`) strip the scope before
     kind inference (`contract.py`); branch slug too (`frontier.py`).
  4. The configured `docs` type label is recognized in kind inference
     (`contract.py`).
  5. Negation-aware decision/external detection (`readiness.py`): "No open
     decisions" no longer manufactures required work.
  6. Section-aware missing-path detection (`readiness.py`): paths named only in
     the Scope/deliverable section are intended new files and do not block.
  7. PR-aware stale checklist detection (`readiness.py`).
  8. Unresolved-placeholder rejection in the contract audit (`contract.py`): a
     proposed body still containing the generated placeholder is
     `needs_contract_revision`, so `standardize` cannot return success for an
     unresolved contract.
  9. Frontier audit-coverage gate (`triage.py`): the frontier requires the
     readiness audit to cover every issue it will rank; partial
     (issue-filtered) `--audit-file` no longer silently mis-ranks. Audit records
     `audit_scope`.
- Two relay-wrapper fixes (`.codex/bin/common.sh`): `codex_header` and the
  `codex_run` command trace now write to stderr, so `--json` stdout is valid
  JSON for schema/digest consumers.
- Tests added/updated in `test_readiness.py`, `test_contract.py`,
  `test_frontier.py`, `test_triage.py`. CHANGELOG `[Unreleased]` entry added; a
  Quick start added to `docs/ISSUE_GOVERNANCE.md`.

**Validation note**
- The sandbox has no `gh` and no network; `test_contract.py`/`test_triage.py`
  import `pytest` (unavailable here), so those were validated by calling the
  functions directly. `test_readiness.py`/`test_frontier.py` ran via a
  pytest-free harness (readiness 29/29, frontier 15/15). CI `pytest` is the
  authority and must be run before merge. `gh api --slurp` needs gh >= ~2.43.

**Open follow-ups (planned for a fresh context)**
- Enhancement A: AI-assisted authoring of missing contract sections in the
  review-packet flow. The deterministic tool keeps emitting placeholders; an
  agent (issue-governance skill) drafts them, a human reviews, and
  `standardize` verifies structure. No determinism change.
- Enhancement B: file references in issues. Bare `path:line` citations are
  inherently untrustworthy and drift. Do NOT build the audit around validating
  line numbers -- "in-range" must never be read as "fresh" (that repeats the
  visibility-limited -> never_built anti-pattern this pass removed). Instead
  prefer content-anchored references (symbol or quoted snippet the audit
  re-locates) and flag bare line numbers as a citation smell. Out-of-range is
  at most a one-directional "definitely stale" signal.
- Contract-side conditional-section negation blindness (`contract.py`): same
  naive term-presence problem as fix #5, in a different file.
- None of the nine fixes are committed; no `CHANGELOG`/doc edits committed.

**Be careful**
- ASCII-only; do not add the "Co-authored with CoCo" marker to *.py/*.sql/*.ipynb
  (repo voice rule + `check_no_attribution.sh` forbid it).

End of session -- 2026-06-25 triage governance correctness pass

---

## 2026-06-25 -- issue 74 governance dogfood

**What changed**
- Ran the issue-governance and relay lifecycle for #74 without mutating GitHub.
- `bash .codex/bin/action.sh doctor` passed with warnings for dirty wrapper mode
  bits, no `gh` login, and absent compatibility schema cache.
- `.codex/bin/action.sh context 74` failed because local `gh` is not
  authenticated; direct `python scripts/triage/triage.py contract --issue 74`
  could still read the public issue.
- Wrote local artifacts under `output/triage/issues/74/`: contract and review
  packet JSON, semantic evidence, the drafted `proposed-body.md`, and
  `standardization.json`.
- The proposed body is contract-accepted locally (`governance_state:
  conformant`, proposed body digest
  `7c21da370b7f6652e8cc6b8e02a6e6f8b2eb30632ff5fd9a282c92738eee2006`,
  standardization digest
  `91a5e2b119859460b5f97e81d05628dfa8ad3e0079a31dbbb8b0b49491c11bea`).
  It still has the non-blocking recommended-section warning for
  `Negative, degradation, and regression coverage` because only generated
  placeholder sections were drafted.
- Frontier audit mode selects #74; implementation mode returns an empty frontier
  and rejects #74 because the live issue body is still nonconformant, the
  `.agents/.codex` path is missing, maintainer choices remain, and the proposed
  body has not been applied.

**Validation**
- `python -m compileall -q dbt_diagnostics scripts/triage` passed.
- Focused triage tests passed: `128 passed`.
- `bash .codex/bin/action.sh full` passed on Python 3.12.9:
  `603 passed, 2 skipped, 1 warning`.
- `CODEX_VENV_DIR=/private/tmp/dbt-diagnostics-py311-issue74 bash
  .codex/bin/action.sh full` passed on Python 3.11.11:
  `603 passed, 2 skipped, 1 warning`.

**Current state**
- Branch:
  `test/74-test-dogfood-the-agentscodex-codex-skills-governance-lifecycle-this-issue-is-the-fixture`.
- `origin/donkey-kong-sandbox` was fetched and is an ancestor of `HEAD`.
- No GitHub tracker mutation was performed.
- Existing executable-bit changes remain on four `.codex/bin/*` wrapper files.

**Next steps**
- Maintainer reviews `output/triage/issues/74/proposed-body.md` and applies it
  by hand if accepted.
- Fix or intentionally exempt the `.agents/.codex` path reference in the live
  issue body.
- Decide the tracker home for repository-governance work; recommendation from
  this pass is a dedicated governance epic, not product epics #4, #48, or #68.
- Keep AI section drafting as a skill assist for prose, but add a deterministic
  harness for artifact shape, placeholder-only diffs, source-anchor checks, and
  standardize validation.
- Reconcile the missing policy labels reported by audit: `cli`, `config`,
  `docs`, `lineage`, `live`, `output`, `release`, `security`, and `spike`.

**Be careful**
- The generated proposed body contains explicit machine-draft markers required
  by the issue-governance skill; the maintainer should rewrite those into their
  own voice before applying if desired.
- Do not treat the live issue as implementation-ready until the body is applied
  and the frontier is recomputed.

End of session -- 2026-06-25 issue 74 governance dogfood

---

## 2026-06-25 -- per-issue governance scaffolding optimization (review follow-up)

**What changed**
- Acted on a critical review of the #74 governance dogfood. Edited scaffolding
  and toolchain; read-only throughout (no GitHub mutation path added):
  - `.agents/skills/issue-governance/SKILL.md`: added a disposition-hypothesis
    step and an explicit draft -> self-verify-anchors -> standardize ->
    bounded-repair loop with stop/escalation conditions.
  - `AGENTS.md`: added an always-loaded "Issue governance" pointer (read-only,
    one issue at a time, content-anchor rules).
  - `scripts/triage/readiness.py`: `.agents/.codex`-style prose shorthand is now
    a non-blocking `prose-path-shorthand` warning, kept out of
    `missing_repository_paths` (additive field `prose_path_references`).
  - `scripts/triage/contract.py`: suppress the redundant "Negative, degradation,
    and regression coverage" recommendation when that coverage is already
    present in the acceptance/test text.
  - `.codex/scripts/task_context.py`: `context <issue>` gains a `--snapshot`
    offline fallback instead of hard-failing on unauthenticated `gh`.
  - `docs/CODEX_GETTING_STARTED.md`: corrected the project_doc_max_bytes/docs
    explanation (only the AGENTS.md hierarchy counts toward the cap).
- Added tests: `scripts/triage/test_task_context.py` plus new cases in
  `test_contract.py` and `test_readiness.py`.
- Wrote five proposed follow-up issue bodies under
  `output/triage/proposed-issues/`: forest-synthesis disposition pass, read-only
  Projects planner, gated dbt-MCP failure harness, governance issue-kind
  decision, and a draft-level anchor-check CLI. Read-only artifacts; not filed.

**Validation**
- Full triage suite passes under real pytest 9.1.1: `135 passed` (was 128).
- All edited Python compiles; all edited files are ASCII; no "Co-authored with
  CoCo" marker on any .py (repo voice rule + CI guard).
- Re-ran `contract_result` on the existing #74 proposed body: still
  `conformant` and accepted, now with zero warnings.

**Current state**
- Authored in the Snowsight Workspace stage; NOT committed to git, NOT pushed.
  No branch, no PR yet.
- `output/triage/issues/74/proposed-body.md` is unchanged and still accepted; it
  has not been applied to the GitHub issue.

**Next steps**
- Commit this session on a branch off `donkey-kong-sandbox` and open one PR into
  `donkey-kong-sandbox`.
- On the Mac, run the full suite (`pytest -q`, ~603 tests) to confirm no
  regression outside the triage package.
- Re-run the #74 governance lifecycle from scratch with the new scaffolding to
  exercise the disposition step and the clean-warning path end to end.
- File the five proposed follow-up issues if accepted.

**Be careful**
- The toolchain must stay read-only; the Projects-planner follow-up must remain
  plan-only.
- New readiness field `prose_path_references` and finding code
  `prose-path-shorthand` are additive; keep them additive.

End of session -- 2026-06-25 per-issue governance scaffolding optimization

---

## 2026-06-26 -- issue 74 governance lifecycle rerun

**What changed**
- Re-ran the #74 issue-governance lifecycle end to end from the local Codex
  checkout without mutating GitHub.
- Recorded the disposition hypothesis in
  `output/triage/issues/74/semantic-evidence.json`: `keep`, because the live
  issue is explicitly the governance dogfood fixture.
- Regenerated `output/triage/issues/74/` artifacts: snapshot, contract,
  review packet, proposed body, standardization, readiness audit, and both
  frontier coordinator outputs.
- Drafted only placeholder sections in
  `output/triage/issues/74/proposed-body.md`, with machine-draft markers and
  verifiable source anchors. Local `standardize` accepts the body with zero
  findings.

**Validation**
- `python .codex/scripts/anchor_check.py output/triage/issues/74/proposed-body.md`
  passed: 9 anchored refs, 0 unresolved, 0 past EOF.
- `python scripts/triage/triage.py standardize --issue 74 --proposed-body
  output/triage/issues/74/proposed-body.md --output-dir output/triage/issues/74
  --json` passed. Proposed body digest:
  `781df283dfd24f13c1a0048d1bf162ecd5d64a54096c2f8e8b9c069445b450e8`;
  standardization digest:
  `7c9a8f7a4e2e6866e64d46c5466014d270010697dd7212edec21600399c4531e`.
- Final snapshot-bound audit digest:
  `1eb80352c8f8a8a79313a031ea8b1d936c72a41ef015fc6c3c6973a33af0d7d6`.
  Audit mode selects #74; implementation mode returns an empty frontier and no
  worker packet because the live issue body is still nonconformant.
- `python -m compileall -q dbt_diagnostics scripts/triage` passed.
- `bash .codex/bin/action.sh full` passed in the controlled `.venv`:
  `613 passed, 2 skipped, 1 warning`.

**Current state**
- Branch:
  `test/74-test-dogfood-the-agentscodex-codex-skills-governance-lifecycle-this-issue-is-the-fixture`.
- `origin/donkey-kong-sandbox` is an ancestor of `HEAD`.
- No GitHub tracker mutation was performed.
- Worktree changes now include new `output/triage/issues/74/` artifacts and
  this progress-log entry. The pre-existing deletion of
  `output/triage/74-optimized-fixture.md` remains untouched.

**Next steps**
- Maintainer reviews `output/triage/issues/74/proposed-body.md` and applies it
  by hand if accepted.
- After the body is applied, refresh the snapshot/audit/frontier to confirm #74
  no longer appears in the governance frontier.
- Track governance work in a dedicated governance/process epic rather than
  product epics #4, #48, or #68.
- Keep AI section drafting as the assist layer, with deterministic checks for
  artifact shape, placeholder-only edits, source anchors, and standardize
  validation.
- Reconcile the missing policy labels still reported by audit: `cli`,
  `config`, `docs`, `lineage`, `live`, `output`, `release`, `security`, and
  `spike`.

**Be careful**
- The proposed body is a local review artifact. The live issue remains
  `needs_contract_revision` until the maintainer applies the exact body.
- The issue still contains `.agents/.codex` prose shorthand in retained
  context; the issue-specific readiness path treats it as a warning, while the
  metadata audit still surfaces a missing-path warning for the live body.
- Do not run local ad-hoc multi-version Python checks; CI owns multi-version
  coverage.

End of session -- 2026-06-26 issue 74 governance lifecycle rerun

---

## 2026-06-26 -- issue 74 applied body and production-readiness decision

**What changed**
- Applied the reviewed #74 body to GitHub with:
  `gh issue edit 74 --body-file output/triage/issues/74/proposed-body.md`.
- Reloaded live #74 as the new source of truth and reran contract, readiness,
  and frontier checks against the applied body.
- Wrote post-apply artifacts under `output/triage/issues/74/`:
  `post-apply-snapshot.json`, `post-apply-audit.json`,
  `post-apply-frontier-audit.json`, `post-apply-frontier-implement.json`, and
  `post-apply-worker-packet.json`.
- Updated local semantic evidence so it no longer says the live body is
  unapplied.

**Validation**
- Live #74 contract is conformant with body digest
  `781df283dfd24f13c1a0048d1bf162ecd5d64a54096c2f8e8b9c069445b450e8`.
- Post-apply readiness audit digest:
  `417146a1307a109d7a6185e4d813e7554d4d5ac87dd2d9c43bbcf14bb0cf84cd`.
  It marks #74 `conformant` and `ready`.
- Post-apply audit frontier is empty. Post-apply implementation frontier
  selects #74 and writes a valid worker packet.
- Coordinator and worker-packet validation passed with zero errors.

**Decision**
- #74 itself is production-ready as a dogfood fixture and handoff record: the
  contract is accepted, semantic evidence is recorded, and the implementation
  frontier can select it.
- The governance toolchain is not fully productionized as a repository process
  until the follow-up governance work is tracked and prioritized separately.
  Recommended tracker home remains a dedicated governance/process epic.
- Keep AI section drafting as an assist layer, but production hardening should
  make the deterministic harness first-class: draft anchor validation, artifact
  shape checks, placeholder-only edit checks, and standardize validation should
  be commands/tests rather than agent convention alone.

**Open production-readiness work**
- File or otherwise track the governance/process epic and the five local
  follow-up drafts under `output/triage/proposed-issues/`.
- Decide whether to add a dedicated governance/process issue kind; #74 was
  forced through `test_verification`, which works but is semantically awkward.
- Reconcile missing labels still reported by audit: `cli`, `config`, `docs`,
  `lineage`, `live`, `output`, `release`, `security`, and `spike`.
- Decide whether GitHub Project metadata stays disabled or gets a read-only
  desired-state planner.
- Promote draft anchor checking from `.codex/scripts/anchor_check.py` into the
  durable triage command/test surface if it is meant to be a supported gate.
- CI, not local Codex, should provide the Python 3.11/3.12 confirmation.

**Current state**
- Branch:
  `test/74-test-dogfood-the-agentscodex-codex-skills-governance-lifecycle-this-issue-is-the-fixture`.
- Worktree changes include this progress-log entry, updated/new #74 triage
  artifacts, and the pre-existing deletion of
  `output/triage/74-optimized-fixture.md`.

**Be careful**
- #74's live issue body still contains machine-draft markers; that is
  acceptable for the dogfood fixture, but future maintainer-facing issue bodies
  may need a cleanup pass in the maintainer's own voice.
- The `.agents/.codex` shorthand remains a warning in audit output.

End of session -- 2026-06-26 issue 74 applied body and production-readiness decision

---

## 2026-06-26 -- issue 75 read-only Project planner

**What changed**
- On branch `feat/75-github-projects-order-of-ops-planner`, implemented #75's
  read-only GitHub Project desired-state planner.
- Added `frontier.build_project_plan()`, which emits deterministic Project
  columns, issue placement, ordering, and dependency-inversion warnings from an
  existing snapshot plus readiness audit.
- Added the offline-only `project-plan` CLI command. It requires `--snapshot`
  and `--audit-file`, emits JSON, and does not call the GitHub runner.
- Kept the mutation surface unchanged: no Project operation is supported, no
  approval bundle is emitted, and issue bodies/state changes are omitted from
  plan items.
- Updated `CHANGELOG.md` under `[Unreleased]`.

**Validation**
- Wrote the failing planner test first:
  `scripts/triage/test_frontier.py::test_project_plan_is_read_only_and_flags_dependency_inversion`.
- `pytest scripts/triage/test_frontier.py::test_project_plan_is_read_only_and_flags_dependency_inversion -q`
  passed after implementation.
- `pytest scripts/triage/test_triage.py::test_project_plan_cli_emits_json_without_github_calls -q`
  passed.
- `pytest scripts/triage/test_frontier.py scripts/triage/test_triage.py -q`:
  79 passed.
- `pytest scripts/triage -q`: 141 passed.
- `bash .codex/bin/action.sh check` passed after rerunning unsandboxed because
  the sandbox could not write `.codex/scripts/__pycache__`.

**Current state**
- Branch `feat/75-github-projects-order-of-ops-planner` is pushed to origin and
  PR #77 is open against `donkey-kong-sandbox`.
- No GitHub issue or Project metadata was mutated by the planner.
- `gh` remains unauthenticated locally; live issue #75 was read through the
  read-only GitHub connector.

**Next steps**
- Review PR #77 and merge it when the Project-plan shape is accepted.

**Be careful**
- Keep `project-plan` snapshot/audit-file driven. Do not add a fallback that
  collects live GitHub metadata.
- Do not add any Project operation kind, `gh project` command, issue-body write,
  or state-change path.

End of session -- 2026-06-26 issue 75 read-only Project planner

---

## 2026-06-26 -- issue 78 project-plan validator and schema

**What changed**
- On branch `feat/78-validate_project_plan-and-a-project-plan-schema-doc`, first
  ran the issue-work gate for #78. The live body failed contract because it was
  missing `Compatibility and canonical JSON implications`.
- Ran the read-only issue-governance path locally, recorded a `keep`
  disposition, generated `output/triage/issues/78/`, drafted only missing
  sections in `proposed-body.md`, and validated the proposed body.
- Added `frontier.validate_project_plan()`, wired `project-plan` to self-check
  before emitting output, and kept `build_project_plan()` output shape
  unchanged.
- Added `docs/PROJECT_PLAN_SCHEMA_V1.md` and
  `docs/project-plan-schema-v1.json`.
- Updated `CHANGELOG.md` under `[Unreleased]`.

**Validation**
- `python .codex/scripts/anchor_check.py output/triage/issues/78/proposed-body.md`
  passed: 16 anchored refs, 0 unresolved, 0 past EOF.
- `python scripts/triage/triage.py standardize --issue 78 --proposed-body
  output/triage/issues/78/proposed-body.md --output-dir output/triage/issues/78
  --json` passed. Proposed body digest:
  `4e61441e5563161c330c28b707c129f7995282bac7aa8bd0e22e2d9de07e4fa3`;
  standardization digest:
  `88f471a3f9605c1551e914cd8b9f6371df8d5809fba15437df1cfe643243d10d`.
- The new validator tests failed first with missing `validate_project_plan`,
  then passed after implementation.
- `pytest scripts/triage/test_frontier.py scripts/triage/test_triage.py -q`:
  85 passed.
- `bash .codex/bin/action.sh check` passed after rerunning unsandboxed because
  the sandbox could not write `.codex/scripts/__pycache__`: 602 passed, 2
  skipped, 20 deselected, 1 warning; compatibility schema gate skipped as
  expected.

**Current state**
- `origin/donkey-kong-sandbox` and `HEAD` match at `f2b7110`.
- The branch is one commit ahead of `origin/feat/78-validate_project_plan-and-a-project-plan-schema-doc`
  because it was fast-forwarded to current `origin/donkey-kong-sandbox` before
  work began.
- Worktree changes are uncommitted and include code, tests, docs, changelog,
  this progress-log entry, and local #78 governance artifacts.
- No GitHub metadata was mutated and nothing was pushed.

**Next steps**
- Review the code/docs diff and decide whether to include the local
  `output/triage/issues/78/` artifacts in the PR.
- Commit this issue branch and open one PR into `donkey-kong-sandbox`.
- If desired, apply `output/triage/issues/78/proposed-body.md` to GitHub by hand
  so the live issue contract matches the implementation-ready local body.

**Be careful**
- The live #78 issue body is still nonconformant until the proposed body is
  applied manually; the implementation proceeded only after local
  `standardize` accepted that final body.
- Keep the project-plan artifact read-only: no `operations`, no issue bodies,
  no item `state`, no GitHub calls, and no apply path.

End of session -- 2026-06-26 issue 78 project-plan validator and schema

---

## 2026-06-26 -- issue 78 dataclass validation refactor

**What changed**
- Refactored the project-plan implementation away from ad hoc dict assembly and
  procedural validation.
- Added dataclass-backed domain objects for `ProjectPlan`, `ProjectPlanItem`,
  `ProjectPlanColumn`, `ProjectPlanOrderingConflict`, `ProjectPlanSafety`, and
  `ProjectPolicy`.
- Added dataclass-backed validators for the project plan, coordinator result,
  and worker packet, sharing one validation context while preserving the public
  `validate_*` function APIs and error strings.
- Kept the emitted project-plan JSON shape unchanged.

**Validation**
- `pytest scripts/triage/test_frontier.py scripts/triage/test_triage.py -q`:
  85 passed.
- `bash .codex/bin/action.sh check` passed after rerunning unsandboxed because
  the sandbox could not write `.codex/scripts/__pycache__`: 602 passed, 2
  skipped, 20 deselected, 1 warning; compatibility schema gate skipped as
  expected.
- In-memory regression comparison against `HEAD:scripts/triage/frontier.py`
  confirmed old and new `build_project_plan()` canonical JSON match for the
  crafted dependency-inversion fixture.
- `python .codex/scripts/anchor_check.py output/triage/issues/78/proposed-body.md`
  passed: 16 anchored refs, 0 unresolved, 0 past EOF.
- `python scripts/triage/triage.py standardize --issue 78 --proposed-body
  output/triage/issues/78/proposed-body.md --output-dir output/triage/issues/78
  --json` passed with the same proposed body digest
  `4e61441e5563161c330c28b707c129f7995282bac7aa8bd0e22e2d9de07e4fa3`.

**Current state**
- Worktree changes remain uncommitted and include code, tests, docs, changelog,
  progress-log entries, and local #78 governance artifacts.
- No GitHub metadata was mutated and nothing was pushed.

**Next steps**
- Review the larger `scripts/triage/frontier.py` diff with attention to the new
  dataclass boundaries and unchanged JSON/error contracts.
- Commit this issue branch and open one PR into `donkey-kong-sandbox`.

**Be careful**
- The dataclasses are internal builders and validators. The public artifact is
  still the same canonical JSON object, and `schema_version` remains `1`.
- The live #78 issue body is still nonconformant until the local proposed body
  is applied manually.

End of session -- 2026-06-26 issue 78 dataclass validation refactor

---

## 2026-06-26 -- issue 78 proposed body applied

**What changed**
- Applied `output/triage/issues/78/proposed-body.md` to live GitHub issue #78
  with `gh issue edit 78 --body-file output/triage/issues/78/proposed-body.md`.
- Verified the live issue body with the contract gate and wrote
  `output/triage/issues/78/post-apply-contract.json`.

**Validation**
- Pre-apply `standardize` passed on the exact proposed body.
- Post-apply `python scripts/triage/triage.py contract --issue 78 --json
  --output output/triage/issues/78/post-apply-contract.json` passed.
- Live body digest:
  `4e61441e5563161c330c28b707c129f7995282bac7aa8bd0e22e2d9de07e4fa3`.
- Governance state is now `conformant`; no contract findings remain.

**Current state**
- GitHub issue #78 has been updated.
- Worktree changes remain uncommitted and include implementation code, docs,
  changelog, progress-log entries, and local #78 governance artifacts.
- Nothing was committed or pushed to the remote branch in this step.

**Next steps**
- Commit this issue branch and open one PR into `donkey-kong-sandbox`.
- Decide whether to include the local `output/triage/issues/78/` artifacts in
  the PR.

**Be careful**
- The live issue now includes draft markers for the locally drafted sections.
  That matched the accepted proposed body, but the maintainer may still want a
  final wording pass before merge.

End of session -- 2026-06-26 issue 78 proposed body applied

---

## 2026-06-26 -- issue 78 branch pushed and draft PR opened

**What changed**
- Committed the non-output issue #78 implementation/docs changes with:
  `c9b4d38 feat: validate project plan artifacts`.
- Pushed branch `feat/78-validate_project_plan-and-a-project-plan-schema-doc`
  to `origin`.
- Opened draft PR #79 into `donkey-kong-sandbox`:
  https://github.com/dckallos/dbt-diagnostics/pull/79.

**Validation**
- Before commit/push, the staged set excluded `output/`.
- Previous full gate still applies to the committed code:
  `bash .codex/bin/action.sh check` passed with 602 passed, 2 skipped, 20
  deselected, 1 warning; compatibility schema gate skipped as expected.
- `git diff --cached --check` passed before the implementation commit.

**Current state**
- PR #79 is open as a draft.
- Local `output/triage/issues/78/` artifacts remain untracked and excluded from
  the branch.
- The branch includes the implementation commit plus this doc-only PR handoff
  entry.

**Next steps**
- Review PR #79, then mark it ready when the schema and dataclass boundaries are
  accepted.

**Be careful**
- Do not add `output/triage/issues/78/` to PR #79 unless that is explicitly
  requested later.

End of session -- 2026-06-26 issue 78 branch pushed and draft PR opened

---

## 2026-06-26 -- code standards documented

**What changed**
- Added `docs/CODE_STANDARDS.md` as the durable Python implementation standard
  for nontrivial validators, planners, JSON artifacts, command handlers, and
  compatibility-sensitive code.
- Added a compact pointer in `AGENTS.md` so future Codex sessions load the
  detailed standard before nontrivial Python edits.
- Kept the detailed guidance out of `AGENTS.md` so the always-loaded file stays
  small.

**Validation**
- `git diff --check` passed.
- `python .codex/scripts/check_ascii.py` passed.
- `bash .codex/bin/action.sh check` passed after rerunning unsandboxed because
  the sandbox could not write `.codex/scripts/__pycache__`: 602 passed, 2
  skipped, 20 deselected, 1 warning; compatibility schema gate skipped as
  expected.

**Current state**
- These docs changes are included on
  `feat/78-validate_project_plan-and-a-project-plan-schema-doc` for PR #79.
- Local `output/triage/issues/78/` artifacts remain untracked and excluded from
  the branch.

**Next steps**
- Review PR #79 and keep this standards guidance in mind for future nontrivial
  Python changes.

**Be careful**
- The standard is guidance for implementation quality. It should not be used to
  force abstractions into tiny one-off glue.

End of session -- 2026-06-26 code standards documented

---

## 2026-06-26 -- issue 80 governance kind PR opened

**What changed**
- Implemented the #80 decision by adding a `governance` issue kind to the
  issue contract and a `governance:` title prefix to triage policy.
- Gave governance issues a reduced decision section set: Summary, Evidence and
  confidence, Acceptance criteria or Decision criteria, Explicit non-goals, and
  Dependencies and traceability.
- Kept product-test sections out of the governance kind by default, including
  the normalized proposed-body skeleton path.
- Updated focused regression tests, `docs/ISSUE_CONTRACT_V1.md`, and
  `CHANGELOG.md`.
- Opened draft PR #88 into `donkey-kong-sandbox`:
  https://github.com/dckallos/dbt-diagnostics/pull/88.

**Validation**
- `pytest -q scripts/triage/test_contract.py` passed: 30 passed.
- `pytest -q scripts/triage/test_triage.py` passed: 60 passed.
- `python -m compileall -q scripts/triage` passed.
- `python .codex/scripts/anchor_check.py output/triage/issues/80/proposed-body.md`
  passed: anchored refs 3, unresolved 0, past EOF 0.
- `python scripts/triage/triage.py standardize --issue 80 --proposed-body
  output/triage/issues/80/proposed-body.md --output-dir
  output/triage/issues/80` passed.
- `bash .codex/bin/action.sh check` passed after rerunning unsandboxed because
  the sandbox could not write `.codex/scripts/__pycache__`: 611 passed, 2
  skipped, 20 deselected, 1 warning; compatibility schema gate skipped as
  expected.

**Current state**
- Branch `feat/80-governance-issue-kind` is pushed and PR #88 is open as a
  draft.
- Implementation commit: `bb2ee56 feat: add governance issue kind`.
- Local `output/triage/issues/78/` and `output/triage/issues/80/` artifacts
  remain untracked and excluded from the PR.

**Next steps**
- Review PR #88, with special attention to the reduced governance section set,
  the normalizer path, and whether a live `governance` label should be created
  separately later.

**Be careful**
- The PR adds only the `governance:` policy prefix. It does not add a desired
  label operation or mutate GitHub metadata.
- The #80 standardized proposed body is a local artifact only; it was not
  applied to the closed issue.

End of session -- 2026-06-26 issue 80 governance kind PR opened

---

## 2026-06-26 -- issue 81 proposed body drafted

**What changed**
- Generated a bounded local review packet for issue #81 under
  `output/triage/issues/81/`.
- Recorded the local disposition hypothesis as `keep` in
  `output/triage/issues/81/semantic-evidence.json`.
- Drafted the missing contract sections in
  `output/triage/issues/81/proposed-body.md` and made #85/#88 traceability
  explicit.

**Validation**
- `python .codex/scripts/anchor_check.py output/triage/issues/81/proposed-body.md`
  passed: anchored refs 9, unresolved 0, past EOF 0.
- `python scripts/triage/triage.py standardize --issue 81 --proposed-body
  output/triage/issues/81/proposed-body.md --output-dir
  output/triage/issues/81 --json` passed with only the recommended
  `Offline behavior` warning.

**Current state**
- No GitHub tracker mutation was made.
- The proposed #81 body is local and ready for maintainer review.
- Branch `feat/80-governance-issue-kind` still carries the #80 PR work; issue
  #81 now records #88 as the implementation prerequisite in the proposed body.

**Next steps**
- Review the proposed #81 body and apply it manually if accepted.
- After #88 merges, refresh issue #81 readiness before implementation work.

**Be careful**
- The drafted sections keep the machine-authored review marker.
- Do not implement #81 before the #80 governance-kind PR lands.

End of session -- 2026-06-26 issue 81 proposed body drafted

---

## 2026-06-26 -- issue 81 body applied and ready

**What changed**
- Applied `output/triage/issues/81/proposed-body.md` to live GitHub issue #81
  with `gh issue edit 81 --body-file output/triage/issues/81/proposed-body.md`.
- Verified PR #88 is merged into `donkey-kong-sandbox` at
  `51cf0f311ade5a7008896b13e5b726a9bf1d02d8`.
- Refreshed local issue #81 semantic evidence so the #88 dependency is recorded
  as merged instead of blocked.

**Validation**
- Live `python scripts/triage/triage.py contract --issue 81 --json --output
  output/triage/issues/81/post-apply-contract.json` passed.
- Focused readiness audit with
  `output/triage/issues/81/semantic-evidence.json` reports
  `implementation_state: ready` and `recommended_disposition: implement`.
- Live body digest:
  `3a1701ae933f0f5897b2b2fe3418d9053ab14530a12da3f975d0c60e75121cf9`.

**Current state**
- GitHub issue #81 has been updated and is ready for implementation work.
- Local output artifacts for #81 remain untracked.
- The current checkout is still on `feat/80-governance-issue-kind`; start #81
  work from fresh `donkey-kong-sandbox` state.

**Next steps**
- Use the `issue-work` skill for issue #81.

**Be careful**
- The issue body still has the expected recommended `Offline behavior` warning;
  the standardization gate accepts it.
- Keep the #81 implementation read-only. Do not add tracker mutation or expand
  the per-issue governance skill's scope.

End of session -- 2026-06-26 issue 81 body applied and ready

---

## 2026-06-26 -- issue 81 backlog synthesis implemented

**What changed**
- Implemented the read-only `backlog-synthesis` command and
  `frontier.build_backlog_synthesis_report()` signal artifact.
- Added deterministic candidate signals for semantic disposition hypotheses,
  explicit overlap, likely duplicates, split markers, and dependency-order
  inversions.
- Kept readiness `recommended_disposition` mechanical and added only additive
  semantic-disposition passthrough fields.
- Added the `backlog-synthesis` skill, signal schema docs, machine schema,
  changelog entry, and governance docs.
- Recorded the local-checkout-only Codex rule in `AGENTS.md`.

**Validation**
- `python -m compileall -q scripts/triage` passed.
- `pytest -q scripts/triage/test_frontier.py scripts/triage/test_triage.py
  scripts/triage/test_readiness.py` passed: 129 passed.
- `python .codex/scripts/check_ascii.py` passed.
- `python -m json.tool docs/backlog-synthesis-signals-schema-v1.json
  >/dev/null` passed.
- `git diff --check` passed.
- `PYTHONPYCACHEPREFIX=.venv/pycache bash .codex/bin/action.sh check` passed:
  621 passed, 2 skipped, 20 deselected, 1 warning; compatibility schema gate
  skipped as expected.

**Current state**
- Work is on local branch `feat/81-backlog-synthesis-local`, based on
  `origin/donkey-kong-sandbox`.
- `.gitignore` has an unrelated local change for `/output/triage`; do not stage
  it for the #81 PR.
- Local `output/triage/issues/` artifacts remain untracked and should stay out
  of the PR.

**Next steps**
- Stage only the #81 implementation/docs/skill files plus `AGENTS.md` and this
  progress entry.
- Commit, push, and open a draft PR into `donkey-kong-sandbox`.

**Be careful**
- The deterministic layer emits candidate signals only. Duplicate, obsolete,
  split, merge, and ordering verdicts remain AI/human/maintainer judgments.
- Use `PYTHONPYCACHEPREFIX=.venv/pycache` for the full local gate if sandboxed
  `.codex/scripts/__pycache__` writes fail.

End of session -- 2026-06-26 issue 81 backlog synthesis implemented
