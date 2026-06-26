---
name: backlog-synthesis
description: Use deterministic dbt-diagnostics backlog-synthesis candidate signals as evidence for maintainer-reviewed duplicate, split, merge, obsolete, and ordering verdicts without mutating GitHub.
---

Input: a tracker snapshot plus readiness audit, or permission to generate them
read-only for the current repository.

## Scope: cross-issue synthesis, no tracker mutation

This skill is the cross-issue synthesis pass that `issue-governance` deliberately
does not do. The deterministic artifact supplies candidate signals only. This
skill, a stronger model, or the maintainer may turn those signals into proposed
verdicts after reviewing the evidence, but the deterministic layer never decides
that an issue is duplicate, obsolete, split-worthy, or ready to close.

The skill never creates, edits, closes, labels, milestones, Project items, issue
bodies, or pull requests.

The output is a maintainer handoff: candidate verdicts with evidence,
uncertainty, and the exact issue numbers involved. The maintainer applies any
tracker change by hand or in a separately authorized writer session.

## 1. Load the contract for the signal artifact

Read:

1. `AGENTS.md`
2. `docs/ISSUE_GOVERNANCE.md`
3. `docs/BACKLOG_SYNTHESIS_SIGNALS_SCHEMA_V1.md`

Do not preload every open issue body. The deterministic report is the bounded
cross-issue input.

## 2. Generate or load the read-only inputs

Preferred live read-only flow:

```bash
python scripts/triage/triage.py snapshot --output output/triage/snapshot.json
python scripts/triage/triage.py audit \
  --snapshot output/triage/snapshot.json \
  --output output/triage/audit.json
python scripts/triage/triage.py backlog-synthesis \
  --snapshot output/triage/snapshot.json \
  --audit-file output/triage/audit.json \
  --output output/triage/backlog-synthesis.json \
  --json
```

If local semantic-review evidence exists, pass it to `audit` before generating
signals:

```bash
python scripts/triage/triage.py audit \
  --snapshot output/triage/snapshot.json \
  --semantic-evidence output/triage/semantic-evidence.json \
  --output output/triage/audit.json
```

Offline flow: use the caller-provided `--snapshot` and `--audit-file` paths with
the same `backlog-synthesis` command. Do not run a live snapshot if the task is
explicitly offline.

## 3. Interpret only candidate signals

For each signal:

- `semantic-disposition`: report the supplied semantic hypothesis and its
  evidence, and say whether it changes the local synthesis verdict from the
  mechanical readiness map.
- `explicit-overlap`: propose an ownership review for the named issues.
- `likely-duplicate`: propose a duplicate review, not an automatic close.
- `split-candidate`: propose a split review, naming the issue that may contain
  more than one coherent PR.
- `dependency-inversion`: propose ordering or dependency cleanup for the named
  issue and dependency.

Obsolete or outdated verdicts require explicit tracker facts or semantic
evidence. Do not infer them from title similarity, ordering, or split-marker
signals alone.

If `signals` is empty, say that no deterministic synthesis candidates were
found. Do not invent a duplicate or split from intuition.

## 4. Present a bounded maintainer handoff

Report:

- artifact path and `backlog_synthesis_digest`;
- candidate verdicts grouped by signal type;
- evidence from the signal artifact;
- uncertainty or places where a stronger model/maintainer must inspect issue
  text;
- explicit reminder that no tracker mutation was made.

Do not include full issue bodies. If a verdict needs deeper review, request or
generate a bounded per-issue packet for that issue before quoting issue text.

## Stop conditions

Stop and escalate when:

- the `backlog-synthesis` command fails validation;
- the artifact contains a forbidden mutation shape such as `operations`;
- the user asks to apply tracker changes without an explicit approved write
  flow;
- a candidate verdict requires comparing issue text that is not present in the
  signal artifact and no bounded per-issue packet is available.
