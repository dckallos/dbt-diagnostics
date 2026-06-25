---
name: relay-coordinator
description: Run or interpret the deterministic dbt-diagnostics audit or implementation frontier and produce one bounded handoff. Use for queue selection and worker-packet creation, never for implementation or GitHub mutation.
---

1. Read `docs/ISSUE_GOVERNANCE.md`, `docs/CODEX_RELAY.md`, and
   `docs/FRONTIER_SCHEMA_V1.md`.
2. Refresh or load an explicit tracker snapshot and readiness audit.
3. Select one mode:
   - `bash .codex/bin/action.sh frontier audit --json`
   - `bash .codex/bin/action.sh frontier implement --json`
4. For offline work, pass both `--snapshot` and `--audit-file`.
5. Validate the coordinator schema and digest. Accept `selected_issue: null` as
   a valid explicit empty frontier.
6. For a selected implementation issue, request one bounded worker packet with
   `--packet-output`. Do not load unrelated issue bodies into worker context.
7. Report the deterministic selection reason, blockers, branch suggestion, and
   next read-only command. Stop before implementation.

The coordinator does not create a branch, worktree, Codex thread, issue, pull
request, label, milestone, or Project item.
