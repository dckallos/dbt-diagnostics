---
name: backlog-review
description: Review validated synthesis-review-packet artifacts and produce advisory maintainer handoff or backlog-review-verdict JSON without mutating GitHub.
---

Input: one caller-supplied `synthesis-review-packet.json`, and optionally prior
validator output from `python scripts/triage/triage.py backlog-review-validate
--packet ... --verdict ... --json`.

## Scope: bounded packet review, no tracker mutation

This skill is the LLM-facing review layer after deterministic packet creation
and before maintainer decision. It consumes only a validated `synthesis-review-packet`
and emits advisory maintainer output.

The skill must not mutate GitHub. It must not create, edit, close, reopen,
label, milestone, or move issues. It must not create Projects, workflow
dispatches, pull request merges, branches, worktrees, Codex threads, approval
batches, apply payloads, operation lists, GitHub request payloads, or anything
directly consumable by `triage.py apply`.

## 1. Load only bounded review inputs

Read:

1. `AGENTS.md`
2. `docs/SYNTHESIS_REVIEW_PACKET_SCHEMA_V1.md`
3. `docs/BACKLOG_REVIEW_VERDICT_SCHEMA_V1.md`
4. One caller-supplied `synthesis-review-packet.json`
5. Optionally, caller-supplied `backlog-review-validate` JSON output

Do not load by default:

- full tracker snapshot;
- all open issue bodies;
- GitHub comments;
- arbitrary GitHub state;
- repository-wide unrelated source files;
- issue bodies not already bounded into packet evidence;
- retrieval indexes or semantic search output.

Do not use full snapshot prompting. Do not collect GitHub comments in v1.
If comments matter, rely only on packet omissions and uncertainty.

## 2. Review packet safety first

Before writing any handoff or verdict, inspect the packet for:

- validation status, if validator output is supplied;
- `safety` fields and forbidden mutation shapes;
- `staleness.freshness_status`, `staleness.stale`, and
  `staleness.llm_review_allowed`;
- serialized byte budget, including hard byte-budget failure;
- source artifact digests and source lineage;
- `comments_included`, `comment_evidence_status`, and comments safety status;
- packet `evidence_items[].evidence_id` values;
- packet `near_misses[].near_miss_id` values;
- packet `omissions[].omission_id` values.

Stop before producing any verdict when:

- packet validation fails;
- packet source lineage is invalid;
- packet is hard-stale;
- packet is non-reviewable;
- `llm_review_allowed` is false;
- packet exceeds the hard byte budget;
- source digests are missing or inconsistent;
- forbidden mutation shape is present;
- decisive evidence is omitted and no safe bounded basis remains;
- the user asks the skill to mutate GitHub or emit executable operations.

## 3. Preserve freshness semantics

Treat packet freshness states distinctly:

- Fresh packet: continue normally when validation and safety checks pass.
- Warning-only freshness: continue only when the packet is otherwise valid and
  reviewable. Prominently surface freshness warnings in the maintainer handoff
  or in verdict `packet_reviewability`, `uncertainty`, or
  `required_maintainer_checks`. Remind the maintainer that GitHub remains the source of truth.
- Hard-stale packet: stop and produce no verdict.
- Non-reviewable packet: stop and produce no verdict.
- Invalid-lineage packet: stop and produce no verdict.

Do not collapse warning-only freshness into a 24-hour hard stale cliff.
Warning-only freshness warnings are review caveats, not automatic stop reasons.

## 4. Produce advisory output only

Produce exactly one of:

- an advisory Markdown maintainer handoff; or
- `backlog-review-verdict` JSON conforming to v1.

A Markdown handoff should include packet digest, freshness status, warnings,
candidate verdicts, evidence refs, uncertainty, required maintainer checks, and
a clear statement that no tracker mutation was made.

Verdict JSON is advisory only. It may include advisory
`future_apply_recommendations`, but those recommendations must not include
executable operations, operation IDs, request methods, request paths, request
bodies, approval batches, apply payloads, GitHub request payloads, issue
body/title/state writes, labels, milestones, Project updates, close/reopen
payloads, workflow dispatches, PR merge instructions, or anything directly
consumable by `triage.py apply`.

## 5. Cite only packet-bound refs

For verdict JSON:

- cite packet `evidence_items[].evidence_id` through `evidence_refs`;
- cite packet `near_misses[].near_miss_id` through `near_miss_refs`;
- cite packet `omissions[].omission_id` through `omission_refs`;
- preserve warning-only freshness in `packet_reviewability`, `uncertainty`, or
  `required_maintainer_checks`;
- use `insufficient-evidence` rather than fabricating support when packet
  evidence is not enough.

For #97 diagnostic ID alignment:

- do not invent `near_miss_id`, `omission_id`, `near_miss_refs`, or
  `omission_refs`;
- do not recompute diagnostic IDs from issue numbers, titles, reason
  categories, or prose;
- cite only `near_miss_id` and `omission_id` values present in the validated
  packet;
- if a useful diagnostic is omitted from the packet, report uncertainty or
  request packet regeneration rather than fabricating a ref;
- if verdict JSON is produced, `near_miss_refs` and `omission_refs` must pass
  #100 integrated validation before the handoff is considered valid.

## 6. Validate verdict JSON before claiming validity

If producing verdict JSON, write it locally and run:

```bash
python scripts/triage/triage.py backlog-review-validate \
  --packet <packet.json> \
  --verdict <verdict.json> \
  --json
```

If the validator returns warnings without errors, preserve those warnings in
the final handoff and required maintainer checks.

If the validator returns errors, do not claim the verdict is valid. Report the
errors and stop.
