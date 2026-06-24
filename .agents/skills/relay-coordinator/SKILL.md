---
name: relay-coordinator
description: Run or interpret the deterministic dbt-diagnostics audit or implementation frontier and produce one bounded handoff. Use for queue selection and worker-packet creation, never for implementation or GitHub mutation.
---

1. Read `docs/ISSUE_GOVERNANCE.md`, `docs/CODEX_RELAY.md`, and
   `docs/FRONTIER_SCHEMA_V1.md`.
2. Refresh or load an explicit tracker snapshot.
3. Run the full audit with semantic evidence.
4. Select one mode:
   - `bash .codex/bin/action.sh frontier audit --json`
   - `bash .codex/bin/action.sh frontier implement --json`
5. Validate the coordinator digest and accept `selected_issue: null` as a valid
   empty frontier.
6. For a selected implementation issue, write one worker packet. Do not load
   unrelated issue bodies into the worker context.
7. Report the deterministic selection reason, blockers, branch suggestion, and
   next read-only command.

The coordinator does not create a branch, worktree, Codex thread, issue, pull
request, label, milestone, or Project item.
