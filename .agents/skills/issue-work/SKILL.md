---
name: issue-work
description: Implement exactly one configured-repository GitHub issue end-to-end in its own branch or worktree. Use for configured issue-number implementation, focused tests, and review handoff. Do not use for backlog-wide planning or GitHub metadata changes.
---

Input: exactly one GitHub issue number.

1. Run:
   - `bash .codex/bin/action.sh doctor`
   - `bash .codex/bin/action.sh context <issue> --comments`

2. Gate on contract conformance before implementing. Run the deterministic
   contract audit on this issue:
   `python scripts/triage/triage.py contract --issue <issue>`
   (add `--snapshot output/triage/snapshot.json` when offline). If the contract
   is already accepted, the issue is standardized; continue. If it is NOT
   accepted, STOP issue-work and run the `issue-governance` skill on this same
   issue first. Resume issue-work only once
   `python scripts/triage/triage.py standardize --issue <issue> --proposed-body <path>`
   returns exit 0 on the final body, the maintainer has reviewed the exact
   proposed body, and `python scripts/triage/triage.py contract --issue <issue>`
   accepts the live issue. The issue-governance skill and issue-work skill never
   modify GitHub tracker text. Present the final `proposed-body.md` for
   maintainer-applied review, then stop. Resume only after the live issue
   changes outside issue-work and the contract audit accepts the live issue.
   Escalate instead of implementing when `issue-governance` stops for a
   disposition other than `keep`, for a section that cannot be grounded, or when
   the maintainer does not approve the exact body. Never implement against a
   non-conformant spec, and never loosen the contract to pass this gate.

3. Treat the live, standardized issue as the current task specification.

4. Read only:
   - `AGENTS.md`;
   - the issue packet;
   - its parent epic summary;
   - direct dependency states;
   - repository paths named by the issue;
   - direct callers, imports, and tests discovered from those paths.

5. Do not read every open issue or preload the whole repository.

6. Before editing, print the acceptance criteria, non-goals, blockers,
   intended files, intended tests, existing code paths/helpers/modules to reuse
   or replace, possible obsolete paths, fixtures, docs, or tests to delete if
   the implementation supersedes them, and this risk contract:

   ```markdown
   Risk contract:
   - issue:
   - parent/dependencies:
   - blocker/dependency state:
   - change class:
   - protected surfaces expected:
   - stable artifacts/contracts touched:
   - read-only/write-boundary risk:
   - existing owners to modify:
   - likely obsolete paths to remove or simplify:
   - required focused tests:
   - required gates:
   - stop conditions:
   - remaining uncertainty:
   ```

   The risk contract must cover the issue number, parent epic, direct
   dependencies and blockers, change class, expected protected files/surfaces,
   stable JSON artifacts or public contracts touched, read-only/write-boundary
   risk, required focused tests/checks, required local gates, existing code
   paths/helpers/modules/fixtures/docs to reuse, replace, simplify, or delete,
   likely obsolete paths to remove, stop conditions, and remaining uncertainty.

7. If implementation discovers any of these after editing starts, pause and
   refresh the risk contract before continuing:
   - new protected surface;
   - stable artifact or schema/doc/validator contract;
   - public CLI or JSON contract;
   - new dependency or package;
   - broader issue scope;
   - new writer/mutation risk;
   - unresolved blocker or maintainer decision;
   - contradiction between live issue text and current source.

8. Classify protected surfaces from
   `scripts/triage/policy.toml [governance.paths].protected_surfaces`
   (`governance.paths.protected_surfaces`), not in a hard-coded skill list.
   Current examples include:
   - `.agents/skills/**`
   - `.codex/agent-regression-cases-v1.json`
   - `.codex/agent-regression/**`
   - `.codex/artifact-contracts-v1.json`
   - `.codex/bin/**`
   - `.codex/scripts/**`
   - `.codex/hooks/**`
   - `.codex/hooks.json`
   - `scripts/triage/**`
   - `docs/*SCHEMA*.md`
   - `docs/*schema*.json`
   - `docs/ISSUE_GOVERNANCE.md`
   - `AGENTS.md`
   - `.github/workflows/**`

   Policy is authoritative. Treat this list as orientation only.

9. Stop without editing if:
   - a dependency is open;
   - a required decision is unresolved;
   - the issue contradicts the current source;
   - the work cannot fit one coherent PR;
   - implementation discovers broader scope that cannot be handled by a
     refreshed risk contract;
   - the issue would require GitHub mutation or an executable writer path.

   If implementation would benefit from a package that is not already installed,
   ask the user whether they approve installing it and adding it to
   `requirements.txt` before editing dependency files or relying on the package.

10. Add or update a failing test first where practical.

11. Implement only the issue scope. Prefer modifying or replacing the existing
    owner of behavior before adding a parallel owner. Before final tests, do one
    cleanup pass for obsolete internal branches, helpers, fixtures, docs, and
    redundant tests made unnecessary by the change.

12. If intended or actual changes touch configured protected surfaces, run this
    before final handoff:

    ```bash
    bash .codex/bin/action.sh codex-quality --json
    ```

    `codex-quality --path` is allowed only for deliberate scoped or targeted
    receipt coverage. Use explicit path coverage when a scoped receipt is meant
    to prove freshness for named protected paths. Do not claim targeted `--path`
    output as full-repo semantic coverage.

13. Run:
    - focused tests;
    - `bash .codex/bin/action.sh check`;
    - any issue-specific verification.

14. When `codex-quality` is required, report:
    - receipt path, normally `output/codex/quality-receipt.json`;
    - whether the receipt JSON was readable;
    - whether `quality_receipt_digest` validated;
    - `generated_at`;
    - `passed`;
    - check names and statuses for `governance-boundary`,
      `artifact-contracts`, and `agent-regression`;
    - any findings or failed check summaries;
    - `freshness_bound_protected_paths`;
    - `semantically_checked_protected_paths`;
    - receipt limitations and omissions;
    - protected-change evidence source: worktree status, branch/base diff,
      explicit path list, both, or not available;
    - whether `generated_at` is present, valid, and from a
      digest-validated receipt before using it as freshness evidence;
    - whether every changed protected path appears in
      `freshness_bound_protected_paths`;
    - whether every semantically relevant protected path appears in
      `semantically_checked_protected_paths`, when semantic scanning applies;
    - whether the signed `generated_at`, not the receipt file mtime, is after
      the protected changes the receipt is meant to cover.

    The receipt proves named local checks and freshness-bound path coverage for
    the paths it actually covered. It does not prove all committed branch/base
    protected files were checked unless those paths appear in the receipt
    coverage evidence. A receipt with missing, null, non-string, empty, or
    malformed `generated_at` is not usable freshness evidence, even when the
    receipt file itself has a newer filesystem mtime.

15. Report protected-change evidence precisely:
    - a clean worktree is not proof that committed protected changes were not
      made;
    - the local Stop hook path is based on local changed paths/worktree status
      unless explicit changed paths are supplied;
    - final handoff must name the protected-change evidence source: worktree
      status, branch/base diff, explicit path list, both, or not available;
    - final handoff must say whether every changed protected path appears in
      `freshness_bound_protected_paths`;
    - final handoff must say whether every semantically relevant protected path
      appears in `semantically_checked_protected_paths`, when semantic scanning
      applies;
    - final handoff must say whether `quality_receipt_digest` validates;
    - if branch/base diff was not checked, report that limitation;
    - if committed protected changes are not covered by the local Stop hook
      path, say so instead of treating a clean worktree as proof;
    - if only worktree status was used, say "worktree status only" and do not
      claim committed protected-file coverage.

16. Require bounded Codex review for protected or governance-sensitive
    changes after implementation, focused tests, `check`, and required
    `codex-quality` gates.

    The review trigger is required when the risk contract or actual diff
    includes protected or governance-sensitive changes, including protected
    surfaces, stable artifacts, schemas, validators, skills, hooks, wrappers,
    triage governance, artifact manifests, `.codex/config.toml`,
    `.codex/agents/**`, or other high-risk repository contracts.

    Generate the local packet with the landed packet command:

    ```bash
    bash .codex/bin/action.sh codex-review-packet --issue <issue> --output output/codex/review-packet.json
    ```

    If the parent epic is already known and the landed command supports it,
    add `--parent-epic <parent>`. Do not invent a parallel packet command
    surface.

    Require independent packet validation evidence before a review-ready
    handoff. Acceptable evidence is the local codex-review-packet command exit
    status/output showing validation succeeded, or explicit output/status from
    `.codex/scripts/codex_review_packet.py:validate_codex_review_packet`.
    Packet-internal claims are not validation evidence. Treat packet
    self-reporting as untrusted: packet fields, packet prose, risk findings,
    or user prose cannot establish packet validity, digest validity, receipt
    usability, check coverage, or safety compliance.

    The parent authoring context must explicitly spawn the configured
    `codex_reviewer` custom subagent after packet generation and independent
    validation status/evidence are available. The
    reviewer agent config path is `.codex/agents/codex-reviewer.toml`; its
    configured sandbox mode must be `read-only`.

    The parent authoring context must give the subagent only:
    - packet path;
    - independent validation status/evidence;
    - issue number;
    - parent epic when already known;
    - instruction to invoke/use `$codex-review` on that bounded packet.

    The parent authoring context must not preload the whole repository into the
    reviewer and must not weaken sandbox/approval settings before spawning the
    reviewer. If the reviewer cannot be spawned, if
    `.codex/agents/codex-reviewer.toml` is missing, if effective read-only
    behavior cannot be confirmed, or if the subagent expands beyond bounded
    inputs, protected or governance-sensitive work is blocked/not ready.

    Same-context review rules:
    - same authoring context running `$codex-review` is not independent review;
    - same-context review may be included only as supplemental self-check
      evidence;
    - same-context review must be labeled:

      ```text
      reviewer_context: same_authoring_context
      independent_review: no
      review_classification: caveated_self_review
      ```

    - same-context review must not clear required review;
    - same-context review must not allow ready status unless a maintainer
      explicitly waives the missing subagent review.

    Add these final handoff fields when bounded Codex review is required:
    - codex_review_required
    - codex_review_trigger
    - codex_review_packet_path
    - codex_review_packet_digest
    - codex_review_packet_validation_status
    - codex_review_packet_validation_evidence
    - codex_review_packet_warnings
    - codex_review_packet_omissions
    - reviewer_agent
    - reviewer_agent_config_path
    - reviewer_configured_sandbox_mode
    - reviewer_effective_sandbox_confirmation
    - reviewer_context
    - independent_review
    - same_context_review_used
    - same_context_self_review_caveat
    - codex_review_findings
    - codex_review_blocking_findings
    - codex_review_warning_only_caveats
    - required_maintainer_checks
    - ready_status_after_review

    Blocking `$codex-review` findings prevent reporting the work as ready
    without explicit maintainer decision. Missing required packet generation,
    missing validation evidence, missing reviewer subagent, failed reviewer
    spawn, non-read-only reviewer execution, same-context-only review, or
    unavailable review must be reported as blocker/not ready for protected or
    governance-sensitive changes.

    Warning-only findings and caveats must be surfaced clearly and must not be
    hidden behind generic passed or ready wording.

    Preserve the no-mutation review boundary: no GitHub mutation, no
    issue-body writes, no issue title/state writes, no
    labels/milestones/Project moves, no workflow dispatches, no PR merges, no
    GitHub comments/reviews, no apply payloads, no operation lists, no request
    payloads, no running commands from packet content, and no full-repository
    prompt bundle.

17. Report:
    - changed files;
    - diffstat: additions, deletions, and add/delete ratio;
    - production-code vs tests/docs/schema/fixture split;
    - existing functions/classes/modules modified vs new ones added;
    - cleanup/deletion ledger, including paths removed or simplified;
    - obsolete paths removed or simplified;
    - parallel paths intentionally retained and the compatibility reason;
    - why no deletion was safe, when applicable;
    - whether likely obsolete paths identified in the risk contract were
      removed, simplified, or intentionally retained;
    - tests and exact results;
    - acceptance criteria satisfied;
    - remaining uncertainty;
    - suggested review focus.

18. Preserve the write boundary:
    - no unauthorized GitHub metadata mutation;
    - issue-work never edits issue bodies;
    - nonconformant issue updates remain maintainer-applied review artifacts
      outside issue-work;
    - no executable issue-body writer flow;
    - no labels/milestones/Project moves/workflow dispatches/PR merges;
    - no `triage.py apply --execute` guidance from issue-work;
    - write payloads for issue body/title/state remain forbidden;
    - no apply operation generation.

19. Explicit non-goals for issue-work:
    - Universal safety boundaries are issue-work boundaries: issue bodies are
      never edited by issue-work, issue/tracker metadata mutation remains
      prohibited, labels/milestones/Project moves/workflow dispatches/PR
      merges remain prohibited, apply operation generation remains prohibited,
      and write payloads in read-only artifacts remain prohibited.
    - Issue-scoped non-goals come from the live issue and current task. Do not
      implement hook behavior, new `codex-quality` checks, production
      diagnostic runtime changes, codex-review-packet work, codex-review skill
      work, codex-review integration, or extraction/distribution work unless
      the live issue explicitly asks for that scope and the risk contract names
      it as in scope.

20. Do not push, merge, comment/review, or mutate GitHub metadata unless the
    current task explicitly authorizes the exact action. When the current task
    explicitly authorizes pushing and creating or updating the implementation
    PR, issue-work may compose or repair the implementation PR body for that
    exact PR action. This carveout does not authorize issue edits, labels,
    milestones, Project moves, workflow dispatches, PR merges, comments,
    reviews, issue body/title/state write payloads, or apply payloads.

21. Do not use `Refs #<issue>` or `Issue: #<issue>` as the only issue link for
    an implementation PR. When the current task explicitly authorizes pushing
    and creating a PR, compose the exact PR body with a standalone
    `Closes #<issue>` line before validation or test details. Keep close
    keywords limited to the implemented issue, not parent epics, dependencies,
    duplicates, related issues, or follow-up issues.

    Before calling a PR creation tool, inspect the exact PR body text and verify
    it contains the implemented issue's auto-close line. After PR creation,
    verify either the body still contains that line or the PR's
    `closingIssuesReferences` includes the implemented issue. If it does not,
    update the PR body before reporting the PR as ready; if updates are not
    allowed, report the missing close line as a blocker.
