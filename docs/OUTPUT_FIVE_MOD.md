# 1. Executive verdict

## Tracker health

**[PROVEN] The tracker is directionally sound but not release-ready.** It contains 24 open issues, none of the fetched open issues is assigned to a milestone, two active epics, several stale feature bodies, six recently filed review-driven issues, and no milestone currently functions as the authoritative initial-release gate.

[SPECULATIVE] Whether an unattached milestone already exists was not established because the connector results exposed issue milestone assignments, not a complete milestone inventory.

The most consequential problems are:

1. **[PROVEN] The live layer can reach confidently wrong conclusions.** `table_exists()` returns `None` when a probe fails, but `_enrich_lineage_trail()` converts every falsey result into `"missing"`. `check_role_grants()` and `check_write_access()` erase query failures into ordinary negative-looking results, and `root_cause._apply_verdict()` can convert those into high-confidence `never_built` or `denied` verdicts. #54 correctly identifies the class of defect, but its current body still needs a tighter same-identity, relation-kind-aware contract.

   This is not merely theoretical Snowflake nuance: `SHOW TABLES` is visibility-limited, uses wildcard matching, and does not cover views; quoted Snowflake identifiers can contain dots and preserve case. An empty result cannot establish physical nonexistence. ([Snowflake Documentation][1])

2. **[PROVEN] Query-history enrichment is currently broken for failed executions.** `query_history.py` filters `INFORMATION_SCHEMA.QUERY_HISTORY` on `EXECUTION_STATUS = 'FAIL'`, while that table function reports failure states such as `FAILED_WITH_ERROR` and `FAILED_WITH_INCIDENT`. #55 owns this release-blocking correction.  ([Snowflake Documentation][2])

3. **[PROVEN] Lineage disconnects are inferred from display order rather than graph edges.** `DagWalker.trace_column_lineage()` returns a flat BFS list, while `_identify_disconnect()` treats adjacent entries as parent-child boundaries. On a branching DAG, adjacent entries may be siblings. `trace_object_lineage()` additionally searches all manifest nodes rather than only reachable ancestors.

4. **[PROVEN] Generic report grouping can prescribe the wrong remedy.** `group_reports()` groups by `error_class:schema`, then labels any runtime group as unmaterialized models. It can therefore collapse an invalid identifier, privilege failure, syntax error, and missing object into one false `dbt build` recommendation. #56 correctly identifies the problem.

5. **[PROVEN] The machine-readable report contract is not yet canonical.** Live enrichment, full live lineage, graph relationships, and `DiffResult` are omitted from JSON, while the terminal renderer independently performs grouping and consumes mutable domain objects.

   The target architecture is one versioned, JSON-compatible canonical report document. `--json` serializes that document directly, and terminal text is a presentation projection of it. The terminal renderer must not classify, group, resolve confidence, select a cause, or invent a fix.

6. **[PROVEN] The release-engineering backlog is fragmented.** #59 mixes offline CI, packaging, real fixtures, branch protection, and persistent live Snowflake CI. The maintainer has already objected to the live-CI scope and suggested releasing first.  The right response is to split the issue, not to publish without live verification.

7. **[PROVEN] Several tracker bodies are stale.** For example, #8 still says the linter exists and is blocked by #25, although PR #29 removed it and closed #25.

8. **[PROVEN] The compatibility gate exists in workflow code but may still be dormant.** PR #53 explicitly left schema-cache population as a maintainer follow-up; the selected snapshot still uses a sentinel that allows the job to pass without the cache.

## Recommended initial-release boundary

The initial public release should include only:

* Evidence-safe Tier-A live behavior.
* Correct query-history matching and cursor management.
* Exact root-cause grouping.
* Edge-preserving lineage.
* A canonical, versioned JSON report document containing structured evidence and final resolutions, with terminal text derived from that document.
* Explicit live opt-in and safe artifact-only operation.
* Validated artifact/config/profile boundaries.
* Python 3.11 and 3.12 offline CI, build, wheel smoke, and mandatory compatibility checks.
* One credential-gated pre-release Snowflake verification run.
* A license, security policy, complete package metadata, and tested Trusted Publishing.

**[PROVEN] Tier-B scans, new diagnostic families, warehouse portability, logs, partial-parse analysis, and compatibility watch work should not delay the initial release.**

**Recommended release:** `v0.6.0`. That version is a maintainer decision, but a minor increment is appropriate because the release changes live-mode defaults and adds user-visible behavior.

---

# 2. Complete issue inventory

|  # | Current title                                                                                         | Type       | Current labels                                               | Parent / current dependencies                       | Disposition                  | Priority | Release target          |
| -: | ----------------------------------------------------------------------------------------------------- | ---------- | ------------------------------------------------------------ | --------------------------------------------------- | ---------------------------- | -------- | ----------------------- |
|  4 | `[Epic] Live Verification Engine: pivot from static linting to DB-grounded root-cause`                | Epic       | `epic`                                                       | None; umbrella for live work                        | **KEEP OPEN — MODIFY**       | P1       | Initial-release tracker |
|  5 | `[Feature] UC #2: upstream grain tracing for uniqueness/relationship failures (gated)`                | Feature    | `priority: next`, `decision-needed`, `tier-b`, `blocked`     | #4; Tier-B ceiling; grain-source decision           | **KEEP OPEN — MODIFY**       | P2       | Post-release            |
|  6 | `[Feature] UC #7: live orphan-FK detection on relationship-test failures (gated)`                     | Feature    | `priority: deferred`, `decision-needed`, `tier-b`, `blocked` | #4; Tier-B ceiling                                  | **KEEP OPEN — MODIFY**       | P2       | Post-release            |
|  8 | `[Feature] UNION-branch type-coercion attribution (to migrate into contract_violation)`               | Feature    | `tier-a`, `priority: next`, `blocked`                        | #4; stale dependency on closed #25                  | **KEEP OPEN — MODIFY**       | P2       | Post-release            |
|  9 | `[Feature] Incremental low/zero-rows differential diagnosis (why 0 merged -> targeted remedy)`        | Feature    | `tier-a`, `priority: next`                                   | #4; benefits from #43                               | **KEEP OPEN — MODIFY**       | P2       | Post-release            |
| 10 | `[Feature] Static grain-consistency cross-check (proactive, $0)`                                      | Feature    | `tier-a`, `priority: deferred`                               | #4; parser decision resolved                        | **KEEP AS-IS**               | P2       | Post-release            |
| 12 | `[Feature] Replace guessed test fixtures with golden fixtures from real dbt runs`                     | Feature    | `priority: deferred`, `decision-needed`                      | Overlaps the current real-fixture policy and #44    | **MERGE INTO ANOTHER ISSUE** | —        | Merge into #44          |
| 15 | `[Feature] Tier-1 attested run identity: optional dbt pre-execution hook to stamp the run's role`     | Feature    | `tier-a`, `priority: deferred`, `decision-needed`            | #4; should follow #54/#55                           | **KEEP OPEN — MODIFY**       | P3       | Research backlog        |
| 28 | `[Feature] Re-home type_hazard TIMESTAMP_LTZ/NTZ detection as a post-failure enricher`                | Feature    | None                                                         | #4; overlaps current code and #8                    | **MERGE INTO ANOTHER ISSUE** | —        | Merge into #8           |
| 33 | `chore: automate PyPI release via trusted publishing (build + gated publish on release)`              | Chore      | `chore`                                                      | Package baseline; offline gates; live verification  | **KEEP OPEN — MODIFY**       | P1       | Initial release         |
| 41 | `feat: dbt_version-aware "newer than validated" note in schema_version (v12 freeze)`                  | Feature    | None                                                         | #48; #36 and #39 complete                           | **KEEP OPEN — MODIFY**       | P1       | Initial release         |
| 43 | `feat: consume sources.json for stale-source diagnosis (restore E5)`                                  | Feature    | None                                                         | #48; should follow #58                              | **KEEP OPEN — MODIFY**       | P2       | Post-release            |
| 44 | `test: cross-version golden-artifact matrix (capture real target/ per dbt version)`                   | Test       | None                                                         | #48; absorbs the remaining useful scope from #12    | **KEEP OPEN — MODIFY**       | P2       | Post-release hardening  |
| 45 | `spike: decide whether to consume the structured event/log stream (protocol-versioned)`               | Spike      | None                                                         | #48                                                 | **KEEP AS-IS**               | P3       | Research backlog        |
| 46 | `spike: stale partial_parse.msgpack as a post-hoc failure cause`                                      | Spike      | None                                                         | #48                                                 | **KEEP AS-IS**               | P3       | Research backlog        |
| 47 | `docs: add compat/WATCH.md for low-urgency compatibility watch items`                                 | Docs       | None                                                         | #48                                                 | **KEEP AS-IS**               | P3       | Research/docs backlog   |
| 48 | `[Epic] Cross-Version Artifact Compatibility (offline reader feeding the live layer)`                 | Epic       | `epic`                                                       | Sibling of #4                                       | **KEEP OPEN — MODIFY**       | P1       | Initial-release tracker |
| 52 | `test: capture real catalog.json fixture for schema-drift scenario 12 (activates #42 contract tests)` | Test       | None                                                         | #48; real Snowflake/artwork-db access               | **KEEP AS-IS**               | P1       | Initial release         |
| 54 | `fix: make live existence and grant verdicts evidence-safe`                                           | Bug        | `bug`                                                        | #4; should follow narrowed #55                      | **KEEP OPEN — MODIFY**       | P0       | Initial release         |
| 55 | `fix: repair Snowflake query-history matching and cursor lifecycle`                                   | Bug        | `bug`                                                        | #4                                                  | **KEEP OPEN — MODIFY**       | P0       | Initial release         |
| 56 | `fix: group by normalized root cause and render each report exactly once`                             | Bug        | `bug`                                                        | #4; depends on #54 semantics                        | **KEEP OPEN — MODIFY**       | P0       | Initial release         |
| 57 | `fix: validate config and profile shapes without silent fallback`                                     | Bug        | `bug`                                                        | #4                                                  | **KEEP OPEN — MODIFY**       | P0       | Initial release         |
| 58 | `fix: make the consumed-path registry and schema gate semantically complete`                          | Bug/compat | `compat`                                                     | #48; first-party cache                              | **SPLIT**                    | P1       | Initial release         |
| 59 | `test: enforce real-artifact contracts and gated live-Snowflake CI`                                   | Test       | `test`                                                       | #48; #12/#44/#52; #54/#55                           | **SPLIT**                    | P1       | Initial release         |

No milestone is currently attached to any open issue. The two epics have been updated recently, but #4 still mixes release blockers, post-release features, and unresolved placeholders.  The #48 status board is materially better reconciled.

---

# 3. Disposition matrix

|  # | Primary disposition      | Load-bearing reason                                                                                                                          |
| -: | ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
|  4 | KEEP OPEN — MODIFY       | [PROVEN] It is the correct live umbrella, but its child list, ordering, release gate, and references are stale.                              |
|  5 | KEEP OPEN — MODIFY       | [PROVEN] Valuable post-release capability, but it conflates unique and relationships failures and lacks settled grain/cost contracts.        |
|  6 | KEEP OPEN — MODIFY       | [PROVEN] Valid reactive feature, but the proactive deep-scan clause violates the current thesis and cost boundary.                           |
|  8 | KEEP OPEN — MODIFY       | [PROVEN] Work remains, but #25 is complete and #28’s remaining useful scope belongs here.                                                    |
|  9 | KEEP OPEN — MODIFY       | [PROVEN] Its differential framing is useful, but it calls an optional `COUNT(*)` Tier A and is too broad for one coherent implementation.    |
| 10 | KEEP AS-IS               | [PROVEN] It is the explicit, narrowly permitted proactive consistency check in the project thesis.                                           |
| 12 | MERGE INTO ANOTHER ISSUE | [PROVEN] #12 and #44 both propose a deterministic dbt-snowflake generator and real artifact capture. #44 should absorb the remaining current-version fixture audit and add the cross-version dimension. |
| 15 | KEEP OPEN — MODIFY       | [PROVEN] A product/design decision must precede implementation; it should be a spike.                                                        |
| 28 | MERGE INTO ANOTHER ISSUE | [PROVEN] The classifier already handles `CURRENT_TIMESTAMP`/`SYSDATE`; remaining branch attribution and `GETDATE` completeness belong in #8. |
| 33 | KEEP OPEN — MODIFY       | [PROVEN] Trusted Publishing is correct, but package baseline, TestPyPI, artifact reuse, and release dependencies are missing.                |
| 41 | KEEP OPEN — MODIFY       | [PROVEN] The current body conflates recognized schema major with real-version validation.                                                    |
| 43 | KEEP OPEN — MODIFY       | [PROVEN] The optional artifact is useful, but the body has completed dependencies, treats a live freshness query too cheaply, and must describe stale-source data as evidence rather than a generic proven cause. |
| 44 | KEEP OPEN — MODIFY       | [PROVEN] The matrix is valuable post-release, but its capture naming and provenance must conform to the repository rule that only `real_*` files represent captured dbt runs; it should absorb #12. |
| 45 | KEEP AS-IS               | [PROVEN] Properly scoped research with no production code.                                                                                   |
| 46 | KEEP AS-IS               | [PROVEN] Properly scoped research with a go/no-go deliverable.                                                                               |
| 47 | KEEP AS-IS               | [PROVEN] Low-risk docs backlog with explicit action triggers.                                                                                |
| 48 | KEEP OPEN — MODIFY       | [PROVEN] Correct umbrella, but release-critical and post-release children need separation and the cache status must remain evidence-based.   |
| 52 | KEEP AS-IS               | [PROVEN] Exact missing artifact and test activation are clearly specified.                                                                   |
| 54 | KEEP OPEN — MODIFY       | [PROVEN] Correct keystone bug, but quoted identifiers, relation kinds, identity consistency, and degradation boundaries need correction.     |
| 55 | KEEP OPEN — MODIFY       | [PROVEN] Correct defect, but it should land before #54 and remain narrow enough for one PR.                                                  |
| 56 | KEEP OPEN — MODIFY       | [PROVEN] Correct blocker; signatures must be structured rather than a new message regex.                                                     |
| 57 | KEEP OPEN — MODIFY       | [PROVEN] Malformed explicit config/profile input can silently alter discovery and live-connection behavior. Keep this issue focused on configuration, profiles, and dotenv rather than adding artifact indexing. |
| 58 | SPLIT                    | [PROVEN] Runtime artifact indexing and semantic JSON-Schema comparison are separate subsystems with different call sites and acceptance tests. Retain schema-gate work in #58 and create a separate indexed-artifact-view issue. |
| 59 | SPLIT                    | [PROVEN] Offline release gates and persistent live Snowflake CI have different cost, ownership, and acceptance conditions.                   |

---

# 4. Issues to keep as-is

## #10 — Static grain-consistency cross-check

**P2, post-release.** The issue is narrowly fenced as declaration consistency rather than general SQL linting. It has a concrete target case and does not require live credentials.

## #45 — Structured event/log spike

**P3, research backlog.** It asks a decision question and forbids production implementation. When executed, the spike should use first-party dbt source, schemas, and documentation rather than treating a secondary mirror as authoritative.

## #46 — `partial_parse.msgpack` spike

**P3, research backlog.** It correctly investigates a dependency/versioning decision before coding.

## #47 — Compatibility watch file

**P3, docs backlog.** The issue is explicitly non-runtime and each watch item has an action trigger.

## #52 — Real healthy catalog fixture

**P1, initial release.** The exact missing artifact and test that it activates are identified. The selected snapshot deliberately omitted large fixtures, so the fixture’s current presence remains unverified; the issue should remain open until the real file and non-skipped test are demonstrated.

---

# 5. Issues to modify

No new labels are required for these recommendations; every proposed label below already appears in the tracker.

## #4

**Proposed title:** `[Epic] Live Verification Engine and initial-release correctness`
**Type:** Epic
**Labels:** `epic`, `priority: now`
**Parent:** None
**Dependencies:** None; umbrella only
**Release target:** Initial-release tracker

<details>
<summary>Replacement body</summary>

```markdown
## Epic: Live Verification Engine and initial-release correctness

Design doc: `docs/DESIGN_LIVE_VERIFICATION.md`

### Thesis

The package provides live, database-grounded root-cause analysis. Artifact
declarations are observations and hypotheses, not proof of current warehouse
state. Every live conclusion must preserve probe status, identity, provenance,
and confidence.

Offline operation must remain useful and must degrade to `unverified` with the
query or evidence needed to confirm the hypothesis.

### Initial-release gate

Correctness and safety:

- [ ] #55 -- repair Snowflake query-history matching and cursor lifecycle
- [ ] #54 -- make relation and grant evidence identity-aware and non-assertive
- [ ] #56 -- distinguish structured symptom groups from proven root-cause groups and assemble each report once
- [ ] #57 -- validate config/profile shapes without silent fallback
- [ ] New issue: centralize validated artifact access in one indexed diagnosis context
- [ ] New issue: make live probing explicit and support artifact-only diagnosis
- [ ] New issue: preserve DAG edges and resolve disconnects only on reachable paths
- [ ] New issue: separate observations, typed evidence, and final resolution
- [ ] New issue: make one canonical JSON report document drive `--json` and terminal output
- [ ] New issue: verify live Snowflake evidence semantics before release

Release engineering owned elsewhere:

- [ ] #59 -- offline release gates
- [ ] #33 -- TestPyPI and PyPI Trusted Publishing

### Completed children

- [x] #7 -- initial single-root-cause aggregator, PR #16
- [x] #20 -- artifact schema-version reporting, PR #22
- [x] #23 -- property and chaos test tiers, PR #27
- [x] #24 -- defensive artifact handling, PR #26
- [x] #25 -- remove static linter, PR #29

### Post-release capabilities

- [ ] #8 -- UNION-branch type-coercion attribution
- [ ] #9 -- incremental no-op differential diagnosis
- [ ] #10 -- static grain-consistency cross-check
- [ ] #5 -- live uniqueness grain tracing, Tier B and gated
- [ ] #6 -- live orphan-key diagnosis, Tier B and gated

### Research backlog

- [ ] #15 -- choose an optional attested run-identity mechanism

### Open decisions

- **OPEN:** Tier-B cost ceiling, query cap, and lineage-depth cap.
- **OPEN:** Authoritative grain sources for Tier-B tracing.
- **OPEN — audit recommendation:** For the first public release, make live
  Snowflake access explicit opt-in and make artifact-only analysis the safe
  default. Record the maintainer's decision before implementing the CLI change;
  do not describe this as resolved until that decision is accepted in the
  tracker.
- **RESOLVED:** JSON changes are additive within the current major.
- **RESOLVED:** `sqlglot` is the supported Snowflake parser.
- **RESOLVED:** Static linting remains out of scope except for #10.

### Workflow

ASCII-only; one PR per issue; branch from `donkey-kong-sandbox`; tests and
CHANGELOG in behavior-changing PRs; docs follow code.
```

</details>

**What changed:** Removed unavailable review-document traceability, corrected the child sequence, separated release blockers from post-release features, and replaced unfiled shorthand placeholders with explicit issue titles.

---

## #5

**Proposed title:** `feat: trace uniqueness-test failures to the first live-confirmed grain break`
**Type:** Feature / capability
**Labels:** `enhancement`, `tier-b`, `blocked`, `decision-needed`, `priority: deferred`
**Parent:** #4
**Dependencies:** New lineage issue; new evidence-resolution issue; Tier-B ceiling; grain-source decision
**Release target:** Post-release

<details>
<summary>Replacement body</summary>

```markdown
## Summary

When a `unique` or `unique_combination_of_columns` test fails, trace the
declared grain upstream and identify the first reachable edge where uniqueness
is live-confirmed to break.

This issue does not own `relationships` failures; #6 owns orphan-key diagnosis.

## Cost tier

- Tier: **B (gated)**.
- Off by default.
- Enforce a per-relation row ceiling or approved sample strategy, a per-run
  query cap, and a maximum upstream depth.

## Trigger

A failed dbt uniqueness test whose tested relation and declared key columns can
be resolved from the manifest.

## Behavior

1. Resolve the tested relation and key columns from the test node.
2. Produce a bounded duplicate-key sample on the failed relation.
3. Walk only real upstream DAG paths.
4. At each eligible upstream relation, test the declared grain.
5. Report the nearest live-confirmed grain break.
6. Stop with `unverified` if grain resolution, visibility, cost approval, or a
   probe fails.

## Evidence and confidence

- Status: **PROVEN** that the capability is not implemented.
- The inferred origin must never be reported as confirmed without a successful
  Tier-B probe on the named relation and grain.
- A missing grain declaration is `unsupported`, not evidence of uniqueness.

## Acceptance criteria

- [ ] A real uniqueness failure resolves to the correct reachable upstream edge.
- [ ] A branching DAG never reports a sibling boundary.
- [ ] A wrong or absent grain declaration degrades to `unverified`.
- [ ] No Tier-B SQL runs without explicit opt-in and the cost gate.
- [ ] Offline output includes the proposed query and unresolved grain source.
- [ ] JSON additions are additive; CHANGELOG updated.

## Test plan

- Offline: unit and e2e tests for test-node parsing, graph paths, gating, and
  degradation.
- Live: credential-gated test on a disposable small relation.

## Scope and files touched

- Test-failure diagnosis
- DAG/path tracing
- Tier-B probe layer
- Terminal and JSON output

## Snowflake / portability impact

Snowflake-specific distinctness SQL belongs behind the metadata/probe gateway.

## Traceability

- Parent epic: #4
- Blocked by: Tier-B policy, lineage graph, structured evidence resolution
```

</details>

**What changed:** Removed `relationships` overlap, made real graph paths mandatory, and replaced vague gating with observable cost controls.

---

## #6

**Proposed title:** `feat: diagnose failing relationships tests with a cost-gated orphan-key probe`
**Type:** Feature / capability
**Labels:** `enhancement`, `tier-b`, `blocked`, `decision-needed`, `priority: deferred`
**Parent:** #4
**Dependencies:** New lineage/evidence issues; Tier-B ceiling
**Release target:** Post-release

<details>
<summary>Replacement body</summary>

```markdown
## Summary

For a failed dbt `relationships` test, report a bounded orphan-key count and
sample, then identify the reachable parent relation that the test expected to
supply those keys.

This issue is reactive only. It does not add a proactive scan of passing builds.

## Cost tier

- Tier: **B (gated)**.
- Off by default.
- Enforce row/sample limits, a per-run query cap, and a hard sample-size limit.

## Trigger

A failed `relationships` test whose child relation, child key, parent relation,
and parent key can be resolved from the test node.

## Behavior

1. Resolve the relationship configuration from the manifest.
2. Build the anti-join query without executing it in offline mode.
3. When explicitly approved, run the bounded orphan-key probe.
4. Report count, sampled keys, probe identity, and confidence.
5. Use real DAG edges to show the expected parent path.
6. Degrade to `unverified` on visibility, query, cost, or configuration failure.

## Evidence and confidence

- Status: **PROVEN** that this capability is not implemented.
- An orphan cause is confirmed only by a successful probe.
- A missing or inaccessible parent remains `unverified`; it is not automatically
  classified as physically absent.

## Acceptance criteria

- [ ] A real failed relationships test yields the correct bounded orphan sample.
- [ ] The named parent is reachable from the tested node.
- [ ] The probe never runs without opt-in and cost approval.
- [ ] Offline output includes the exact query and cost classification.
- [ ] Failed and visibility-limited probes remain unverified.
- [ ] JSON additions are additive; CHANGELOG updated.

## Test plan

- Offline unit/e2e cases for parsing, query construction, and degradation.
- Credential-gated live case on disposable small relations.

## Scope and files touched

- Test-failure classifier
- Lineage graph
- Tier-B probe layer
- Terminal and JSON output

## Traceability

- Parent epic: #4
- Blocked by: Tier-B policy, lineage graph, structured evidence resolution
```

</details>

**What changed:** Removed the out-of-scope proactive scan and made relation reachability, probe identity, and cost gating explicit.

---

## #8

**Proposed title:** `feat: attribute contract type coercion to the responsible expression or UNION branch`
**Type:** Feature / capability
**Labels:** `enhancement`, `tier-a`, `priority: deferred`
**Parent:** #4
**Dependencies:** New structured-evidence issue; no dependency on #25
**Release target:** Post-release

<details>
<summary>Replacement body</summary>

```markdown
## Summary

After a real contract type mismatch, identify the compiled expression that
produced the mismatched output. For UNION models, identify the responsible
branch and projected expression that caused Snowflake type promotion.

This issue absorbs #28. The current classifier already handles the simple
`CURRENT_TIMESTAMP()` and `SYSDATE()` cases; the retained work adds
`GETDATE()` parity, completes source-location evidence, and adds robust
multi-branch UNION attribution.

## Cost tier

- Tier: **A**.
- SQL analysis is offline.
- Optional live confirmation uses relation description metadata only.

## Trigger

A real `contract_violation` involving a type mismatch. UNION-specific branch
analysis runs only when the mismatched output is produced by `UNION` or
`UNION ALL`.

## Behavior

1. Parse the compiled SQL with `sqlglot` using the Snowflake dialect.
2. Resolve the output column position across every UNION branch.
3. Record each branch expression and explicit cast.
4. Identify asymmetric timestamp or other type coercion.
5. Explain Snowflake's promoted result as a hypothesis.
6. Confirm the final live column type when the relation can be described.
7. Degrade to `unverified` if parsing, branch alignment, or live description
   fails.

## Evidence and confidence

- Status: **PROVEN** that branch-specific attribution is not implemented.
- Current source already covers the simple single-expression
  `CURRENT_TIMESTAMP()` and `SYSDATE()` cases.
- Manifest or parser inference alone must not be labeled live-confirmed.

## Acceptance criteria

- [ ] The target UNION fixture names the responsible branch and expression.
- [ ] `CURRENT_TIMESTAMP()`, `SYSDATE()`, and `GETDATE()` are handled.
- [ ] Nested CTE and N-branch UNION cases are covered.
- [ ] A parser failure produces an ordinary contract diagnosis, not a crash.
- [ ] Live type confirmation carries probe identity/status.
- [ ] JSON additions are additive; CHANGELOG updated.

## Test plan

- Unit tests for branch alignment and coercion.
- Real contract fixtures for the canonical JSON report document; terminal
  projection tests assert the same diagnosis without recomputing it.
- Credential-gated Tier-A type confirmation.

## Traceability

- Parent epic: #4
- Absorbs: #28
- #25 is complete and is not a blocker.
```

</details>

**What changed:** Removed the completed #25 blocker, acknowledged behavior already present in `ContractViolationClassifier`, and incorporated #28’s remaining useful scope.

---

## #9

**Proposed title:** `feat: explain incremental no-op runs from artifacts without blind full-refresh advice`
**Type:** Feature / capability
**Labels:** `enhancement`, `tier-a`, `priority: deferred`
**Parent:** #4
**Dependencies:** #43 for source freshness where available; new evidence model
**Release target:** Post-release

<details>
<summary>Replacement body</summary>

```markdown
## Summary

When an incremental model succeeds with zero or unexpectedly few affected rows
and a related downstream test fails, explain the artifact-supported candidate
causes without automatically recommending `--full-refresh`.

## Cost tier

- Core diagnosis: **Tier A / offline artifacts**.
- Any row count, late-arriving-row search, or data comparison is **Tier B** and
  is out of scope for this issue unless separately gated.

## Trigger

Both conditions are required:

1. A manifest node is materialized as incremental and reports zero or low
   affected rows.
2. The model or a reachable downstream node has a failing test.

Zero rows alone are normal and produce no diagnosis.

## Behavior

Use only artifact and optional freshness evidence to distinguish:

- healthy or unsupported no-op;
- upstream source stale;
- compiled SQL changed since the previous manifest;
- incremental configuration changed;
- downstream failure predates the current run;
- evidence insufficient.

Recommend `--full-refresh` only when the artifact evidence supports a
logic/configuration change that cannot repair existing target state.

## Evidence and confidence

- Status: **PROVEN** that the differential diagnosis is not implemented.
- `rows_affected` is adapter-specific and may be absent.
- Watermark/lookback bugs and duplicate cleanup cannot be confirmed without
  data scans; report them only as unverified follow-ups.

## Acceptance criteria

- [ ] Zero rows without a related failure emits no finding.
- [ ] Missing `rows_affected` degrades safely.
- [ ] Previous-manifest and source-freshness evidence are serialized.
- [ ] No COUNT or row scan runs in this issue.
- [ ] `--full-refresh` is not the default recommendation.
- [ ] JSON additions are additive; CHANGELOG updated.

## Test plan

- Offline unit and e2e tests using real incremental run artifacts.
- No live credentials required for this issue.

## Traceability

- Parent epic: #4
- Related: #43
```

</details>

**What changed:** Removed incorrectly classified Tier-A row scans and narrowed the issue to claims that artifacts can actually support.

---

## #15

**Proposed title:** `spike: choose an optional attested run-identity mechanism`
**Type:** Spike / investigation
**Labels:** `decision-needed`, `priority: deferred`, `tier-a`
**Parent:** #4
**Dependencies:** #54 and #55
**Release target:** Research backlog

<details>
<summary>Replacement body</summary>

````markdown
## Question to answer

Should dbt-diagnostics offer an optional attested run-identity mechanism, and
if so, should it use query comments, a marker relation, or another medium?

## Why this is a spike

The current query-history recovery has query-id, visibility, and retention
gaps. The proposed media have materially different properties:

- A query comment requires no write access but still depends on query-history
  visibility and retention.
- A marker relation can survive retention but requires object creation/write
  privileges and lifecycle management.
- Neither option should be implemented until the corrected #54/#55 identity
  and failure semantics are stable.

## Evidence and confidence

- Status: **SPECULATIVE** until tested against a real Snowflake account.
- Existing tracker history from #17 and #19 has been consolidated here.

## Investigation tasks

- [ ] Define the exact fidelity guarantees of each candidate.
- [ ] Test behavior when the diagnostic identity differs from the dbt identity.
- [ ] Test missing query ID and out-of-retention runs.
- [ ] Determine installation, discovery, cleanup, and security requirements.
- [ ] Decide whether the mechanism belongs in this Python package, a dbt
      package, or documentation only.

## Probe / reproduction

```text
Run one disposable dbt invocation with an identity marker, remove query-id
access from the diagnostic input, and verify whether the marker can still
recover role, user, warehouse, and invocation id.
````

## Deliverable

Record an explicit go/no-go decision and the chosen fidelity contract. If the
decision is "go", file one implementation issue with exact storage,
permissions, retention, and offline behavior.

## Acceptance criteria

* [ ] All candidate media are compared using real Snowflake evidence.
* [ ] Security and cleanup implications are documented.
* [ ] The decision is recorded in the repository.
* [ ] No production runtime code ships from this spike.

## Scope and files touched

* Documentation and disposable probe code only.

## Traceability

* Parent epic: #4
* Depends on: #54, #55
* Consolidates discussion from closed #17/#18/#19.

````

</details>

**What changed:** Converted an unresolved implementation proposal into the decision spike it actually is.

---

## #33

**Proposed title:** `chore: publish the first release through TestPyPI and PyPI Trusted Publishing`  
**Type:** Chore / maintenance  
**Labels:** `chore`, `priority: next`, `decision-needed`  
**Parent:** Standalone release issue  
**Dependencies:** New package-baseline issue; rewritten #59; new live-verification issue  
**Release target:** Initial release

PyPI Trusted Publishing uses OIDC rather than a long-lived token, requires `id-token: write`, supports TestPyPI, and is designed to be combined with a protected GitHub environment. :contentReference[oaicite:11]{index=11}

<details>
<summary>Replacement body</summary>

```markdown
## Summary

Build, test, and publish the initial release using PyPI Trusted Publishing.
Exercise the workflow on TestPyPI before the first production upload.

## Evidence and confidence

- Status: **PROVEN** that no publish workflow is present in the selected source.
- The package remains pre-release and version 0.5.0 is workspace-only.
- Trusted Publishing avoids a long-lived PyPI token.

## Scope / deliverables

- [ ] Add a build job that creates one sdist and one wheel.
- [ ] Run installed-wheel smoke tests against those artifacts.
- [ ] Upload the exact build artifacts as a workflow artifact.
- [ ] Add a protected TestPyPI publish path.
- [ ] Verify installation and `dbt-diagnostics --help` from TestPyPI.
- [ ] Add a production publish job triggered by an approved GitHub Release.
- [ ] Use `permissions: id-token: write` only on publish jobs.
- [ ] Use protected `testpypi` and `pypi` environments.
- [ ] Confirm `scripts/` and governance files do not ship in either artifact.
- [ ] Attach the tested wheel and sdist to the GitHub Release.
- [ ] Update CONTRIBUTING.md with the exact release flow.

## Config / command

```bash
python -m build
python -m venv smoke-venv
smoke-venv/bin/pip install dist/*.whl
smoke-venv/bin/dbt-diagnostics --help
````

## Acceptance criteria

* [ ] Package-baseline, offline-CI, and live-verification release gates are green.
* [ ] TestPyPI publish and install succeed before production publication.
* [ ] No PyPI API token is stored.
* [ ] Production publishing requires an approved release/environment.
* [ ] The wheel and sdist contain only intended package files.
* [ ] Version, tag, GitHub Release, package metadata, and CHANGELOG agree.
* [ ] No diagnostic or JSON behavior changes in this issue.

## Constraints / process note

Workflow changes must be committed by the maintainer because the coding-agent
token cannot modify `.github/workflows/*`.

## Scope and files touched

* `.github/workflows/release.yml`
* `CONTRIBUTING.md`
* packaging manifest/excludes if required

## Traceability

* Standalone release issue
* Depends on: package baseline, #59, pre-release live verification

````

</details>

**What changed:** Added TestPyPI, build-once discipline, package-content verification, and explicit release-gate dependencies.

---

## #41

**Proposed title:** `fix: distinguish recognized schema majors from newer-than-validated dbt versions`  
**Type:** Bug / correctness fix  
**Labels:** `bug`, `compat`, `priority: next`  
**Parent:** #48  
**Dependencies:** #58 for final field semantics  
**Release target:** Initial release

The current stable dbt release line remains 1.11, while newer prerelease work can still emit manifest v12 and run-results v6; the schema-major check alone therefore cannot mean “validated.” :contentReference[oaicite:12]{index=12}

<details>
<summary>Replacement body</summary>

```markdown
## Summary

Distinguish "the artifact schema major is recognized" from "this exact dbt
release line has been validated with real artifacts."

A future dbt version that still emits manifest v12 must not be silently labeled
validated merely because v12 is recognized.

## Evidence and confidence

- Status: **PROVEN**.
- `SUPPORTED_SCHEMAS` currently answers only whether a schema major is known.
- Manifest v12 spans multiple dbt release lines.
- Real-version validation is separately established by committed artifacts.

## Current behavior

A recognized major sets `supported=True` and emits no note, even when
`metadata.dbt_version` is newer than the highest validated dbt version.

## Expected behavior

- Preserve the existing `supported` meaning for recognized schema structure.
- Add an explicit additive validation state, for example:
  - `validated`
  - `newer_than_validated`
  - `unvalidated_major`
  - `unknown`
- Emit an advisory note for a newer dbt version on a recognized major.
- Never claim parsing is proven safe solely because the major is unchanged.

## Acceptance criteria

- [ ] Validated dbt version and major: supported and validated, no note.
- [ ] Newer dbt version on a recognized major: supported structurally,
      not validated, advisory note.
- [ ] Unknown major: unsupported and unvalidated.
- [ ] Missing/garbled dbt version: recognized-major behavior remains usable but
      validation is unknown.
- [ ] JSON additions are additive; CHANGELOG updated.
- [ ] Tests cover manifest and run-results independently and as a pair.

## Test plan

- Unit tests with inline metadata shapes.
- Contract test against each committed real-artifact version.

## Scope and files touched

- `dbt_diagnostics/schema_version.py`
- schema-version and CLI JSON tests

## Traceability

- Parent epic: #48
- Coordinate with: #58
````

</details>

**What changed:** Replaced the unsafe “future v12 is genuinely supported” claim with separate structural-support and real-validation states.

---

## #43

**Proposed title:** `feat: consume sources.json as optional upstream freshness evidence`
**Type:** Feature / capability
**Labels:** `enhancement`, `compat`, `priority: deferred`
**Parent:** #48
**Dependencies:** #58
**Release target:** Post-release

<details>
<summary>Replacement body</summary>

## Summary

Consume an optional, provenance-recorded `sources.json` and attach its freshness
results as upstream evidence for failures whose reachable lineage includes the
corresponding source.

A stale source is a candidate contributing condition. It is not automatically
the root cause of an arbitrary runtime or data failure.

## Cost tier

- Reading `sources.json`: offline artifact analysis; no Snowflake probe.
- A future query such as `MAX(loaded_at)` against the source relation is a
  warehouse data scan and therefore Tier B. It is out of scope here unless a
  separate cost-gated design is approved.

## Trigger

A diagnosed node has a reachable source dependency that also has a result in
the supplied `sources.json`.

## Behavior

1. Resolve optional `target/sources.json`.
2. Parse status, freshness criteria, `max_loaded_at`, and `snapshotted_at`
   through version-tolerant accessors.
3. Correlate freshness only to sources reachable from the failing node.
4. Record the artifact's timestamp and age so stale evidence is not presented
   as current warehouse truth.
5. Render and serialize the freshness evidence through the canonical report
   document.
6. Missing, malformed, or unrelated `sources.json` produces no diagnosis and no
   crash.

## Evidence and confidence

- Status: **PROVEN** that the package does not currently consume this artifact.
- Whether the proposed fields and tuple shapes behave consistently must be
  verified with a real `real_*` sources artifact.
- Freshness evidence alone does not establish causation.

## Acceptance criteria

- [ ] A reachable source with a warn/error freshness result appears as upstream
      evidence with status, criteria, and artifact timestamp.
- [ ] An unrelated stale source is ignored.
- [ ] A stale artifact is visibly marked as historical evidence.
- [ ] Missing or malformed sources artifacts degrade silently.
- [ ] No live source-table scan is introduced.
- [ ] The captured contract fixture begins with `real_` and records provenance.
- [ ] The canonical JSON report gains only additive fields; terminal text is
      derived from that report.
- [ ] CHANGELOG updated.

## Test plan

- Unit tests for tolerant accessors.
- Contract tests against a real `real_*_sources` artifact.
- Offline CLI tests for absent, stale, unrelated, warn, and error cases.

## Traceability

- Parent epic: #48
- Depends on: #58
- Related post-release consumer: #9

---

## #44

**Proposed title:** `test: build a provenance-recorded cross-version real-artifact matrix`
**Type:** Test / CI / fixtures
**Labels:** `test`, `compat`, `priority: deferred`
**Parent:** #48
**Dependencies:** #58 and the indexed-artifact-view issue
**Release target:** Post-release hardening

<details>
<summary>Replacement body</summary>

## Summary

Build a deterministic dbt-snowflake capture harness that absorbs the remaining
useful scope from #12 and extends it across supported dbt release lines.

The resulting real captures run offline in contract tests. Captured artifacts
must follow the repository's real-fixture naming and provenance rules.

## Evidence and confidence

- Status: **PROVEN** that the cross-version real-artifact matrix does not exist.
- The repository already contains current-version `real_*` failure captures.
- Published schemas alone cannot establish actual adapter output.

## Capture scope

Capture representative real artifacts for each selected dbt-snowflake line:

- healthy build;
- compilation failure;
- Snowflake runtime failure;
- failed generic test;
- catalog generation;
- source freshness;
- incremental no-op where supported.

Interrupted/truncated files are adversarial robustness inputs, not ordinary dbt
outputs, and should remain explicitly synthetic corruption cases.

## Fixture policy

- Every captured dbt artifact filename begins with `real_`.
- Each capture records dbt-core, dbt-snowflake, Python, schema URLs, scenario,
  date, source command, and SHA-256 provenance.
- Do not silently rewrite captured artifacts. If nondeterministic fields must be
  normalized, preserve the raw hash and document the deterministic transform.
- Update `docs/FIXTURE_CAPTURE.md` before introducing a second capture source.

## Acceptance criteria

- [ ] The current-version fixture audit formerly owned by #12 is completed.
- [ ] Real artifacts exist for the selected version boundaries.
- [ ] Every capture satisfies the `real_*` naming and provenance policy.
- [ ] Offline contract tests assert expected classification and structured
      output, not merely "does not crash."
- [ ] Runtime fields are compared with the relevant first-party schema.
- [ ] Unsupported version combinations are documented rather than fabricated.
- [ ] A repeatable capture command exists.
- [ ] CHANGELOG updated.

## Test plan

- Version-aware capture outside ordinary PR CI.
- Committed offline parametrized contract tests.
- Reality-versus-schema comparison against #58.

## Traceability

- Parent epic: #48
- Absorbs: #12
- Supports: #41, #58, #59

---

## #48

**Proposed title:** `[Epic] Cross-Version Artifact Compatibility and artifact contracts`
**Type:** Epic
**Labels:** `epic`, `priority: next`
**Parent:** None; sibling of #4
**Dependencies:** None
**Release target:** Initial-release tracker plus post-release hardening

<details>
<summary>Replacement body</summary>

```markdown
## Epic: Cross-Version Artifact Compatibility and artifact contracts

Design: `dbt_diagnostics/compat/DESIGN.md`

### Thesis

The runtime reads only the artifact fields it needs. First-party schemas and
provenance-recorded real artifacts establish compatibility. Unknown or
malformed inputs degrade safely without pretending that unvalidated behavior
is proven.

### Completed foundation

- [x] #35/#34 -- compatibility package and schema diff, PR #36
- [x] #37 -- safe accessor wiring, PR #49
- [x] #38 -- interrupted/corrupt artifact handling, PR #51
- [x] #39 -- mixed-version pair detection, PR #53
- [x] #40 -- schema-gate workflow and tooling, PR #53
- [x] #42 -- optional catalog consumption, PR #53
- [x] #50 -- datetime comparison correction, PR #49

### Initial-release gate

- [ ] #41 -- distinguish recognized majors from validated dbt versions
- [ ] #52 -- commit the real healthy catalog fixture
- [ ] #58 -- make the consumed-path registry and schema comparison semantic
- [ ] New issue -- centralize validated artifact access in indexed views
- [ ] #59 -- enforce offline release gates on Python 3.11 and 3.12

The first-party schema cache is a required release input. The workflow must not
pass merely because the cache is absent.

### Post-release hardening

- [ ] #43 -- consume `sources.json`
- [ ] #44 -- cross-version real-artifact matrix

### Research and docs backlog

- [ ] #45 -- structured event/log spike
- [ ] #46 -- partial-parse cache spike
- [ ] #47 -- compatibility watch file

### Cross-cutting rules

- First-party schemas and real artifacts are both required evidence.
- A recognized major is not the same as a validated dbt release.
- The consumed-path registry must match every runtime read.
- Runtime accessors and schema checks must share fallback definitions.
- JSON changes remain additive.
- Runtime diagnosis performs no network fetch.

### Relationship to #4

This epic establishes trustworthy artifact inputs. #4 owns diagnosis,
warehouse evidence, confidence, and final resolution.

### Workflow

ASCII-only; one issue per PR; tests and CHANGELOG for behavior changes; docs
follow merged code.
```

</details>

**What changed:** Removed uncertain claims that the cache is fully active, separated initial-release work from long-term compatibility research, and reconciled completed children.

---

## #54

**Proposed title:** `fix: make live relation and grant evidence identity-aware and non-assertive`
**Type:** Bug / correctness fix
**Labels:** `bug`, `priority: now`
**Parent:** #4
**Dependencies:** #55 should land first because both modify cursor/probe code
**Release target:** Initial release

<details>
<summary>Replacement body</summary>

```markdown
## Summary

Live relation and grant probes currently convert failed, visibility-limited, or
identity-mismatched observations into confident `never_built` or `denied`
verdicts. Replace ambiguous booleans and empty dictionaries with typed,
identity-aware outcomes and prohibit conclusions the evidence cannot prove.

## Evidence and confidence

- Status: **PROVEN**.
- `table_exists()` returns `None` on probe failure.
- `_enrich_lineage_trail()` currently converts that falsey value to `missing`.
- Grant helpers swallow exceptions and return negative-looking results.
- `root_cause._apply_verdict()` can turn those results into high-confidence
  absence or denial.
- `SHOW TABLES` observes only objects visible to the probing identity.

## Root cause

The model does not preserve:

- successful negative result vs query failure;
- physical absence vs not visible;
- diagnostic identity vs run identity;
- table vs view vs other relation kind;
- database USAGE vs schema USAGE vs object privilege.

## Expected behavior

Define typed outcomes with at least:

- status: `found`, `not_visible_or_missing`, `failed`, `unsupported`;
- `physically_absent` may be emitted only if an explicitly authoritative probe
  is introduced and its authority is recorded. Ordinary visibility-limited
  `SHOW` results must not use that state;
- value;
- probing identity and provenance;
- relation kind;
- reason/error;
- query used.

A visibility-limited result must never claim physical absence. Evidence gathered
under different identities must not be combined into one confirmed verdict.

## Proposed fix

- Add typed relation/grant/write-access probe results.
- Preserve `None`/failure as unknown rather than missing.
- Make relation checks exact and relation-kind-aware.
- Support correctly quoted identifiers or return `unsupported`; do not reject
  all quoted roles as invalid.
- Split database USAGE, schema USAGE, object privilege, and CREATE privilege.
- Add a top-level live-enrichment degradation boundary so one failed probe does
  not abort the diagnosis.
- Record all live observations in the canonical report document. `--json`
  exposes that document, and terminal text derives from it.

## Acceptance criteria

- [ ] Failed probes yield `unverified`, never confirmed absence or denial.
- [ ] Visibility-limited empty results remain `not_visible` or `unverified`.
- [ ] Probe identity and provenance are recorded.
- [ ] Tables and views are handled honestly.
- [ ] Database/schema/object/write privileges remain distinct.
- [ ] Quoted-identifier cases are supported or explicitly unsupported without
      unsafe SQL interpolation.
- [ ] One failed live probe cannot abort other reports.
- [ ] Positive, negative, visibility, and failure regression tests exist.
- [ ] JSON changes are additive; CHANGELOG updated.

## Test plan

- Unit tests with recorded cursor rows and failures.
- Offline e2e degradation tests.
- Credential-gated live verification with separate diagnostic and run roles.

## Scope and files touched

- Live relation/grant helpers
- Root-cause verdict logic
- Lineage live status
- canonical report-document evidence fields and additive JSON serialization

## Traceability

- Parent epic: #4
- Sequence after: #55
- Blocks: lineage resolution, structured evidence, live release verification
```

</details>

**What changed:** Corrected quoted-identifier handling, added relation kinds and same-identity requirements, and made the top-level degradation boundary explicit.

---

## #55

**Proposed title:** `fix: repair Snowflake query-history matching and close every cursor`
**Type:** Bug / correctness fix
**Labels:** `bug`, `priority: now`
**Parent:** #4
**Dependencies:** None
**Release target:** Initial release

<details>
<summary>Replacement body</summary>

```markdown
## Summary

Repair failed-query matching against Snowflake Information Schema and make
cursor cleanup reliable on success, execution failure, acquisition failure, and
close failure.

## Evidence and confidence

- Status: **PROVEN**.
- `query_history.py` filters on `EXECUTION_STATUS = 'FAIL'`, which does not match
  the failed states returned by the table function.
- Grant helpers open cursors without closing them.
- Several helpers create the cursor before entering their protected `try`.
- `_is_lagging()` contains an unreachable duplicate implementation.

## Current wrong behavior

A real failed query can produce no history match even when the time window and
SQL similarity are correct. Cursor and query failures can be erased into
ordinary empty results.

## Expected behavior

- Query documented failed execution states.
- Validate timing entries before using them.
- Close every acquired cursor.
- Preserve query failure separately from no matching row.
- Keep role/query identity and visibility limitations observable.
- Remove unreachable timestamp-comparison code.

## Acceptance criteria

- [ ] Recorded failed rows with each supported failure status are considered.
- [ ] A successful match returns code, message, status, identity, and confidence.
- [ ] No matching row is distinct from query failure.
- [ ] Every cursor acquired anywhere under `dbt_diagnostics/enrichers/` is
      closed on success, execution failure, fetch failure, and result-shape
      failure.
- [ ] Cursor acquisition and cursor-close failures are contained and cannot
      replace the original diagnostic outcome.
- [ ] Cursor acquisition and close failures do not mask the diagnosis.
- [ ] Malformed timing entries do not raise.
- [ ] Aware/naive timestamp tests remain green.
- [ ] CHANGELOG updated.

## Test plan

- Unit tests using recorded Snowflake row shapes.
- Robustness tests for malformed timing and cursor exceptions.
- Credential-gated live failed-query correlation before release.

## Scope and files touched

- `enrichers/query_history.py`
- `enrichers/grants.py`
- `enrichers/params.py`
- `enrichers/schema_inspector.py`
- `enrichers/run_identity.py`
- any shared cursor helper introduced for the package

## Traceability

- Parent epic: #4
- Must land before: #54
```

</details>

**What changed:** Reversed the dependency so the narrow status/cursor repair lands first, and avoided mixing the full probe ontology into the same PR.

---

## #56

**Proposed title:** `fix: group by structured signatures and assemble each report exactly once`
**Type:** Bug / correctness fix
**Labels:** `bug`, `priority: now`
**Parent:** #4
**Dependencies:** #54 semantics; coordinate with the structured-evidence issue
**Release target:** Initial release

<details>
<summary>Replacement body</summary>

## Summary

Replace schema-wide grouping with two explicit structured concepts:

- a **symptom group** for repeated reports sharing the same normalized failure
  signature when the cause remains unresolved;
- a **root-cause group** only when the reports share the same final resolved
  cause.

Assemble groups and individual reports once in the canonical report document
before JSON serialization or terminal rendering.

## Evidence and confidence

- Status: **PROVEN**.
- `group_reports()` groups only by error class plus schema.
- every grouped runtime error receives an unmaterialized-model explanation;
- root-cause groups and ordinary report groups are assembled independently;
- the terminal renderer currently performs application-level grouping.

## Expected behavior

- Build signatures from structured fields: normalized Snowflake code, exact
  resolved relation/identifier, subtype, and final resolution.
- Do not introduce another generic message-regex cause detector.
- Unresolved identical failures may form a symptom group, but that group must
  not claim a root cause or cause-specific remedy.
- Only a shared final resolution may produce a root-cause group.
- The canonical report document owns membership, ordering, representative
  choice, member IDs, and member details.
- Every report ID appears exactly once in the canonical document.
- Terminal rendering performs formatting and verbosity filtering only.
- A missing dedicated template uses `generic.j2`.

## Acceptance criteria

- [ ] Same-schema identifier, privilege, syntax, and missing-object failures are
      not combined merely because they share an error class and schema.
- [ ] Identical unresolved failures may collapse as a symptom group without an
      unevidenced cause or fix.
- [ ] Root-cause groups require a shared structured final resolution.
- [ ] Every report ID occurs once in the canonical report document.
- [ ] Verbose terminal output exposes all member details already present in the
      document; it does not recompute diagnosis.
- [ ] JSON group membership is normative, and terminal group membership is a
      direct projection of it.
- [ ] Missing classifier templates use `generic.j2`.
- [ ] Golden tests cover heterogeneous failures, unresolved repeated symptoms,
      and proven common causes.
- [ ] CHANGELOG updated.

## Test plan

- Unit tests for symptom and root-cause signatures.
- Golden canonical-document tests.
- Terminal projection tests against those same documents.
- No Snowflake account required.

## Scope and files touched

- `grouping.py`
- `root_cause.py`
- canonical report assembly
- group serialization
- `report.j2` and generic fallback behavior

## Traceability

- Parent epic: #4
- Depends on: #54
- Coordinates with: structured-evidence and canonical-document issues
**Type:** Bug / correctness fix
**Labels:** `bug`, `priority: now`
**Parent:** #4
**Dependencies:** #54 semantics
**Release target:** Initial release

<details>
<summary>Replacement body</summary>

```markdown
## Summary

Replace schema-wide grouping with structured root-cause signatures and assemble
the rendered report exactly once.

## Evidence and confidence

- Status: **PROVEN**.
- `group_reports()` groups by error class plus schema.
- Every grouped runtime error receives an unmaterialized-model explanation.
- Root-cause groups and ordinary report groups are rendered independently.

## Expected behavior

- Use structured fields already owned by the diagnosis, such as normalized
  Snowflake code, exact resolved object, subtype, and final resolution.
- Do not invent a generic message-regex signature for unknown failures.
- Do not group reports whose cause is unresolved.
- Render every report once.
- In collapsed normal output, preserve member IDs/counts.
- In verbose output, preserve every member's location, message, and evidence.
- Use `generic.j2` when a dedicated template is absent.

## Acceptance criteria

- [ ] Same-schema invalid identifier, privilege, syntax, and missing-object
      errors remain separate unless their structured signatures match.
- [ ] No group says "not materialized" without a corresponding resolution.
- [ ] Root-cause members do not render again as ordinary reports.
- [ ] Verbose output includes every member's distinct detail.
- [ ] A missing classifier template uses `generic.j2`.
- [ ] Text and JSON identify the same groups and members.
- [ ] Golden output tests cover heterogeneous and homogeneous runs.
- [ ] CHANGELOG updated.

## Test plan

- Unit tests for signature construction.
- Offline e2e golden text and JSON.
- No Snowflake account required.

## Scope and files touched

- `grouping.py`
- `root_cause.py`
- report assembly
- `report.j2` and fallback behavior
- JSON group serialization

## Traceability

- Parent epic: #4
- Depends on: #54
```

</details>

**What changed:** Required structured signatures, preserved verbose member detail, and moved grouping into one report-assembly step.

---

## #57

**Proposed title:** `fix: validate config and profile shapes without silent fallback`
**Type:** Bug / correctness fix
**Labels:** `bug`, `priority: now`
**Parent:** #4
**Dependencies:** None
**Release target:** Initial release

<details>
<summary>Replacement body</summary>

## Summary

Distinguish missing configuration from malformed explicit configuration and
prevent bad config/profile/env input from silently falling through to
auto-discovered credentials or a live connection.

Artifact shape normalization belongs in the separate indexed-artifact-view
issue.

## Evidence and confidence

- Status: **PROVEN**.
- explicit malformed or wrong-shaped config can be treated as absent;
- profile parsing assumes mapping-shaped YAML, mapping-shaped outputs, and a
  string target;
- YAML and I/O failures can be reported misleadingly as "profile not found";
- profile discovery and dotenv loading are duplicated;
- explicit missing-env-file and missing-`python-dotenv` warnings must survive
  consolidation.

## Expected behavior

- Missing optional config and malformed explicit config are distinct outcomes.
- Explicit malformed config is a user-facing error.
- Validate config top-level and nested project/connection mappings.
- Validate profiles top-level, selected profile, outputs, target name, and
  selected Snowflake output mapping.
- A non-string or unhashable target is rejected before membership lookup.
- Consolidate profile and dotenv discovery without changing search order.
- Never fall through from an explicit bad input to another credential source.

## Acceptance criteria

- [ ] Malformed YAML and wrong nested shapes produce clear parse/shape errors.
- [ ] List/dict-valued targets do not raise `TypeError`.
- [ ] Missing outputs and malformed selected outputs are reported.
- [ ] An explicit bad config or env file cannot trigger auto-discovery or a live
      connection.
- [ ] Existing profile and dotenv search order is unchanged.
- [ ] Missing explicit env-file and missing-`python-dotenv` warnings remain.
- [ ] Fully offline unit, robustness, and CLI tests cover each case.
- [ ] CHANGELOG updated.

## Scope and files touched

- `main.py` config boundary
- `discover.py`
- `enrichers/connection.py`
- config/profile/dotenv tests

## Traceability

- Parent epic: #4
- Independent of probe implementation
- Artifact shape validation is tracked by the indexed-artifact-view issue
**Type:** Bug / correctness fix
**Labels:** `bug`, `priority: next`
**Parent:** #4
**Dependencies:** None
**Release target:** Initial release

<details>
<summary>Replacement body</summary>

```markdown
## Summary

Validate every external document at its input boundary and distinguish missing,
malformed, unsupported, and unavailable inputs. Explicit bad inputs must never
silently fall through to auto-discovered credentials or live mode.

## Evidence and confidence

- Status: **PROVEN**.
- `load_json()` accepts valid JSON values that are not objects.
- `DagWalker` assumes manifest mappings.
- profile parsing assumes mapping-shaped YAML and string target names.
- explicit config errors are not consistently reported as such.
- timing lists are read by several downstream functions with inconsistent
  shape guards.
- profile and dotenv discovery are duplicated.

## Expected behavior

Validate before downstream use:

- manifest top-level object, nodes, sources, parent map;
- run-results top-level object, results, timing entries;
- optional catalog collections;
- config top-level mapping and nested project/connection mappings;
- profile, outputs, target, and Snowflake target mapping;
- explicit env/config paths.

Missing optional input and malformed explicit input are different outcomes.

## Acceptance criteria

- [ ] Wrong-shaped valid JSON produces a clear artifact-shape error.
- [ ] Malformed YAML produces a parse error, not "profile not found".
- [ ] Non-string or unhashable profile target is rejected cleanly.
- [ ] An explicit bad config/env file cannot trigger auto-discovery or a live
      connection.
- [ ] Existing profile and dotenv search order is unchanged.
- [ ] Missing `python-dotenv` and missing explicit env-file warnings remain.
- [ ] Malformed timing entries degrade without aborting other reports.
- [ ] Fully offline unit, robustness, and CLI tests cover each case.
- [ ] CHANGELOG updated.

## Scope and files touched

- `main.py`
- `discover.py`
- `enrichers/connection.py`
- artifact validation helpers
- input-boundary tests

## Traceability

- Parent epic: #4
- Independent of live-probe implementation
```

</details>

**What changed:** Corrected the current-behavior description, fixed the module path, and added the artifact/timing shapes downstream code actually assumes.

---

## #58 — retained half after split

**Proposed title:** `fix: make the consumed-path registry and schema gate semantically complete`
**Type:** Bug / correctness fix
**Labels:** `bug`, `compat`, `priority: next`
**Parent:** #48
**Dependencies:** Committed first-party schema cache
**Release target:** Initial release

<details>
<summary>Replacement body</summary>

## Summary

Make the consumed-path registry the executable source of truth for artifact
field aliases and make the schema gate compare field semantics rather than
presence somewhere in a union.

Runtime indexing and artifact-context construction are split into a separate
refactor issue.

## Evidence and confidence

- Status: **PROVEN**.
- `safe.py` manually repeats fallback aliases;
- the registry omits runtime-consumed fields;
- `schema_diff` reduces definition, requiredness, type, and nullability
  information to `present_anywhere()`;
- the compatibility workflow can pass when the committed cache is absent.

## Expected behavior

- Inventory every artifact path consumed by runtime views.
- Derive accessor fallback order from the registry.
- Compare relevant concrete definitions by:
  - presence;
  - requiredness;
  - nullability;
  - type;
  - surviving declared fallback.
- Use structural keys when schema titles/IDs are not stable or unique.
- Fail CI when the committed first-party cache is absent.
- Do not claim real-version validation from schema comparison alone.

## Acceptance criteria

- [ ] Runtime fallback order is sourced from the registry.
- [ ] A guard proves registered aliases cannot drift from accessors.
- [ ] The registry covers every field exposed by the indexed artifact views.
- [ ] Dropped, retyped, newly required, and newly non-nullable fields produce
      the correct gate result.
- [ ] Real first-party schemas exercise the comparison.
- [ ] Missing cache fails CI.
- [ ] Real dbt-version support remains tied to provenance-recorded artifacts.
- [ ] CHANGELOG updated.

## Test plan

- Unit tests using semantic schema breaks.
- Contract tests against the first-party schema cache.
- Later cross-version confirmation from #44.

## Scope and files touched

- `compat/consumed_paths.py`
- `compat/safe.py`
- `compat/path_resolver.py` / `compat/schema_model.py` as required
- `scripts/compat/schema_diff.py`
- schema-contract tests

## Traceability

- Parent epic: #48
- Requires: committed first-party cache
- Supported by, but not blocked on: #44
**Type:** Bug / correctness fix
**Labels:** `bug`, `compat`, `priority: next`
**Parent:** #48
**Dependencies:** First-party schema cache; #44 is supporting evidence, not a hard implementation blocker
**Release target:** Initial release

<details>
<summary>Replacement body</summary>

```markdown
## Summary

Make the consumed-path registry the executable source of truth for runtime
artifact access, build one index per diagnosis, and compare schema semantics
rather than only presence somewhere in a union.

## Evidence and confidence

- Status: **PROVEN** for the runtime and diff gaps.
- `safe.py` manually repeats fallback aliases.
- the registry omits fields read by runtime code;
- result/status lookups are repeatedly rebuilt or linearly scanned;
- `schema_diff` reduces definition/type/nullability/requiredness information to
  `present_anywhere()`.

## Expected behavior

- Inventory every artifact field read at runtime.
- Derive accessor fallback order from the registry.
- Construct one run-results index and one manifest view per diagnosis.
- Pass those views to classifiers, lineage, enrichment, and identity recovery.
- Compare consumed paths on relevant concrete definitions, including:
  - presence;
  - requiredness;
  - nullability;
  - type;
  - declared fallback survival.
- Fail CI if the committed first-party schema cache is absent.

## Acceptance criteria

- [ ] One shared index/view is constructed per diagnosis.
- [ ] No guarded artifact path is read directly outside the view/accessor layer.
- [ ] Accessor fallback order is sourced from the registry.
- [ ] Registry audit covers every runtime read.
- [ ] A dropped, retyped, newly non-nullable, or newly required field is
      classified correctly by the schema gate.
- [ ] Synthetic semantic-break tests fail.
- [ ] Contract tests run against the committed first-party cache.
- [ ] The implementation does not claim support for an unvalidated real dbt
      version.
- [ ] CHANGELOG updated.

## Test plan

- Unit tests for indexes, accessors, and semantic schema comparisons.
- Contract tests against cached first-party schemas.
- #44 later broadens the real-version evidence matrix.

## Scope and files touched

- `compat/consumed_paths.py`
- `compat/safe.py`
- new indexed artifact views
- classifiers, lineage, enrichment, run identity call sites
- `scripts/compat/schema_diff.py`

## Traceability

- Parent epic: #48
- Requires: first-party schema cache
- Supported by, but not blocked on: #44
```

</details>

**What changed:** Removed #12/#44 as artificial hard blockers, required one shared index instead of partial migration, and specified semantic schema comparisons.

---

## #59 — retained half after split

**Proposed title:** `test: enforce offline release gates on Python 3.11 and 3.12`
**Type:** Test / CI / fixtures
**Labels:** `test`, `priority: next`
**Parent:** #48
**Dependencies:** #57, #58, new JSON issue, #52 where its fixture is required
**Release target:** Initial release

<details>
<summary>Replacement body</summary>

````markdown
## Summary

Make all credential-free release checks mandatory on every pull request. Keep
live Snowflake verification in a separate issue with its own credentials,
cost, and environment policy.

## Evidence and confidence

- Status: **PROVEN**.
- CI currently tests only Python 3.12.
- branch protection requires only the `test` context.
- the compatibility job can pass when the schema cache sentinel is absent.
- build, wheel-install, README-render, and Python 3.11 gates are absent.
- `.pre-commit-config.yaml` already exists, but its attribution hook is only a
  commented example.

## What runs with no warehouse

- [ ] Python 3.11 and 3.12 test matrix.
- [ ] `python -m compileall dbt_diagnostics`.
- [ ] unit, contract, robustness, property, and offline e2e tiers.
- [ ] first-party schema cache and semantic compatibility gate.
- [ ] all committed `real_*` artifact contracts.
- [ ] canonical JSON-document golden tests plus terminal-projection parity tests.
- [ ] source distribution and wheel build.
- [ ] installed-wheel `dbt-diagnostics --help` smoke test.
- [ ] README metadata/render validation.
- [ ] package-content audit excluding governance/operator scripts.
- [ ] active pre-commit attribution hook plus existing fast checks.
- [ ] `guards` and `compat-schema-gate` added to required branch checks.

## Build gate

```bash
python -m compileall dbt_diagnostics
python -m build
python -m venv smoke-venv
smoke-venv/bin/pip install dist/*.whl
smoke-venv/bin/dbt-diagnostics --help
````

## Acceptance criteria

* [ ] All offline gates run on every PR on 3.11 and 3.12.
* [ ] Missing first-party schema cache fails CI.
* [ ] Built wheel and sdist install and contain only intended files.
* [ ] Required branch checks match the workflow job names.
* [ ] Fork pull requests require no secrets.
* [ ] No live Snowflake connection is attempted.
* [ ] No diagnostic behavior or JSON contract changes in this issue.

## Constraints / process note

Workflow and branch-protection changes must be committed/applied by the
maintainer because the coding-agent token lacks workflow/admin permissions.

## Scope and files touched

* tests and committed fixtures
* `.pre-commit-config.yaml`
* CI workflow, maintainer-applied
* branch-protection policy JSON, maintainer-applied

## Traceability

* Parent epic: #48
* Live verification is tracked separately.

````

</details>

**What changed:** Split out persistent/live Snowflake CI, recognized that pre-commit configuration already exists, and reduced the retained issue to mandatory offline release gates.

---

# 6. Issues to close, merge, or delete

## #12 — MERGE INTO #44

**Exact closure reason:** #12 and #44 both propose a deterministic real-artifact capture harness. The revised #44 explicitly absorbs #12's current-version fixture audit and failure-scenario capture work while adding the cross-version matrix.

**Ready-to-paste closing comment:**

```markdown
Closing as merged into #44.

#12 and #44 both propose a deterministic dbt-snowflake generator and captured
real artifacts. The revised #44 now owns:

- the current-version audit of synthetic versus captured fixtures;
- representative failure-scenario capture;
- the repeatable generator;
- provenance and `real_*` naming;
- the cross-version extension.

#52 remains the specific healthy catalog capture, and #59 owns mandatory
offline release gates.

No issue history is being deleted.
````

## #28 — MERGE INTO #8

**Exact closure reason:** Duplicate/merged scope. Most simple timestamp attribution already exists; #8 will own the remaining branch-specific and `GETDATE()` work.

**Ready-to-paste closing comment:**

```markdown
Closing as merged into #8.

The current `ContractViolationClassifier` already recognizes
`CURRENT_TIMESTAMP()` and `SYSDATE()`, explains their LTZ behavior, and
recommends an explicit NTZ cast after a real contract failure.

The remaining useful work is branch-specific UNION attribution, `GETDATE()`
parity, structured evidence, and live type confirmation. The replacement body
for #8 now owns those items explicitly.

No issue history is being deleted.
```

## Deletion assessment

**[PROVEN] No open issue should be deleted.** None contains exposed credentials, spam, accidental sensitive data, or content whose continued existence is harmful. GitHub issue deletion is permanent and removes useful history; ordinary completed, duplicate, superseded, and not-planned work should be closed instead. ([GitHub Docs][3])

---

# 7. New issues to create

Tracker searches found no equivalent open or closed issue for edge-preserving lineage, structured evidence resolution, JSON parity, explicit live/artifact-only operation, package baseline/security metadata, or bounded pre-release live verification.

## NEW-1 — lineage correctness

**Title:** `fix: preserve DAG edges and resolve disconnects only on reachable paths`
**Type:** Bug / correctness fix
**Labels:** `bug`, `priority: now`, `blocked`
**Parent:** #4
**Dependencies:** #54 and NEW-7
**Sequence:** After #54/NEW-7, before structured evidence and the canonical report document
**Release target:** Initial release

<details>
<summary>Complete body</summary>

```markdown
## Summary

Replace flat BFS lineage lists as the basis for causal inference with an
edge-preserving graph or explicit root-to-ancestor paths. Resolve disconnects
only across real edges and only among ancestors reachable from the failing
node.

## Evidence and confidence

- Status: **PROVEN**.
- `trace_column_lineage()` returns a flat BFS list.
- `_identify_disconnect()` treats adjacent list entries as parent and child.
- adjacent entries in a branching DAG can be siblings.
- `trace_object_lineage()` searches globally matching manifest relations rather
  than only reachable ancestors.
- manifest declaration can currently outrank an actual run error in display
  status.

## Current wrong behavior

A branching graph can produce a verdict between unrelated nodes. A globally
matching but unreachable relation can be shown as the missing object's lineage.

## Root cause

Display order is being used as graph structure, and column-name presence is
being treated as proven provenance.

## Expected behavior

- Preserve node IDs and directed edges.
- Preserve complete root-to-ancestor paths where a path-specific verdict is
  needed.
- Search only reachable ancestors.
- Record true depth and whether a search was truncated.
- Treat run errors as stronger evidence than manifest declaration.
- Treat column-name matches as candidates until derivation is established.
- Keep a stable ordered projection only for rendering.

## Acceptance criteria

- [ ] A branching-DAG positive test finds the correct disconnect on a real edge.
- [ ] A sibling boundary is never reported.
- [ ] An unreachable same-relation node is ignored.
- [ ] True path depth is preserved.
- [ ] Truncated searches are reported as truncated, not not-found.
- [ ] Execution error outranks manifest-declared status.
- [ ] Object and column lineage use the same graph contract.
- [ ] Offline graph output works without Snowflake.
- [ ] Live status is attached as evidence without changing graph topology.
- [ ] JSON additions are additive; CHANGELOG updated.

## Test plan

- Unit tests for linear, branching, diamond, cyclic, truncated, and unreachable
  graphs.
- Contract tests using real manifest/run-results pairs.
- Golden canonical-document tests plus terminal projection tests.

## Offline behavior

Build and render the graph from artifacts. Unresolved disconnects remain
`unverified`.

## Live behavior and cost tier

Tier A only. Live metadata annotates nodes but does not manufacture edges.

## Scope and files touched

- lineage models
- `tracers/dag_walker.py`
- disconnect resolution
- lineage templates and JSON

## Snowflake / portability impact

Graph structure is warehouse-neutral. Live node annotations remain
Snowflake-specific until the metadata gateway exists.

## Traceability

- Parent epic: #4
- Depends on: #54, #58
- Blocks: structured evidence resolution and the canonical report document
```

</details>

---

## NEW-2 — evidence and final resolution

**Title:** `refactor: separate observations, typed evidence, and final resolution`
**Type:** Refactor
**Labels:** `bug`, `priority: next`, `blocked`
**Parent:** #4
**Dependencies:** #54, #55, #56, NEW-1
**Sequence:** After corrected probes and lineage
**Release target:** Initial release

<details>
<summary>Complete body</summary>

````markdown
## Summary

Replace ordered mutation of `DiagnosticFinding.fix_suggestion` with structured
observations, evidence, hypotheses, confidence, and one final resolution step.

## Evidence and confidence

- Status: **PROVEN**.
- classifiers produce causal prose before live verification;
- live enrichment mutates `fix_suggestion`;
- reconciliation mutates it again;
- write-access enrichment prepends more prose;
- root-cause grouping creates a separate parallel verdict;
- schema-change classification currently treats an upstream declaration as
  proof of physical drift.

## Current structure

```python
classifier -> DiagnosticFinding strings
          -> in-place live mutation
          -> more string mutation
          -> parallel RootCauseGroup verdict
          -> renderer reinterprets reports again
````

## Target structure

```python
observations -> verification requests -> typed evidence
             -> one resolver -> final resolution/confidence
             -> canonical JSON-compatible report document
```

## Compatibility / migration

* Keep existing summary/explanation/fix JSON keys during migration.
* Populate them from the final resolution rather than using them as state.
* Move one diagnosis class at a time.
* Remove the corresponding legacy enricher in the same PR that switches a
  class; never run new and legacy collectors against one finding.

## Acceptance criteria

* [ ] Classifier observations are distinct from live evidence.
* [ ] Every evidence item records source, status, identity, and provenance.
* [ ] Final confidence is calculated once.
* [ ] `fix_suggestion` is not mutated by ordered enrichment passes.
* [ ] A manifest schema declaration remains a hypothesis until live evidence.
* [ ] New and legacy collectors never issue duplicate probes.
* [ ] Final resolutions are written once into the canonical report document.
* [ ] Neither the JSON serializer nor the terminal renderer recomputes a
      resolution.
* [ ] Unknown/failed evidence produces no confirmed wording.
* [ ] Existing diagnosis classes retain or improve golden output.
* [ ] JSON additions are additive; CHANGELOG updated.

## Test plan

* Unit tests for resolution tables and conflicting evidence.
* Probe-count tests proving no duplicate SQL.
* Golden text and JSON for every diagnosis class.
* Robustness tests for missing/failed evidence.

## Offline behavior

Artifact observations resolve to `unverified` hypotheses with confirmation
steps.

## Live behavior and cost tier

Existing Tier-A evidence only. No Tier-B query is introduced.

## Scope and files touched

* domain models
* classifiers
* enrichment orchestration
* root-cause resolution
* canonical report assembly and serializers

## Traceability

* Parent epic: #4
* Depends on: #54, #55, #56, lineage issue
* canonical report assembly and serializers

````

</details>

---

## NEW-3 — canonical report document

**Title:** `refactor: make one canonical report document drive --json and terminal output`
**Type:** Refactor
**Labels:** `bug`, `priority: next`, `blocked`
**Parent:** #4
**Dependencies:** NEW-1, NEW-2, and #56
**Sequence:** After the final domain and grouping models are stable
**Release target:** Initial release

<details>
<summary>Complete body</summary>

## Summary

Produce one versioned, JSON-compatible canonical report document after
classification, evidence collection, final resolution, lineage construction,
and grouping.

`--json` is the normative external contract and serializes that document
directly. Terminal output is a lossy presentation projection of the same
document.

The implementation should pass the in-memory document to the renderer; it
should not serialize a JSON string and parse it back.

## Evidence and confidence

- Status: **PROVEN**.
- current JSON omits live enrichment, full live lineage, and manifest diffs;
- terminal grouping is recomputed inside the renderer;
- templates consume mutable `DiagnosticReport` objects;
- terminal output can therefore expose semantics absent from the machine
  contract;
- matched SQL and other evidence require an explicit redaction policy.

## Target pipeline

```text
artifacts + optional live probes
             |
             v
observations + typed evidence
             |
             v
final resolutions + structured groups
             |
             v
versioned canonical report document
             |
             +--> `--json`: serialize directly
             |
             +--> terminal: format/filter the same document  
**Type:** Bug / correctness fix  
**Labels:** `bug`, `priority: next`, `blocked`  
**Parent:** #4  
**Dependencies:** NEW-1 and NEW-2  
**Sequence:** After the final domain model is stable  
**Release target:** Initial release

<details>
<summary>Complete body</summary>

```markdown
## Summary

Serialize the same final diagnosis used by the terminal renderer, including
live evidence, identity, confidence, graph edges, manifest diffs, and
degradation state.

## Evidence and confidence

- Status: **PROVEN**.
- current JSON omits `EnrichmentData`;
- live lineage fields and relation names are omitted;
- `DiffResult` is omitted;
- text-only grouping is recomputed inside the renderer;
- matched SQL can contain sensitive literals and has no explicit redaction
  policy.

## Expected behavior

The top-level JSON contract gains additive fields for:

- final resolution and confidence;
- evidence items with status, identity, provenance, and query category;
- complete lineage nodes and edges;
- truncation state;
- manifest diff;
- normalized root-cause groups and member details;
- redaction metadata.

Raw matched query text is excluded by default unless an explicit, documented
unsafe/debug option is added.

## Acceptance criteria

- [ ] Text and JSON are generated from the same resolved analysis result.
- [ ] Live evidence and failed/unknown states are serialized.
- [ ] Complete lineage nodes and graph edges are serialized.
- [ ] Manifest diffs are serialized.
- [ ] Root-cause group membership matches terminal output.
- [ ] Sensitive SQL literals and credential-adjacent fields follow a documented
      redaction policy.
- [ ] Golden JSON exists for every diagnosis class and offline/live degradation.
- [ ] Existing keys are not removed or renamed.
- [ ] Increment the additive schema version consistently and update CHANGELOG.

## Test plan

- Offline CLI golden JSON for every diagnosis class.
- Mocked live evidence golden JSON.
- Redaction tests with SQL literals, quoted identifiers, and account-like names.
- Schema compatibility test against the previous JSON shape.

## Offline behavior

All available artifact evidence is serialized; missing live evidence is
explicitly unverified.

## Live behavior and cost tier

Serializes only evidence already collected. It introduces no probe.

## Scope and files touched

- domain serializers
- CLI output assembly
- text report assembly
- JSON golden tests
- output-contract documentation

## Traceability

- Parent epic: #4
- Depends on: lineage issue, structured evidence issue
````

</details>

---

## NEW-4 — explicit live mode and artifact-only operation

**Title:** `fix: make live Snowflake probing explicit and support credential-free artifact-only diagnosis`
**Type:** Bug / correctness fix
**Labels:** `bug`, `priority: now`, `decision-needed`
**Parent:** #4
**Dependencies:** #57; coordinate with #54
**Sequence:** Before release and before live verification
**Release target:** Initial release

<details>
<summary>Complete body</summary>

```markdown
## Summary

Make artifact-only diagnosis the safe default. Do not discover credentials,
load dotenv files, parse profiles, or connect to Snowflake unless the user
explicitly requests live evidence.

Also allow explicit `--run-results` and `--manifest` inputs outside a dbt
project.

## Evidence and confidence

- Status: **PROVEN**.
- live mode is currently enabled unless `--no-live` is passed;
- dotenv/profile discovery can load credentials automatically;
- explicit artifact paths are applied only after a dbt project has been found;
- guessed current-directory model/compiled paths would be misleading in true
  standalone mode.

## Expected behavior

- Default: offline artifact analysis.
- `--live`: explicitly enables profile/env discovery and Snowflake connection.
- `--live` and `--no-live` are mutually exclusive.
- Retain `--no-live` as a compatibility alias while it remains documented.
- Explicit manifest + run-results can execute without `dbt_project.yml`.
- In standalone mode, source-file and compiled-file context is unavailable
  unless explicitly supplied.
- Live standalone operation requires explicit connection/project/profile
  configuration; it never guesses from the current directory.

## Acceptance criteria

- [ ] Default invocation performs no credential discovery or connection.
- [ ] `--live` is required for any Snowflake query.
- [ ] Explicit artifacts work from an empty directory.
- [ ] Standalone output identifies unavailable source/project context honestly.
- [ ] Bad explicit config cannot fall back to discovered credentials.
- [ ] Mutually exclusive live flags are tested.
- [ ] Existing explicit `--no-live` automation continues to work.
- [ ] README and CLI help match behavior.
- [ ] JSON additions are additive; CHANGELOG updated.

## Test plan

- CLI e2e tests from a directory without a dbt project.
- Assertions that connection/profile/dotenv functions are not called by default.
- Explicit live mocked-connection tests.
- Bad-config and missing-context degradation tests.

## Offline behavior

This is the default and requires only the two required artifacts.

## Live behavior and cost tier

Explicit `--live`; existing Tier-A probes only.

## Scope and files touched

- CLI parser and path resolution
- profile/env discovery boundary
- README and tests

## Traceability

- Parent epic: #4
- Depends on: #57
- Coordinates with: #54
```

</details>

---

## NEW-5 — package baseline and security

**Title:** `chore: add license, package metadata, and security policy before the first release`
**Type:** Chore / maintenance
**Labels:** `chore`, `priority: next`, `decision-needed`
**Parent:** Standalone
**Dependencies:** License choice and private security-reporting contact
**Sequence:** Parallel with code hardening; before #33
**Release target:** Initial release

<details>
<summary>Complete body</summary>

```markdown
## Summary

Complete the legal, packaging, and security baseline required for the first
public package release.

## Evidence and confidence

- Status: **PROVEN**.
- no root LICENSE is present in the selected source;
- `pyproject.toml` lacks readme, license, project URLs, maintainers/authors, and
  useful classifiers;
- no SECURITY.md is present;
- README explicitly says not to assume redistribution permission.

## Scope / deliverables

- [ ] Choose and add a root `LICENSE`.
- [ ] Add `readme = "README.md"` to project metadata.
- [ ] Add license metadata matching the committed license.
- [ ] Add repository, issues, changelog, and documentation project URLs.
- [ ] Add maintainer/author metadata approved by the maintainer.
- [ ] Add supported Python and Snowflake/dbt classifiers where accurate.
- [ ] Add `SECURITY.md` with supported versions and a private reporting path.
- [ ] Confirm wheel and sdist metadata with `python -m build`.
- [ ] Add a concise compatibility table to README.

## Acceptance criteria

- [ ] License text and package metadata agree.
- [ ] PyPI-rendered README succeeds.
- [ ] Wheel metadata includes readme, license, project URLs, and Python floor.
- [ ] SECURITY.md names a private vulnerability-reporting channel.
- [ ] No unsupported compatibility claim is added.
- [ ] No diagnostic or JSON behavior changes.

## Constraints / process note

License selection and security contact are maintainer decisions.

## Scope and files touched

- `LICENSE`
- `SECURITY.md`
- `pyproject.toml`
- `README.md`

## Traceability

- Standalone initial-release prerequisite
- Blocks: #33
```

</details>

---

## NEW-6 — split from #59

**Title:** `test: verify live Snowflake evidence semantics before the first release`
**Type:** Test / CI / fixtures
**Labels:** `test`, `tier-a`, `priority: next`, `blocked`
**Parent:** #4
**Dependencies:** #54, #55, #56, NEW-1, NEW-2, NEW-4, #52
**Sequence:** Final correctness verification before publication
**Release target:** Initial release

<details>
<summary>Complete body</summary>

```markdown
## Summary

Run a bounded, credential-gated pre-release Snowflake verification matrix
against disposable objects and roles. This is required release evidence, but it
does not require maintaining an always-on Snowflake instance or running live
tests on fork pull requests.

## Evidence and confidence

- Status: **PROVEN** that mocked cursors cannot establish Snowflake visibility,
  role hierarchy, relation-kind, and query-history behavior.
- The selected source contains no live workflow proving those semantics.

## What requires a real Snowflake account

- failed query-history states and query-id correlation;
- separate diagnostic and dbt run identities;
- visible, hidden, and physically absent relations;
- tables and views;
- quoted and mixed-case identifiers;
- database USAGE, schema USAGE, object privileges, and CREATE privileges;
- direct and inherited role grants;
- session parameter values and levels;
- real connector tuple/exception shapes;
- the healthy catalog capture for #52.

## Environment and cost

- Tier A metadata only.
- Disposable database/schema/roles or a tightly scoped equivalent.
- Least-privileged credentials.
- Protected GitHub environment, manual workflow, or documented maintainer run.
- Never available to untrusted fork pull requests.
- No production data or warehouse-scanning query.

## Acceptance criteria

- [ ] Every corrected probe has a successful positive live case.
- [ ] Unknown, not-visible, failed, and unsupported cases remain distinct.
- [ ] Evidence records the identity that observed it.
- [ ] Query-history failure matching works on a real failed statement.
- [ ] Table/view and quoted-identifier behavior is correct.
- [ ] Cursor and connector behavior match recorded test fixtures.
- [ ] Results and commands are documented without secrets.
- [ ] A green verification record is attached to the release candidate.

## Offline behavior

Recorded, scrubbed connector rows become contract-test inputs for ordinary CI.

## Live behavior and cost tier

Credential-gated Tier A only.

## Scope and files touched

- live tests
- disposable setup/teardown SQL
- protected manual workflow or runbook
- recorded scrubbed rows/fixtures

## Traceability

- Parent epic: #4
- Split from: #59
- Depends on corrected probe, grouping, lineage, evidence, and live-mode work
- Blocks: #33
```

---

## NEW-7 — validated indexed artifact context

**Title:** `refactor: centralize artifact access in validated indexed views`
**Type:** Refactor
**Labels:** `bug`, `compat`, `priority: next`
**Parent:** #48
**Dependencies:** None
**Sequence:** Before lineage and structured-evidence refactors
**Release target:** Initial release

<details>
<summary>Complete body</summary>

## Summary

Construct one validated, indexed artifact context per diagnosis and require
classifiers, lineage, enrichment, diffing, and identity recovery to consume its
views instead of repeatedly reading raw dictionaries.

## Evidence and confidence

- Status: **PROVEN**.
- valid JSON values with the wrong top-level shape can reach downstream code;
- manifest nodes, sources, parent maps, results, and timing shapes are assumed
  in multiple modules;
- result and status lookups are repeatedly scanned or rebuilt;
- `DagWalker`, enrichers, and run-identity recovery maintain separate indexes.

## Current structure

```text
raw manifest/run_results/catalog dictionaries
  -> repeated `.get()` assumptions
  -> repeated linear scans and private status maps
  -> inconsistent malformed-input behavior

</details>

---

# 8. Globally ranked issue backlog

This is the strict total order across every retained and newly proposed item. Epics are ranked first because their tracker edits should precede implementation, not because they are code work.

|    Rank | Priority | Issue                                                                          | Release                |
| ------: | -------- | ------------------------------------------------------------------------------ | ---------------------- |
|       1 | P1       | #4 — reconcile live epic                                                       | Initial tracker action |
|       2 | P1       | #48 — reconcile compatibility epic                                             | Initial tracker action |
|       3 | P0       | #55 — query-history status and cursor lifecycle                                | Initial                |
|       4 | P0       | #54 — evidence-safe relation/grant probes                                      | Initial                |
|       5 | P1       | #57 — input-boundary validation                                                | Initial                |
|       6 | P0       | NEW-4 — explicit live and artifact-only mode                                   | Initial                |
|       7 | P0       | #56 — correct grouping and render once                                         | Initial                |
|       8 | P1       | #58 — central artifact views and semantic schema gate                          | Initial                |
|       9 | P0       | NEW-1 — edge-preserving lineage                                                | Initial                |
|      10 | P1       | NEW-2 — structured evidence and final resolution                               | Initial                |
|      11 | P1       | NEW-3 — JSON parity                                                            | Initial                |
|      12 | P1       | #41 — recognized vs validated dbt versions                                     | Initial                |
|      13 | P1       | #52 — real catalog fixture                                                     | Initial                |
|      14 | P1       | #59 — offline release gates                                                    | Initial                |
|      15 | P1       | NEW-5 — license/package/security baseline                                      | Initial                |
|      16 | P1       | NEW-6 — pre-release live Snowflake verification                                | Initial                |
|      17 | P1       | #33 — TestPyPI and PyPI publication                                            | Initial                |
| **CUT** |          | **Publish only after rank 17 is complete and the release candidate is green.** |                        |
|      18 | P2       | #43 — `sources.json` freshness signal                                          | Post-release           |
|      19 | P2       | #9 — incremental no-op diagnosis                                               | Post-release           |
|      20 | P2       | #8 — UNION branch attribution                                                  | Post-release           |
|      21 | P2       | #10 — static grain consistency                                                 | Post-release           |
|      22 | P2       | #44 — cross-version real-artifact matrix                                       | Post-release           |
|      23 | P2       | #5 — uniqueness grain tracing                                                  | Post-release           |
|      24 | P2       | #6 — orphan-key diagnosis                                                      | Post-release           |
|      25 | P3       | #15 — attested identity spike                                                  | Research               |
|      26 | P3       | #45 — structured log spike                                                     | Research               |
|      27 | P3       | #46 — partial-parse spike                                                      | Research               |
|      28 | P3       | #47 — compatibility watch docs                                                 | Research/docs          |

---

# 9. Dependency graph and release critical path

## Dependency DAG

```text
#55 query-history/cursors
  |
  v
#54 evidence-safe probes --------------------------+
  |                                               |
  +--> #56 grouping/render once                    |
  |                                               |
  +------------------------+                      |
                           v                      |
#58 artifact views -----> NEW-1 lineage graph     |
                           |                      |
                           +----------+-----------+
                                      v
                              NEW-2 evidence/resolution
                                      |
                                      v
                                NEW-3 JSON parity
                                      |
                                      +----------------------+
                                                             |
#57 input validation --> NEW-4 explicit live/artifact-only   |
                                                             |
#52 real catalog --------------------------------------------+
                                                             |
#41 version validation --> #59 offline release gates --------+
                                                             |
NEW-5 license/package/security ------------------------------+
                                                             |
#54 + #55 + #56 + NEW-1 + NEW-2 + NEW-4 + #52              |
                         \                                   |
                          +--> NEW-6 live verification ------+
                                                             |
                                                             v
                                                    #33 publish release
```

Post-release:

```text
#43 sources.json --> #9 incremental diagnosis

NEW-1 + NEW-2 + Tier-B decisions --> #5 uniqueness grain tracing
NEW-1 + NEW-2 + Tier-B decisions --> #6 orphan-key diagnosis

NEW-2 --> #8 UNION attribution

#44 broadens real-version evidence after release

#15 follows #54/#55
#45, #46, #47 are independent research/docs work
```

## Critical path to initial release

**#55 → #54 → NEW-1 → NEW-2 → NEW-3 → NEW-6 → #33**

The following parallel branches must converge before #33:

* #57 → NEW-4.
* #58 → NEW-1 and #59.
* #41 → #59.
* #52 → NEW-6.
* NEW-5 → #33.
* #56 → NEW-2.
* #59 → #33.

## Work that can proceed in parallel

Immediately after tracker cleanup:

* #55, #57, #58, #41, #52, and NEW-5 can proceed independently.
* #56 can begin design work while #54 lands, but final signature semantics must use #54’s evidence contract.
* NEW-4 can begin after #57’s input-boundary contract is settled.
* Offline workflow drafting for #59 can proceed while source fixes land; final golden assertions must wait for NEW-3.
* Disposable Snowflake setup for NEW-6 can be prepared early, but acceptance runs must use the corrected APIs.

## Blocked on real artifacts or credentials

| Issue | Required evidence                                                           |
| ----- | --------------------------------------------------------------------------- |
| #52   | Healthy real `catalog.json` from a Snowflake-backed dbt docs run            |
| NEW-6 | Live Snowflake credentials and disposable objects/roles                     |
| #44   | Multiple dbt-snowflake environments plus Snowflake capture                  |
| #43   | Real `sources.json` warn/error artifacts                                    |
| #9    | Real incremental multi-run artifacts; source freshness for one branch       |
| #8    | Real contract/UNION artifact; live DESCRIBE for strongest confirmation      |
| #5    | Real uniqueness failure plus gated Tier-B access                            |
| #6    | Real relationships failure plus gated Tier-B access                         |
| #15   | Live experiments comparing identity-stamp media                             |
| #58   | Committed first-party schema cache; broad real-version proof later from #44 |
| #59   | Committed fixtures/cache, but no warehouse during ordinary CI               |

## Work blocked on product or architecture decisions

* #5: grain authority, scan ceiling, query cap, depth cap.
* #6: scan ceiling and sampling policy.
* #15: query comment vs marker relation vs no feature.
* NEW-4: audit recommends explicit live opt-in; implementation should record that product decision.
* NEW-5: license and private security contact.
* #33: TestPyPI/PyPI environments and publisher setup.
* #45/#46: go/no-go research outcomes.

---

# 10. GitHub action plan

## Safe tracker actions to perform immediately

1. **Edit #55 first** with the replacement body and add `priority: now`.
2. **Edit #54** with the identity/relation-kind-aware body and add `priority: now`.
3. Edit #57, #56, and #58 with their replacement bodies and recommended labels.
4. Create NEW-1 through NEW-6 in the order presented above, recording their assigned issue numbers.
5. Replace #59 with the offline-only body; add the new live-verification issue as its split counterpart.
6. Replace #41, #33, #5, #6, #8, #9, and #15.
7. **Update #8 before closing #28**, so no useful scope is lost.
8. Close #28 with the merge comment.
9. Close #12 as superseded with the supplied comment.
10. Update #4 and #48 last, substituting the newly assigned issue numbers into their child lists.
11. Create an `initial public release` milestone and attach every P0/P1 implementation issue plus #33.
12. Leave all P2/P3 issues outside that milestone.

## Implementation sequence after tracker cleanup

1. #55.
2. #54 and #57.
3. NEW-4 and #56.
4. #58.
5. NEW-1.
6. NEW-2.
7. NEW-3 and #41.
8. #52 and #59.
9. NEW-5.
10. NEW-6.
11. #33 and the release PR.

## Actions requiring a decision or external artifact

* Choose the license and security-reporting address before NEW-5 can close.
* Confirm explicit live opt-in as the first-release policy before NEW-4 lands.
* Populate and prove the first-party schema cache before #58/#59 close.
* Capture the healthy catalog before #52 closes.
* Run NEW-6 against a disposable Snowflake environment before publication.
* Configure TestPyPI/PyPI Trusted Publishers and protected environments before #33 closes.
* Do not begin #5 or #6 until the Tier-B cost policy is recorded.

---

# 11. Unverified questions

Only the following questions cannot be settled from the supplied source and tracker metadata:

1. **[SPECULATIVE] Is the first-party schema cache actually committed on the authoritative branch?**
   Evidence needed: directory listing and `PROVENANCE.json` under `dbt_diagnostics/fixtures/schemas/`. The selected source shows a sentinel-based workflow but omits the large cache.

2. **[SPECULATIVE] Does `real_schema_change_missing_column_catalog.json` already exist outside the selected snapshot?**
   Evidence needed: the exact fixture file and a non-skipped run of `TestSchemaChangeUsesRealCatalog`.

3. **[SPECULATIVE] Which non-`real_*` fixtures were once guessed rather than deliberately synthetic?**
   Evidence needed: fixture provenance or git history for each non-real fixture. Their filenames alone establish only that they are synthetic, not whether they remain useful.

4. **[SPECULATIVE] Is the complete test suite currently green on Python 3.11 and 3.12?**
   Evidence needed: fresh CI or local logs for the full suite, compileall, build, installed-wheel smoke, and offline e2e tests.

5. **[SPECULATIVE] Are branch-protection policies currently applied, and which checks are required live?**
   Evidence needed: a current branch-protection export or GitHub settings/API result. The repository files express intended policy, not necessarily applied state.

6. **[SPECULATIVE] What do the supported Snowflake connector versions return for all relevant `SHOW`, `DESCRIBE`, and query-history rows and exceptions?**
   Evidence needed: recorded, scrubbed rows from NEW-6’s live matrix.

7. **[SPECULATIVE] How do direct and inherited roles affect the package’s intended access conclusions?**
   Evidence needed: live cases with separate diagnostic/run roles, inherited grants, hidden existing objects, and missing database/schema USAGE.

8. **[SPECULATIVE] Which license and private vulnerability-reporting channel will the maintainer choose?**
   Evidence needed: maintainer decision recorded in NEW-5.

9. **[SPECULATIVE] Is the PyPI project name reserved and are Trusted Publishers configured for TestPyPI and PyPI?**
   Evidence needed: publisher/environment configuration and a successful TestPyPI workflow run.

10. **[SPECULATIVE] What Tier-B cost ceiling and grain authority are acceptable?**
    Evidence needed: explicit decisions on row/sample limits, query count, maximum depth, and trusted grain declarations before #5/#6 begin.

[1]: https://docs.snowflake.com/en/sql-reference/sql/show-tables "https://docs.snowflake.com/en/sql-reference/sql/show-tables"
[2]: https://docs.snowflake.com/pt/sql-reference/functions/query_history "https://docs.snowflake.com/pt/sql-reference/functions/query_history"
[3]: https://docs.github.com/en/issues/tracking-your-work-with-issues/administering-issues/closing-an-issue "https://docs.github.com/en/issues/tracking-your-work-with-issues/administering-issues/closing-an-issue"
