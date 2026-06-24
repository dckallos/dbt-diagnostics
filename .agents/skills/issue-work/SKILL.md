---
name: issue-work
description: Implement exactly one dbt-diagnostics GitHub issue end-to-end in its own branch or worktree. Use for issue-number implementation, focused tests, and review handoff. Do not use for backlog-wide planning or GitHub metadata changes.
---

Input: exactly one GitHub issue number.

1. Run:
   - `bash .codex/bin/action.sh doctor`
   - `bash .codex/bin/action.sh context <issue> --comments`

2. Treat the live issue as the current task specification.

3. Read only:
   - `AGENTS.md`;
   - the issue packet;
   - its parent epic summary;
   - direct dependency states;
   - repository paths named by the issue;
   - direct callers, imports, and tests discovered from those paths.

4. Do not read every open issue or preload the whole repository.

5. Before editing, print:
   - acceptance criteria;
   - non-goals;
   - blockers;
   - intended files;
   - intended tests.

6. Stop without editing if:
   - a dependency is open;
   - a required decision is unresolved;
   - the issue contradicts the current source;
   - the work cannot fit one coherent PR.

7. Add or update a failing test first where practical.

8. Implement only the issue scope.

9. Run:
   - focused tests;
   - `bash .codex/bin/action.sh check`;
   - any issue-specific verification.

10. Report:
    - changed files;
    - tests and exact results;
    - acceptance criteria satisfied;
    - remaining uncertainty;
    - suggested review focus.

11. Do not push, merge, or mutate GitHub metadata unless the current task
    explicitly authorizes it.
