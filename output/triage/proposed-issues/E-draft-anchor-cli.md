# feat: anchor-check a draft proposed body before applying (draft-level CLI)

## Summary

Expose the content-anchor verifier so a drafted `proposed-body.md` can be
checked before it is applied to the issue. Today the verifier only runs on the
live issue-body audit path, so the per-issue self-critique loop has no
deterministic way to catch a stale or fabricated `path:symbol` / snippet in its
own draft.

## Evidence and confidence

`verify_file_anchors` reads `issue["body"]` and runs inside the readiness audit
(`scripts/triage/readiness.py` `verify_file_anchors`; gated by
`check_file_anchors`). The `standardize` command only runs `contract_result`
(sections, coverage, title) and does not verify anchors
(`scripts/triage/triage.py`, the `standardize` handler). The `contract`
subcommand has no `--proposed-body` flag (`scripts/triage/triage.py` argument
parser). So there is no command that anchor-checks a draft file. Confidence
high; verified against source. Discovered while writing the per-issue loop in
`.agents/skills/issue-governance/SKILL.md`, which currently tells the agent to
verify anchors by hand as a result.

## Current wrong behavior or gap

The self-verify step in the issue-governance loop relies on manual anchor
checking; a fabricated symbol can slip through until after the body is applied
and re-audited.

## Acceptance criteria

- A positive case: a draft whose anchors all resolve passes with no
  unresolved-anchor finding.
- A negative case: a draft citing a nonexistent symbol or snippet is reported as
  an unresolved anchor, exit nonzero.
- A regression case: the live issue-body audit path is unchanged.
- Read-only: the command performs no GitHub mutation.

## Focused test plan

Add a `--proposed-body` source to the audit/contract path; unit-test that a
draft with a resolvable symbol passes and one with a fabricated symbol fails,
reusing the existing `verify_file_anchors` tests as the oracle.

## Scope and likely files

- `scripts/triage/triage.py` (CLI wiring)
- `scripts/triage/readiness.py` (allow a body override for anchor verification)
- `.agents/skills/issue-governance/SKILL.md` (replace the manual step with the
  command once it exists)
- `scripts/triage/test_readiness.py` / `scripts/triage/test_triage.py`

## Explicit non-goals

- No GitHub mutation; local draft validation only.

## Dependencies and traceability

- Strengthens the per-issue loop added to the issue-governance skill.
- Parent: governance toolchain epic.
