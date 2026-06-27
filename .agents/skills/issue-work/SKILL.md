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
   Escalate
   instead of implementing when `issue-governance` stops for a disposition other
   than `keep`, for a section that cannot be grounded, or when the maintainer
   does not approve the exact body. Never implement against a non-conformant
   spec, and never loosen the contract to pass this gate.

3. Treat the live, standardized issue as the current task specification.

4. Read only:
   - `AGENTS.md`;
   - the issue packet;
   - its parent epic summary;
   - direct dependency states;
   - repository paths named by the issue;
   - direct callers, imports, and tests discovered from those paths.

5. Do not read every open issue or preload the whole repository.

6. Before editing, print:
   - acceptance criteria;
   - non-goals;
   - blockers;
   - intended files;
   - intended tests.

7. Stop without editing if:
   - a dependency is open;
   - a required decision is unresolved;
   - the issue contradicts the current source;
   - the work cannot fit one coherent PR.

8. Add or update a failing test first where practical.

9. Implement only the issue scope.

10. Run:
    - focused tests;
    - `bash .codex/bin/action.sh check`;
    - any issue-specific verification.

11. Report:
    - changed files;
    - tests and exact results;
    - acceptance criteria satisfied;
    - remaining uncertainty;
    - suggested review focus.

12. Do not push, merge, or mutate GitHub metadata unless the current task
    explicitly authorizes it.

13. Do not use `Refs #<issue>` as the only issue link for an implementation PR.
    When the current task explicitly authorizes pushing and creating a PR, make
    the PR body close this implemented issue with a GitHub auto-close keyword,
    preferably `Closes #<issue>`. Keep close keywords limited to the implemented
    issue, not parent epics, dependencies, duplicates, or related issues. When
    practical after PR creation, check the PR's `closingIssuesReferences`; if it
    does not include the implemented issue, update the PR body before merge.
