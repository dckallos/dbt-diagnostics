# Pass 5 -- convert the OUTPUT_FOUR-gated review into GitHub issues

This is the step that turns analysis into shippable work. Be disciplined: do
not duplicate existing issues, and do not file work the red-team did not stand
behind. OUTPUT_FOUR is the gate, not OUTPUT_THREE.

## Sources (read first, with bash, not the GitHub MCP)

- `docs/OUTPUT_ONE.md`, `OUTPUT_TWO.md`, `OUTPUT_THREE.md` (the 27-change plan),
  and `docs/OUTPUT_FOUR.md` (the adversarial red-team). OUTPUT_FOUR decides what
  ships:
  - A change OUTPUT_FOUR judged sound (accept / accept-as-narrow-fix) becomes an
    implementation issue.
  - A change it judged `rewrite` becomes an implementation issue scoped to the
    REQUIRED CORRECTION it names -- not OUTPUT_THREE's original patch.
  - A change it `reject`ed or called a facade/theater does NOT become an
    implementation issue; at most a verification task.
- The new issue templates under `.github/ISSUE_TEMPLATE/` (bug, refactor, spike,
  test, feature, chore, epic, docs). File every issue through the matching
  template; fill the evidence, code-example, files-touched, test-tier, and
  traceability sections.

## The gate, in one rule

Only file an implementation issue for a defect that is PROVEN against the actual
source on `review/package-health-status` (or a first-party doc/schema). A claim
that reads convincingly in OUTPUT_THREE is not proof: the four passes are from
one model family, share blind spots, and none executed the package. Confirm
before filing.

## Wave 0 -- verification already done (2026-06-18)

Confirmed against source on this branch (do not re-litigate; cite these):

- `enrichers/query_history.py` queries `TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(...))`
  with `WHERE EXECUTION_STATUS = 'FAIL'`. That table function's failure statuses
  are `FAILED_WITH_ERROR` / `FAILED_WITH_INCIDENT`; `'FAIL'` matches nothing, so
  genuine failures return zero rows. CONFIRMED real (N2).
- `enrichers/grants.py`: `check_role_grants`, `check_write_access`, and
  `get_current_role` each open a cursor and none call `.close()` (leak);
  `f"SHOW GRANTS TO ROLE {role_name}"` is interpolated unvalidated;
  `except Exception: pass` makes a failed probe indistinguishable from a negative
  fact; one `has_usage` conflates database- and schema-level USAGE;
  `target_upper in name.upper()` is a substring match. CONFIRMED (N1).
- `tracers/dag_walker.py` has no `from __future__ import annotations` and no
  `LineageGraph`/`LineageEdge`; OUTPUT_THREE change 13 would `NameError`.
  CONFIRMED (N3 must add the import and enumerate call sites).
- `grouping.py` groups on `f"{report.error_class}:{schema_prefix}"` and labels
  the group "models not yet materialized"; unrelated same-class errors in a
  schema are mislabeled. CONFIRMED (N4).

## Epistemic charter (the deepest finding -- encode it in #4)

The package repeatedly confuses: not-visible with nonexistent; no-direct-grant-row
with no-effective-access; manifest-declaration with physical-truth; a same-named
ancestor column with proven lineage; a failed probe with a negative fact. A graph
class or adapter protocol does not fix this. Make evidence IDENTITY, STATUS,
PROVENANCE, and CONFIDENCE first-class, and never emit a high-confidence cause the
evidence does not prove.

## SPECULATIVE findings are not implementation issues

Everything OUTPUT_FOUR tagged `[SPECULATIVE]` (effective-access vs direct grants,
`query_id`/`rows_affected` guarantees, `compiled_code` on failed runs, classifier
regex coverage, SQLGlot version matrix, schema-title stability, the adapter import
cycle) is a VERIFICATION task. Route it to the real-fixture issues (#12, #44, #52)
or a spike, never to a fix.

## The small shipping slice (ship this first, in order)

1. Repair query-history failure statuses + cursor lifecycle (N2).
2. Make live probes typed and identity-aware; forbid high-confidence
   absence/denial from inconclusive evidence (N1).
3. Group by normalized root cause; render each report once (N4).
4. Add real regression fixtures for the above (N9 / #12 / #44 / #52).
5. Only then replace lineage adjacency with real edges (N3).

Do NOT block this slice on a full warehouse abstraction, an evidence ontology, a
JSON rewrite, or a CI redesign. Quoted-identifier handling: fail SAFE with a clear
message now; defer a full quoted-identifier parser.

## Reconcile the tracker before creating anything

Epic bodies have drifted from reality and must be corrected as part of this pass:

- #4 still says the `lint`/`linters/` package is present and the scope-guard
  contradiction stands -- but #25 (linter removal) is CLOSED. Rewrite.
- #48 lists #37/#38/#39/#40/#42 as unchecked -- all are CLOSED (PR #53). Rewrite.

## The issue backbone (N1-N12)

Map OUTPUT_THREE's 27 changes onto these; none duplicates an open issue.

- N1 fix: evidence-safe existence/grant verdicts (changes 1,2,3,5) -- epic #4
- N2 fix: query-history matching + cursor lifecycle (change 4 + the FAIL bug) -- #4
- N3 refactor: edge-preserving lineage + real-path disconnects (6,13,14,15) -- #4
- N4 fix: normalized root-cause grouping, render once (9,18 + grouping) -- #4
- N5 feat: additive JSON contract -- evidence, graph, diff (8) -- #4
- N6 refactor: requests/evidence/resolution, drop prose mutation (16,17) -- #4
- N7 refactor: centralize Snowflake metadata + identifiers (19,20,24) -- #4
- N8 spike: real warehouse-neutral adapter contract (21) -- #4
- N9 fix: complete consumed-path registry + schema gate (11,12,22) -- #48
- N10 fix: validate config/profile shapes, no silent fallback (10,25) -- #4
- N11 feat: standalone artifacts + explicit live policy (26,27) -- #4
- N12 test: real-artifact contracts + gated live CI (Section 5) -- #48

Change 23 (`_is_lagging` dead code) overlaps closed #50 -- fold into N2 as residual
cleanup, do not file standalone. Change 27 is a product DECISION, not code.

Create now (PROVEN, dependency-light): N1, N2, N4, N9, N10, N12 + the two epic
body updates. Defer (refine after the slice lands typed probes and the
live-default/portability decisions): N3, N5, N6, N7, N8, N11.

## Workflow (per AGENTS.md)

ASCII-only; no AI-authorship markers anywhere; one PR per issue; branch off
`donkey-kong-sandbox`; conventional commits; CHANGELOG on behavior change;
additive `--json`. The agent token cannot modify `.github/workflows/*`; hand CI
changes to the maintainer.
