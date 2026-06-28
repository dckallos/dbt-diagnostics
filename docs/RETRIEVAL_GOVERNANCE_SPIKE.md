# Retrieval governance spike

## Summary and recommendation

I evaluated retrieval/indexing only as supplemental evidence for the bounded
LLM governance layer. The local harness builds bounded synthetic
backlog-synthesis and synthesis-review-packet artifacts through the existing
frontier builders, indexes only bounded report and packet fields, and scores
deterministic lexical queries with no network, GitHub, comments, LLM, vector
database, subprocess retrieval tool, or apply path.

The result is not strong enough to implement retrieval yet. The baseline finds
some known handles, but it also misses multi-candidate handles, prefers
unrelated issue-number evidence in distractor cases, and retrieves omissions or
freshness metadata as if they were positive evidence. Those are evaluation and
deterministic-layer gaps, not a reason to add production retrieval.

## Live/base state verified

Read-only live preflight on 2026-06-28 verified:

| Item | State |
| --- | --- |
| #94 | Closed; PR #104 merged into `donkey-kong-sandbox`; issue was manually closed because the PR used a reference rather than an auto-close keyword. |
| #95 | Closed by merged PR #123 into `donkey-kong-sandbox`. |
| #96 | Closed by merged PR #125 into `donkey-kong-sandbox`. |
| #97 | Closed by merged PR #126 into `donkey-kong-sandbox`. |
| #98 | Closed by merged PR #127 into `donkey-kong-sandbox`. |
| #99 | Closed; PR #128 merged into `donkey-kong-sandbox`. |
| #100 | Closed by merged PR #129 into `donkey-kong-sandbox`. |
| #101 | Closed by merged PR #130 into `donkey-kong-sandbox`. |
| #102 | Closed by merged PR #131 into `donkey-kong-sandbox`. |
| #103 | Open and the remaining open #93 child from the #94 through #103 set. |
| #118/#120/#121 | Open downstream work; not implemented here. |
| #199 | Did not resolve as an issue or pull request; not reinterpreted as #119, #120, or #121. |

## Scope and hard non-goals

This is a research/evaluation spike. It adds a local experimental harness,
focused tests, and this report. It does not ship production retrieval behavior.

Hard non-goals:

- no production retrieval command;
- no public retrieval API;
- no stable schema change;
- no stable validator change;
- no `triage.py` command surface change;
- no backlog-review, backlog-synthesis, or issue-governance skill semantics
  change;
- no operator workflow docs that describe retrieval as available;
- no GitHub reads from the committed harness;
- no GitHub writes;
- no GitHub comments collection;
- no browser, web, external docs, network API, vector database, external
  service, subprocess retrieval tool, or LLM invocation;
- no apply operations, mutation-shaped payloads, GitHub request payloads, or
  `triage.py apply` integration;
- no #118 reusable extraction, #120 module extraction, #121 distribution
  decision, package/plugin publication, submodule/subtree work, or physical
  repository split.

## Current #93 artifact model

The bounded governance layer remains:

```text
snapshot.json
  -> audit.json
  -> backlog-synthesis.json
  -> synthesis-review-packet.json
  -> backlog-review-verdict.json
  -> backlog-review-validate
  -> maintainer decision
```

GitHub remains the source of truth. Deterministic local artifacts are bounded
evidence. LLM verdicts are advisory. Maintainers decide. Future writes remain
manual or behind the existing explicit write-gated apply path.

The spike harness respects the current artifact contracts:

- `backlog-synthesis` is advisory candidate evidence, not a verdict.
- `synthesis-review-packet` is bounded advisory evidence, not an operation
  plan.
- `backlog-review-verdict` is advisory and must cite exact packet refs.
- hard-stale, non-reviewable, or invalid-lineage artifacts stay invalid even
  when retrieval finds matching text.

## Residual closed-issue gap audit

### #97 duplicate-centric near misses

`build_backlog_synthesis_report` currently collects near misses from duplicate
diagnostics. Split and dependency paths emit positive signals when their
deterministic thresholds are met, but they do not emit weak split/dependency
near-miss categories.

The harness does not add production split/dependency near misses. Its finding
is that retrieval cannot safely rescue weak split or dependency evidence if the
bounded artifacts have no stable handle for that evidence. If maintainers want
weak split/dependency evidence, the safer follow-up is deterministic near-miss
work, not retrieval-only behavior.

### #99 fixtures are in-test, not reusable evaluation assets

The #99 labels and builders live in `scripts/triage/test_frontier.py`. They are
useful, but they are not a stable reusable evaluation asset. This spike keeps a
separate experimental matrix under `scripts/triage/experiments/` rather than
moving production or test ownership.

Future work should extract a stable recall-fixture module or JSON fixture set
only after the fixture shape is reviewed as a first-class evaluation contract.

### #99 first-candidate/evidence-001 overfitting risk

Existing positive tests commonly assert `candidate_sets[0]` and
`evidence-001`. The spike adds multi-candidate and distractor cases so the
retriever must rank expected handles in top K rather than merely find the first
valid packet item.

The multi-candidate case shows top-K pressure: the retriever returns
`evidence-001`, `evidence-003`, and `evidence-004`, while missing the expected
candidate-set handles. That is a false negative under this spike's definition.

### Sequential evidence ID instability

Packet evidence IDs are deterministic for identical inputs, but they are
local-order dependent. The harness demonstrates that `evidence-001` maps to
issues `[1, 2]` in a duplicate-only packet and to `[30, 31]` after earlier
semantic-disposition evidence is added.

Future retrieved evidence needs a separate namespace such as:

```text
retrieval-evidence-{source_slug}-{issue_numbers}-{content_digest_prefix}
```

That rule is draft-only. This spike does not change the stable packet schema.

### Lightweight evidence provenance

Packet evidence validation is intentionally lightweight for v1. Future
retrieved evidence needs richer provenance than current bounded packet evidence
items provide. Draft-only required provenance is listed later in this report.

### #100 ref-existence versus issue-alignment gap

Current packet-aware validation checks that `evidence_refs`, `near_miss_refs`,
and `omission_refs` exist in the packet. It does not prove cited evidence
issue numbers overlap the verdict issue numbers.

The distractor and wrong-issue-number cases retrieve valid packet handles from
unrelated issue numbers. Future #100 work should validate issue-number overlap
before retrieved evidence refs can be cited.

### Loose diagnostic array shape

Packet near-miss and omission arrays permit loose object-or-string entries for
v1 compatibility. Future retrieval evidence should not be modeled as loose
strings. It should be structured, provenance-rich, and validator-backed.

### #101/#102 retrieval excluded by design

The backlog-review skill and operator docs intentionally exclude retrieval from
the default workflow. This spike does not change that. Any future docs or skill
changes must be target-state follow-up work after a separate implementation
issue.

## Retrieval baseline and corpus

The baseline is deterministic lexical retrieval:

- scorer: `token-overlap-jaccard-v1`;
- tokenization: lowercase ASCII alphanumeric tokens with stable stopword
  filtering;
- score: Jaccard overlap between query tokens and bounded document tokens;
- top K: `3`;
- tie-break: score descending, then handle, then artifact kind;
- dependencies: standard library only.

The corpus is built only from bounded local artifacts generated by existing
frontier functions:

- backlog-synthesis signals, near misses, and omissions;
- synthesis-review-packet candidate sets, evidence items, near misses,
  omissions, and staleness metadata;
- staleness metadata is guardrail-only, never positive verdict evidence.

The corpus does not index raw issue bodies outside bounded packet excerpts,
GitHub comments, full snapshot issues/pulls arrays, live GitHub state, all open
issue bodies, arbitrary repository source files, external docs, browser/web
results, LLM summaries, GitHub request payloads, workflow dispatches, PR merge
instructions, approval batches, or apply operations.

## Fixture matrix and queries

The harness covers every #99 recall label:

- likely-duplicate-true-positive
- likely-duplicate-false-positive-control
- close-duplicate-near-miss
- backlog-omission-id-preservation
- split-candidate
- no-split-control
- dependency-order-inversion
- no-dependency-order-inversion-control
- semantic-disposition-evidence
- insufficient-evidence-verdict
- fresh-packet-under-warning
- warning-only-packet
- hard-stale-packet
- stricter-max-age-packet
- invalid-lineage-packet
- unknown-diagnostic-ref

It also adds #103-specific cases:

- multi-candidate-duplicate-split-dependency-semantic
- distractor-evidence-unrelated-issue-numbers
- valid-handle-wrong-issue-numbers
- omission-retrieved-as-positive-evidence
- freshness-retrieved-as-positive-evidence
- close-near-miss-not-upgraded
- hard-stale-retrieval-hit-nonreviewable
- invalid-lineage-retrieval-hit-invalid
- evidence-id-instability-demonstration

## Results table

Harness summary:

| Metric | Value |
| --- | ---: |
| Fixture count | 25 |
| False-negative fixtures | 2 |
| Noisy-result fixtures | 10 |
| Safe supplemental-evidence fixtures | 10 |
| Reviewable fixtures | 13 |
| Warning-only fixtures | 2 |
| Hard-stale non-reviewable fixtures | 3 |
| Invalid-lineage fixtures | 2 |
| No-action controls | 5 |

Selected fixture outcomes:

| Fixture | Guardrail status | False negative | Noise | Safe as supplemental packet evidence |
| --- | --- | --- | --- | --- |
| likely-duplicate-true-positive | reviewable | no | no | yes |
| close-duplicate-near-miss | reviewable | no | yes: `staleness:fresh` | no |
| split-candidate | reviewable | no | no | yes |
| dependency-order-inversion | reviewable | no | yes: `issue-comments-not-collected` | no |
| semantic-disposition-evidence | reviewable | no | no | yes |
| multi-candidate-duplicate-split-dependency-semantic | reviewable | yes | yes | no |
| distractor-evidence-unrelated-issue-numbers | reviewable | yes | yes | no |
| omission-retrieved-as-positive-evidence | no_action_control | no | yes | no |
| freshness-retrieved-as-positive-evidence | warning_only | no | yes | no |
| hard-stale-packet | hard_stale_non_reviewable | no | no | no |
| invalid-lineage-packet | invalid_lineage | no | no | no |

The harness JSON records the full per-fixture expected handles, retrieved
top-K handles, true positives, missed handles, noisy handles, guardrail status,
supplemental-evidence safety, and deterministic-layer gap flag.

## False negatives

The harness found two false-negative cases:

1. `multi-candidate-duplicate-split-dependency-semantic`
   - Expected handles: `candidate-set-001`, `candidate-set-002`,
     `candidate-set-003`, and `candidate-set-004`.
   - Retrieved handles: `evidence-001`, `evidence-003`, and `evidence-004`.
   - Interpretation: top-K lexical retrieval can surface bounded evidence
     items while missing the expected candidate-set handles. This exposes
     first-candidate overfitting and result-limit sensitivity.

2. `distractor-evidence-unrelated-issue-numbers`
   - Expected handles: `candidate-set-001` and `evidence-001`.
   - Retrieved handles: `evidence-002`, `candidate-set-002`, and
     `candidate-set-001`.
   - Interpretation: lexical retrieval can prefer an unrelated duplicate pair
     when the query tokens match the distractor more strongly than the intended
     issue pair.

## False positives/noise

The harness found ten noisy-result cases. The important noise categories are:

- guardrail metadata retrieved with evidence, such as `staleness:fresh` or
  `staleness:warning`;
- packet omissions retrieved as if they supported a positive verdict, including
  `issue-comments-not-collected` and `full-issue-bodies-not-embedded`;
- unrelated issue-number handles retrieved as valid but semantically wrong
  evidence;
- candidate-set/evidence-ID mismatch caused by local-order-dependent handles.

Noise does not prove retrieval is unsafe in every future design, but it proves
that retrieved handles need provenance, issue-number alignment checks,
omission/noise classification, and integrated validation before citation.

## Guardrail outcomes

Warning-only packets remain reviewable only when freshness warnings stay
visible to the maintainer. Retrieval does not change that.

Hard-stale packets still have `stale: true`, `llm_review_allowed: false`, and
packet validation errors. Retrieval hits in `hard-stale-packet`,
`stricter-max-age-packet`, and
`hard-stale-retrieval-hit-nonreviewable` are not safe supplemental evidence.

Invalid-lineage artifacts remain invalid regardless of retrieval hits.
`invalid-lineage-packet` and `invalid-lineage-retrieval-hit-invalid` both find
the expected duplicate evidence text, but source-lineage errors still block
review.

No-action controls remain no-action controls. Retrieval must not turn controls,
omissions, or staleness metadata into positive verdict evidence.

## Recommendation

Recommendation: add more fixture/evaluation work first.

I do not recommend implementing retrieval yet. The evaluation shows useful
bounded-evidence hits, but the false negatives, unrelated issue-number noise,
omission-as-evidence noise, freshness-as-evidence noise, and sequential
evidence-ID instability all need stronger fixtures and validator design before
retrieval can be a safe packet supplement.

The other allowed recommendation values are intentionally not selected:

- `do not implement retrieval` is premature because bounded evidence hits do
  occur in the synthetic matrix.
- `implement retrieval only as packet supplemental evidence` is premature
  because the current fixtures and validator gaps are not sufficient.

## Required guardrails if retrieval proceeds

- Retrieval cannot replace backlog-synthesis.
- Retrieval cannot replace deterministic candidate generation.
- Retrieval cannot become the authoritative selector.
- Retrieval cannot fetch GitHub live by default.
- Retrieval cannot collect GitHub comments unless separately authorized.
- Retrieval cannot invoke an LLM.
- Retrieval cannot mutate GitHub.
- Retrieval cannot generate apply plans.
- Retrieval cannot embed full issue bodies into bounded packets.
- Retrieval cannot weaken packet/verdict validation.
- Retrieval cannot make hard-stale, non-reviewable, or invalid-lineage packets
  reviewable.
- Retrieval evidence is never sufficient for a verdict without packet grounding
  and integrated validation.
- Any future retrieval evidence must be packet supplemental evidence with
  stable IDs and provenance.

## Draft-only future schema/validator considerations

These are target-state considerations, not implemented behavior in this spike.

Future retrieval evidence should use stable IDs outside the current sequential
packet evidence namespace:

```text
retrieval-evidence-{source_slug}-{issue_numbers}-{content_digest_prefix}
```

Future retrieval snippets should carry structured provenance:

- retrieval query ID;
- source artifact digest or digests;
- source artifact field/path;
- issue numbers;
- rank;
- score;
- scorer name/version;
- excerpt byte length;
- omission/noise status when not used;
- explicit `comments_included: false` and comments-not-collected handling.

Future validators should consider:

- issue-number overlap validation for retrieved refs;
- scorer name/version allowlists;
- source digest checks for every retrieved snippet;
- packet byte-budget accounting for retrieval evidence;
- omission/noise diagnostics distinct from positive evidence;
- no comments unless separately authorized;
- no loose-string retrieval items.

## Follow-up issue candidates

Suggestions only; none are implemented here:

- Extract the #99 recall matrix into a stable fixture module or JSON fixture
  set for evaluation reuse.
- Add deterministic split/dependency near-miss diagnostics if weak evidence is
  useful enough to preserve.
- Add issue-number overlap validation for retrieved evidence refs before any
  future retrieval refs can be cited.
- Design a draft retrieval-evidence schema with stable IDs, provenance, budget
  accounting, and omission/noise status.
- Run a second spike with a stronger deterministic lexical scorer after the
  reusable fixture matrix exists.

## Validation commands run

- `bash .codex/bin/action.sh doctor` passed with 0 failures and 2 expected
  warnings: protected base branch before the issue branch was created, and the
  absent compatibility schema cache.
- `bash .codex/bin/action.sh context 103 --comments` passed.
- `python scripts/triage/triage.py contract --issue 103` passed with only the
  existing missing-type-label warning.
- Read-only `gh issue view` / `gh pr list` checks verified #94 through #102
  closed with merged-PR evidence into `donkey-kong-sandbox`, #103 open,
  #118/#120/#121 open downstream, and #199 unresolved.
- `python scripts/triage/experiments/retrieval_governance_spike.py --json`
  passed.
- `python -m pytest -q scripts/triage/test_retrieval_governance_spike.py`
  passed: 7 passed. It initially failed before this report existed, as the
  test-first guard for the report.
- `python -m pytest -q scripts/triage/test_frontier.py scripts/triage/test_triage.py`
  passed: 176 passed.
- `python -m py_compile scripts/triage/experiments/retrieval_governance_spike.py scripts/triage/test_retrieval_governance_spike.py`
  passed.
- `python -m json.tool docs/synthesis-review-packet-schema-v1.json >/dev/null`
  passed.
- `python -m json.tool docs/backlog-synthesis-signals-schema-v1.json >/dev/null`
  passed.
- `python -m json.tool docs/backlog-review-verdict-schema-v1.json >/dev/null`
  passed.
- `bash .codex/bin/action.sh check` passed: Codex tests 106 passed; offline
  tests 818 passed, 2 skipped, 20 deselected, 1 warning; compatibility schema
  gate skipped as expected.
- `bash .codex/bin/action.sh codex-quality --json` passed.
