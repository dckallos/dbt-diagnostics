# Read-only relay and Codex work loop

This document describes how the governance audit feeds one bounded, accepted
issue to a Codex worker. The relay is read-only. It does not edit GitHub, create
a worktree, create a branch, or start a Codex thread as a side effect.

The workflow was checked against the current official OpenAI Codex
documentation on 2026-06-24:

- [Codex app worktrees](https://developers.openai.com/codex/app/worktrees)
- [Codex app features](https://developers.openai.com/codex/app/features)
- [AGENTS.md](https://developers.openai.com/codex/guides/agents-md)
- [Agent Skills](https://developers.openai.com/codex/skills)
- [Non-interactive mode](https://developers.openai.com/codex/noninteractive)
- [Code review](https://developers.openai.com/codex/review)

## Scope boundary

Issue standardization happens before this relay. The implementation frontier
consumes:

- the live or offline tracker snapshot;
- contract-v1 audit results;
- source-aware semantic-review evidence;
- dependency and merge evidence;
- repository path checks;
- active pull request metadata where available.

Python owns the full graph and deterministic selection. The coordinator emits
one bounded packet. A worker handles one issue, one branch or worktree, and one
implementation loop.

## Two frontier modes

### Audit frontier

Selects the next issue needing contract review, standardization, or semantic
review. It does not require implementation readiness.

```bash
bash .codex/bin/action.sh frontier audit --json
```

### Implementation frontier

Selects only an accepted and ready issue. It rejects open dependencies, missing
merge evidence, cycles, decisions, external blockers, missing paths, active pull
request conflicts, and explicit ownership overlap.

```bash
bash .codex/bin/action.sh frontier implement --json
```

An empty frontier is a valid result. The coordinator returns `selected_issue:
null` rather than guessing.

## Coordinator result

The coordinator result is a compact fact record. It does not contain every open
issue body. Schema version 1 includes:

- repository, mode, generation time, and snapshot/audit digests;
- selected issue or explicit null;
- issue contract digest;
- governance and implementation states;
- deterministic selection reason and score;
- parent epics and direct dependencies;
- blockers, decisions, external evidence, and referenced paths;
- suggested branch and next read-only context command;
- coordinator digest.

The schema is in `docs/FRONTIER_SCHEMA_V1.md` and
`docs/frontier-schema-v1.json`.

## Worker packet

A worker packet contains only what one issue needs:

- live issue number, title, metadata, and body;
- accepted contract version and body digest;
- acceptance criteria and non-goals;
- direct dependency state and recorded merge evidence;
- issue-specific parent epic excerpts;
- referenced repository paths and existence state;
- source and test entry points recorded by semantic review;
- unresolved uncertainty, decisions, and external evidence;
- required verification commands;
- branch/worktree state supplied by the caller;
- the latest relevant progress-log excerpt, marked historical.

It intentionally excludes unrelated issue bodies and the full tracker.

Generate a packet with:

```bash
python scripts/triage/triage.py frontier --mode implement \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --json \
  --packet-output output/triage/frontier-worker-packet.json
```

## Local checkout versus worktree

A Local thread works in the checkout already open in the Codex app. Use it for
one focused task when no parallel branch needs an isolated file tree.

A worktree is a separate checkout with its own working files and branch while
sharing the repository's Git object database and history. Use one issue per
worktree when:

- another task is already changing the Local checkout;
- two independent issues are being implemented in parallel;
- review must inspect a branch without disturbing another working tree;
- an experiment needs an isolated reset/cleanup boundary.

Parallel work is unsafe when issues touch the same ownership surface, one issue
depends on the other's unmerged code, both alter the same migration, or tracker
readiness says they overlap. A separate worktree prevents file collisions; it
does not make overlapping changes semantically independent.

The Codex app lets a thread use Local, Worktree, or Cloud environment modes.
Selecting Worktree gives the thread an isolated checkout. The repository also
supports ordinary Git commands:

```bash
git fetch origin
git worktree add ../dbt-diagnostics-55 -b fix/55-query-history \
  origin/donkey-kong-sandbox
cd ../dbt-diagnostics-55
bash .codex/bin/action.sh setup
```

The relay never runs these commands automatically.

## One issue per worktree

Keep one implementation issue and one primary branch in a worktree. Do not
reuse a dirty worktree for a second issue merely because the first thread is
finished. The branch, tests, and files are durable project state; thread memory
is not.

Before editing:

```bash
bash .codex/bin/action.sh doctor
bash .codex/bin/action.sh context 55 --comments
```

Or load the coordinator packet directly when the worker has been selected by
the frontier.

## Codex threads

A Codex thread is the temporary task context for one line of work. Resume the
same primary thread when continuing the same issue and the same implementation
loop after an interruption. Start a fresh thread when:

- selecting a different issue;
- switching from implementation to an independent review;
- the issue contract or branch has materially changed;
- the previous thread accumulated unrelated context;
- a maintainer wants a clean adversarial pass.

Use a fresh review thread so the reviewer does not rely on the implementer's
assumptions. The review thread should load the accepted issue packet, inspect
the final diff and tests, and verify acceptance criteria and non-goals.

Codex may compact or resume a conversation, but the relay never treats thread
memory as repository state. Durable facts live in:

- the live tracker and snapshot;
- the accepted issue contract and digest;
- repository files and tests;
- audit and worker packet JSON;
- the branch commit and diff;
- verification output and the handoff.

## AGENTS.md and skills

Codex reads `AGENTS.md` before work. Instructions are resolved from repository
root toward the working directory, with nearer files taking precedence for
that subtree. Keep stable repository rules in `AGENTS.md`; do not duplicate the
whole file in a skill.

Repository skills live under `.agents/skills/<name>/SKILL.md`. They use
progressive disclosure: a short name and description route the task, then the
skill points to stable repository commands and docs.

This repository provides:

- `issue-governance`: audit or standardize one issue locally;
- `issue-work`: implement exactly one accepted issue contract;
- `relay-coordinator`: run or read the deterministic frontier and create a
  bounded handoff.

## Single-issue implementation loop

1. Load the accepted worker packet and verify its digests.
2. Confirm the issue remains one coherent PR and no blocker appeared.
3. Reproduce the defect or add a failing test where practical.
4. Implement the smallest coherent change.
5. Run focused tests.
6. Recheck every acceptance criterion and non-goal.
7. Run regression and repository gates.
8. Inspect the diff for scope expansion, duplicated paths, and hidden
   compatibility changes.
9. Repeat until all criteria pass or record an explicit blocker.
10. Produce a handoff with exact test evidence and uncertainty.

The worker does not close the issue, merge, push, or change tracker metadata.

## Across-issues relay loop

1. Refresh the live tracker snapshot after a merge or tracker change.
2. Rerun contract, readiness, and semantic evidence audit.
3. Recompute the implementation frontier in Python.
4. Select one issue or stop on an empty frontier.
5. Create or select one issue branch/worktree through the maintainer's normal
   process.
6. Start one fresh primary Codex thread with the bounded packet.
7. Implement and review the issue.
8. Merge through the maintainer's normal process.
9. Refresh and repeat.

No thread selects the next issue from memory. The frontier is recomputed from
current facts.

## Non-interactive use

Official Codex CLI non-interactive mode is `codex exec`. It is read-only by
default unless a different sandbox is explicitly selected. It can emit JSONL,
write a final response file, validate a response schema, and resume a prior
non-interactive session.

For repository automation, prefer stable wrapper commands and explicit output
files. A read-only coordinator example is:

```bash
codex exec --sandbox read-only --json \
  "Read output/triage/frontier-worker-packet.json and summarize blockers only" \
  > output/triage/codex-frontier-review.jsonl
```

Do not use non-interactive mode to bypass the repository's GitHub or sandbox
safety rules.

## Review loop

Use a fresh review thread with the accepted packet and final diff. The reviewer
checks:

- source claims and failure reproduction;
- acceptance criteria and non-goals;
- positive, negative, degradation, and regression cases;
- compatibility and canonical JSON implications;
- one-PR scope;
- no duplicate live or legacy path;
- exact commands and results;
- remaining uncertainty.

Codex review comments are review evidence, not project state. Resolve findings
in files and tests, rerun gates, and include the result in the handoff.

## Worked example: issue 55

Assume the implementation frontier selects #55.

```bash
python scripts/triage/triage.py frontier --mode implement \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --json \
  --output output/triage/frontier-implement.json \
  --packet-output output/triage/issues/55/worker-packet.json
```

Create an isolated worktree through the maintainer's normal Git process:

```bash
git fetch origin
git worktree add ../dbt-diagnostics-55 -b fix/55-query-history \
  origin/donkey-kong-sandbox
cd ../dbt-diagnostics-55
bash .codex/bin/action.sh setup
bash .codex/bin/action.sh context 55 --comments
```

The primary thread loads only #55, its parent excerpt, direct dependencies,
referenced paths, relevant source/tests, and verification commands. It adds a
failing query-history or cursor-lifecycle test, implements the smallest change,
and runs focused plus repository gates.

A fresh review thread then reads the packet, branch diff, and exact test output.
After the maintainer merges the PR, remove the worktree only after confirming no
uncommitted work remains:

```bash
git -C ../dbt-diagnostics-55 status --short
git worktree remove ../dbt-diagnostics-55
git branch -d fix/55-query-history
```

Do not force-remove a worktree containing uncommitted files. Remote branch
cleanup follows the maintainer's normal process.
