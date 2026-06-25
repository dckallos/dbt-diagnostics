---
name: relay-coordinator
description: Interpret an explicitly supplied coordinator/frontier JSON artifact without implementing work or mutating GitHub. PR #73 does not expose frontier generation through the CLI.
---

1. Read `docs/CODEX_RELAY.md` and `docs/FRONTIER_SCHEMA_V1.md`.
2. Require a caller-supplied coordinator JSON artifact. Do not invent or select
   an issue when no artifact is supplied.
3. Validate its schema version and digest with the documented schema rules.
4. Accept `selected_issue: null` as a valid empty result.
5. For a selected issue, report only its deterministic selection reason,
   blockers, branch suggestion, and next read-only context command.
6. Stop before implementation or GitHub mutation.

The supported PR #73 CLI surface is `snapshot`, `audit`, `plan`, and `apply`.
There is no supported `frontier` command or worker-packet generator in this PR.
The coordinator does not create a branch, worktree, Codex thread, issue, pull
request, label, milestone, or Project item.
