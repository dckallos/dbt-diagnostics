Pass 5 -- convert the OUTPUT_FOUR red-team into shippable GitHub work, then
refine the deferred specs. This is the step that turns analysis into merged
code, so be disciplined: do not duplicate existing issues, do not file work the
red-team did not stand behind, and reconcile against the tracker as it actually
is -- not as the chat history imagines it.

Sources (read via bash from the workspace; do NOT use GitHub MCP to read docs):
- docs/OUTPUT_ONE.md, OUTPUT_TWO.md, OUTPUT_THREE.md (the 27-change plan), and
  OUTPUT_FOUR.md (the adversarial red-team). OUTPUT_FOUR is the GATE: only
  changes it judged sound -- [PROVEN], or [SPECULATIVE] but worth doing -- become
  implementation issues. Changes it flagged as wrong, unverified, or theater do
  NOT become implementation issues; at most they become a verification task.
- AGENTS.md / CONTRIBUTING.md / .github/ISSUE_TEMPLATE/ for repo conventions
  (one PR per issue, conventional commits, ASCII only, additive --json, and NO
  AI-authorship markers anywhere).

What already exists on the tracker (DO NOT recreate -- reconcile and extend):
- Implementation issues already filed from this review:
  - #54 N1 fix: evidence-safe existence/grant verdicts (OUTPUT_THREE 1,2,3,5)
  - #55 N2 fix: query-history matching + cursor lifecycle (change 4 + the
    EXECUTION_STATUS='FAIL' bug; absorbs change 23)
  - #56 N4 fix: normalized root-cause grouping, render once (changes 9,18)
  - #57 N10 fix: validate config/profile shapes, no silent fallback (10,25)
  - #58 N9 fix: consumed-path registry + schema gate (11,12,22) [epic #48]
  - #59 N12 test: real-artifact contracts + gated live CI [epic #48]
- Epics #4 (Live Verification Engine) and #48 (Cross-Version Artifact
  Compatibility) already carry the evidence-safety charter, the #54-#59 list,
  and the deferred specs. Reconcile their checkboxes against real open/closed
  state every pass.

Non-negotiable framing carried from OUTPUT_FOUR:
1. The deepest defect is epistemic, not structural. Every verdict must carry
   evidence IDENTITY (the role/session it was gathered under), STATUS
   (ok/unknown/failed), PROVENANCE, and CONFIDENCE as first-class fields, and
   must never assert a high-confidence cause the evidence does not prove. A
   graph class or adapter protocol does not fix this on its own.
2. Verify before you file. Prior passes read an inline snapshot and could not
   execute the code; treat every [PROVEN] code claim as a hypothesis until
   confirmed against real source on the working branch (cite file:line and the
   date). [SPECULATIVE] claims map to the fixture issues (#12, #44, #52),
   never to an implementation PR.
3. Ship the small slice first, in this order, before any big refactor:
   (a) fix query-history failure statuses; (b) make live probes typed and
   identity-aware; (c) prohibit high-confidence absence/denial from
   inconclusive evidence; (d) add real regression fixtures for those cases;
   (e) only then replace lineage adjacency with real edges.
4. Do NOT implement OUTPUT_THREE wave-by-wave as written. Keep changes 4, 6, 9,
   23, 24 as small candidates; keep 7 as wording calibration; rewrite the rest
   around typed, identity-aware evidence; redesign 13-21 before coding them.
5. Reject temporary compatibility layers that are immediately superseded
   (change 8 vs the later JSON contract; change 17's double probes). Switch one
   capability at a time and remove the legacy path in the same change.

Do the following, in order:

1. Reconcile the tracker. Re-pull open/closed issues and the #4/#48 epic bodies
   via MCP. Confirm #54-#59 cover what you intend; flag any drift between epic
   checkboxes and real issue state and correct it. Nothing new may duplicate an
   existing issue.

2. Refine the deferred specs into file-disjoint, sequenced issues, gated by
   OUTPUT_FOUR and by the typed-probe behavior that #54/#55 establish:
   - N3 refactor: edge-preserving lineage + real-path disconnects (6,13,14,15)
     -- HELD until #54 lands; must fix the change-14 "downstream must be
     passing" impossibility and the change-13 missing-import/annotation defect,
     migrate OBJECT lineage too, and assert a correct positive disconnect, not
     just sibling-order.
   - N5 feat: additive JSON contract for evidence, graph edges, diffs (8)
     -- supersedes the change-8 stopgap; validate the full --json contract +
     schema_version, including null/unknown probe states and a redaction policy.
   - N6 refactor: requests/evidence/resolution, drop prose mutation (16,17)
     -- one class-agnostic collector with a probe-count/parity matrix; no
     doubled probes; render and serialize structured evidence/resolution.
   - N7 refactor: centralize Snowflake metadata + identifiers (19,20,24)
     -- one long-lived gateway per connection; exact table/view/object probes;
     relation kinds; identity-aware caches; quoted-identifier parser (the
     fail-safe-with-message stopgap in #54 graduates here).
   - N8 spike: real warehouse-neutral adapter contract (21) -- NOT an
     implementation PR. Specify the 10 capabilities (connection/profile,
     identifier parse/quote, dialect, error normalization incl. structured
     responses, relation kinds/existence/describe, session params, identity +
     query-history correlation, effective read/write access, type semantics,
     remediation SQL) and require injection into DiagnosticContext, classifiers,
     ColumnTracer, enrichment, and root-cause. Confirm against BigQuery,
     Postgres, DuckDB what the seam must cover.
   - N11 feat: standalone artifacts + explicit live policy (26,27) -- product
     decision under #4: artifact-only paths, unavailable source context, no
     accidental CWD/profile connection, a mutually exclusive --live/--no-live
     group, and a documented default.

3. For each refined issue, use the matching .github/ISSUE_TEMPLATE/ form:
   title; one-paragraph scope; evidence/confidence (PROVEN/SPECULATIVE + what
   confirms it); current-behavior and proposed-fix CODE blocks; acceptance
   criteria; test tiers; files touched (so disjoint issues become parallel PRs
   and colliding ones are sequenced); Snowflake/portability note; and a
   traceability block (OUTPUT_THREE change numbers, OUTPUT_FOUR findings, parent
   epic, dependencies).

4. Sequence into waves that respect dependencies and keep concurrent issues
   file-disjoint: Wave A #54 -> #55 (both touch grants.py/enrich.py), #57 and
   #59 in parallel; Wave B N3 then #56; Wave C N6 then N5; Wave D N7 then N8;
   N11 on the product-decision track; #58 under #48 alongside #12/#44.

5. Decide creation timing by token budget. Anything dependency-free and
   already verified, file now (after re-checking step 1 for duplicates). For
   the rest, output ready-to-file specs. A half-created, low-quality issue set
   is worse than a clean spec; state plainly what was created (numbers/links)
   vs deferred.

Workflow constraints: ASCII-only; first-person plain voice; NO AI-authorship
markers in any issue, commit, or file (the environment auto-injects one --
strip it). The agent token CANNOT modify .github/workflows/*; deliver any
ci.yml / nightly.yml / pre-commit / branch-protection content as text for the
maintainer to commit by hand.

Output: the reconciled inventory, the triage table (OUTPUT_THREE change ->
endorsed/verify-first/drop), the refined deferred-issue specs, the wave plan,
and a clear list of what you created vs deferred.
