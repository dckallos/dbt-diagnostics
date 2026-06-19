According to a document from June 18, 2026, **OUTPUT_THREE is not safe to implement as written**. I accounted for all 27 numbered changes. 

# Pass 4 — adversarial red-team report

## Executive verdict: the most damaging findings

1. **[PROVEN] Change 2 still permits a false, high-confidence `never_built` verdict.** `SHOW TABLES` is executed through the diagnostic connection and only returns objects visible to that connection’s current role. Its absence result cannot prove physical nonexistence, especially when `access_check()` inspects a different recovered or declared run role. Snowflake explicitly documents that `SHOW TABLES` only returns objects visible to the current role. ([Snowflake Documentation][1])

2. **[PROVEN] Changes 13 and 14 do not produce a working lineage replacement.** Change 13’s shown `dag_walker.py` patch references `LineageGraph` and `LineageEdge` without importing them; that module has no postponed-annotations import, so applying the patch literally raises `NameError` while defining `trace_column_graph()`. More seriously, change 14 requires a downstream step to be “passing,” but the graph root is the failing model with `run_status="error"`. The important root-to-parent edge therefore usually yields no disconnect at all.

3. **[PROVEN] Change 17 intentionally executes the new collector and the legacy enricher back-to-back.** Runtime findings can issue `table_exists`, `DESCRIBE`, and query-history calls twice. Contract parameters can also be queried twice once contract requests are added. That is not a compatibility shim; it is duplicated live work with two partially different data models.

4. **[PROVEN] The plan misses a current live-path defect larger than several proposed changes: query-history matching filters on a nonexistent status.** `query_history.py` uses `WHERE EXECUTION_STATUS = 'FAIL'`. Snowflake documents failure states as `failed_with_error` and `failed_with_incident`; `FAIL` is not listed. The current matcher can therefore return no failed queries even when its time and SQL matching are otherwise correct. ([Snowflake Documentation][2])

5. **[PROVEN] Change 21 is a façade, not a warehouse abstraction.** Its generic protocol imports `ProbeResult` from a Snowflake metadata module, its Snowflake adapter imports private regexes from `RuntimeErrorClassifier`, and no classifier, tracer, connector, enricher, or root-cause path receives or calls the adapter.

6. **[PROVEN] The proposed tests frequently test branch selection or wording, not correctness.** Examples include asserting that a lineage graph contains edges without checking that a real disconnect is found, asserting that timeout parameters were collected without checking that users can see them, and accepting a quoted-role rejection as a security success even though quoted roles are valid Snowflake identifiers.

7. **[PROVEN] The plan does not fix the existing false grouping algorithm.** `grouping.group_reports()` still groups every same-class runtime error in a schema and can label unrelated identifier, syntax, privilege, and missing-source errors as “models not yet materialized.”

8. **[PROVEN] No package test suite was executable from the supplied materials.** Only the three review files were mounted; package source was inline and fixtures were deliberately omitted. I did execute isolated checks confirming the Jinja include-list fallback under Jinja 3.1.6, SQLGlot behavior under 27.29.0, and Python’s annotation evaluation behavior. Those checks do not substitute for running this package against its real artifacts.

The high-level conclusion of OUTPUT_TWO—refactor specific subsystems rather than rewrite the package—still holds, but OUTPUT_THREE overstates how close its patches are to implementation-ready code.  The broader defects identified in OUTPUT_ONE also remain materially relevant. 

---

# 1. OUTPUT_THREE, change by change

## Wave 1

### 1. Preserve live probe failure as unknown — **rewrite**

**[PROVEN]** The “before” excerpt accurately reflects `_enrich_lineage_trail()`: a falsey `None` from `table_exists()` currently becomes `live_status="missing"`.

**[PROVEN]** The proposed `unknown` state is directionally correct and compiles, but the new `_is_failing()` begins with:

```python
if step.live_status == "unknown":
    return False
```

That masks an independent `run_status=="error"` or `manifest_status=="missing"`. The corresponding `status_emoji` and `status_text` similarly display unknown before checking run failure. This contradicts change 5’s promise that execution failure outranks weaker signals.

**[PROVEN]** `describe_table()` returns `[]` both for a genuinely empty result and for validation, permission, cursor, or execution failure. In the proposed code, an empty result leaves the relation as `exists` without establishing whether the target column is present. Column state therefore remains ambiguous but is not marked unknown.

**[PROVEN]** The proposed test only covers `table_exists() is None`. It would not catch either `unknown + run_status=error` or `describe_table() == []`. It is insufficient.

**Required correction:** model each evidence dimension separately. A failed existence probe must not suppress a known execution failure, and a failed column probe must have its own unknown state.

---

### 2. Make grant probe failure explicit — **reject as written**

**[PROVEN]** The “before” excerpt matches `check_role_grants()`: exceptions currently produce an ordinary empty negative-looking result.

**[PROVEN]** The grant wrapper’s `query_succeeded` field and cursor cleanup are improvements.

**[PROVEN]** The `exists is None` patch contains a literal `...`; it is not a complete implementable patch.

**[PROVEN]** The central verdict remains logically invalid:

```python
SHOW TABLES returned no rows
+ SHOW GRANTS succeeded
+ no grants_found
= object does not exist, high confidence
```

`SHOW TABLES` is visibility-filtered for the diagnostic session’s current role, while `SHOW GRANTS` may inspect a recovered, declared, or session role. Those may be different identities. A role-filtered empty listing is not physical nonexistence. ([Snowflake Documentation][1])

**[PROVEN]** Conversely, `grants_found` is not proof that an object exists and was denied. It can include schema-level grants, stale or unrelated substring matches, or grants on another object whose name merely contains the target.

**[SPECULATIVE]** Effective access may differ from the direct rows inspected because of role hierarchy and other access paths. The patch has no effective-privilege model, so absence of a matching direct row should remain unverified.

**[PROVEN]** The proposed test exercises only the newly added query-failure branch. It would pass while the false high-confidence `never_built` branch remains. It is test theater.

**Required correction:** the probe result must record the identity under which existence was tested. Never emit confirmed physical absence from a visibility-limited `SHOW` result unless the probing identity has a capability that makes absence authoritative.

---

### 3. Split database/schema usage and validate roles — **rewrite**

**[PROVEN]** The “before” excerpt correctly identifies that one `has_usage` boolean combines database and schema USAGE.

**[PROVEN]** Splitting `has_database_usage` and `has_schema_usage` fixes that particular defect, and preserving the old `has_usage` key is a reasonable transition.

**[PROVEN]** The role validator rejects every quoted role. Snowflake supports quoted identifiers and requires exact quoting for case-sensitive or special-character names. Rejecting them is a functional regression, not a complete security fix. ([Snowflake Documentation][3])

**[PROVEN]** `schema_fq` remains split and interpolated without a real identifier parser. The patch therefore secures one interpolated identifier while leaving the other unresolved.

**[SPECULATIVE]** Direct `SHOW GRANTS TO ROLE` rows may not capture every effective privilege available through role relationships. Until that is tested with a live hierarchy, `can_create=False` should mean “no matching direct evidence found,” not “cannot create.”

**[PROVEN]** The proposed security test enshrines rejection of quoted identifiers and does not test valid quoted roles, effective access, query failure, cursor-close failure, or malformed schema names.

---

### 4. Defensive query-history timing access — **accept as a narrow fix**

**[PROVEN]** The before excerpt exactly matches `_enrich_runtime_error()`.

**[PROVEN]** The replacement safely handles a non-list `timing`, non-dict entries, and missing `name`; it compiles and preserves conforming input behavior.

**[PROVEN]** The test is useful for this specific regression.

**[PROVEN]** It does not make the entire lookup robust: `_find_result()` can still call `.get()` on non-dict entries until later changes, and `find_matching_query()` still filters on the wrong Snowflake execution status.

---

### 5. Execution failure must outrank manifest declaration — **rewrite**

**[PROVEN]** The before excerpt accurately shows the status-ordering defect.

**[PROVEN]** `_is_passing()` improves the precedence of `run_status=="error"` over `manifest_status=="declared"`.

**[PROVEN]** `_is_failing()` immediately returns false for `live_status=="unknown"` before checking `run_status=="error"`. An unknown live probe therefore outranks and hides a confirmed execution failure.

**[PROVEN]** Change 1’s display properties have the same contradiction: `unknown` is rendered before checking run error.

**[PROVEN]** The proposed test covers `declared + error` but not `unknown + error`, the combination introduced by change 1. It would certify a broken implementation.

---

### 6. Skip disconnect inference for generic data trails — **accept as a tactical guard**

**[PROVEN]** The before excerpt matches the unconditional `_identify_disconnect()` call.

**[PROVEN]** The guard prevents today’s data-error findings—which do not set target object or identifier fields—from receiving an absence-oriented disconnect verdict.

**[PROVEN]** It relies on overloaded target fields as an implicit capability flag. A future data finding that legitimately sets either field would silently re-enable the wrong algorithm.

**[PROVEN]** The proposed test is sufficient for the present data-error shape, but not for the eventual structured evidence model.

---

### 7. Downgrade schema-drift wording — **accept only as confidence calibration**

**[PROVEN]** The before text overclaims physical schema alteration from manifest evidence alone.

**[PROVEN]** The proposed wording is more honest and compiles.

**[PROVEN]** The classifier still returns `error_class="schema_change_error"` solely because `find_column_origin()` finds the same column name in an ancestor’s manifest declaration or compiled alias. No live relation/column evidence is required.

**[PROVEN]** A wrong alias, quoted-case mismatch, stale manifest, or unrelated projection can still be categorized as schema drift. The patch changes prose, not classification semantics.

**[PROVEN]** Testing that the explanation no longer contains the words “This means” is wording-oriented and does not establish diagnostic correctness.

---

### 8. Serialize enrichment, lineage, and diff — **extend before implementation**

**[PROVEN]** The before excerpt correctly identifies missing JSON fields.

**[PROVEN]** The proposed fields are additive and compile.

**[PROVEN]** By the end of the plan, JSON would still omit the newly proposed `lineage_graph`, graph edges, `enrichment_request`, `evidence`, and `resolution`. Change 8 therefore becomes obsolete before wave 2 finishes.

**[PROVEN]** Omitting `matched_query_text` by default is defensible because SQL may contain literals, but that needs a documented redaction/opt-in policy rather than an isolated comment.

**[PROVEN]** The test should validate the complete CLI JSON contract and schema version, including null/unknown probe states. Merely checking that two keys exist is too weak.

---

### 9. Jinja generic fallback — **accept**

**[PROVEN]** The before include appears at three dynamic include sites in `report.j2`.

**[PROVEN]** Jinja supports a list of candidate templates and chooses the first that exists. I verified the proposed syntax under Jinja 3.1.6, which is inside the package’s declared dependency range.

**[PROVEN]** Updating every dynamic include site, as the plan states, is necessary.

**[PROVEN]** The proposed rendering test is sufficient.

---

### 10. Validate JSON and YAML shapes — **rewrite**

**[PROVEN]** The before excerpts match `load_json()` and `parse_profile()`.

**[PROVEN]** Requiring a top-level JSON object is correct for the two required dbt artifacts.

**[PROVEN]** A malformed profile can still crash:

```python
target = target_name or profile.get("target", "dev")
if target not in outputs:
```

If `profile["target"]` is a list or dictionary and no CLI target was supplied, membership lookup raises `TypeError`.

**[PROVEN]** `_load_config()` silently converts unreadable, malformed, or wrong-shaped explicit configuration into “no config.” The CLI may then fall through to auto-detected defaults and potentially a live connection. An explicit bad configuration should be reported, not silently ignored.

**[PROVEN]** `parse_profile()` similarly erases YAML parse and I/O errors, causing `open_connection()` to report that the profile was not found. That is misleading diagnosis.

**[PROVEN]** The proposed tests cover only a list-valued JSON artifact and an empty profile file. They miss malformed YAML, wrong nested shapes, unhashable target values, and explicit-config fallback.

---

## Wave 2

### 11. Add `RunResultsIndex` — **accept with caveats**

**[PROVEN]** The before example is one real repeated linear scan, though it is not the only one.

**[PROVEN]** The shown module compiles, handles malformed result entries, and provides useful indexes.

**[PROVEN]** Duplicate `unique_id` or `query_id` entries overwrite silently. That may be acceptable, but the desired policy is unspecified.

**[PROVEN]** `RunResultView.raw` is typed as a general `Mapping`, while `safe.node_compiled_code()` accepts only actual dictionaries. Runtime construction currently passes dictionaries, so this is a misleading rather than immediately broken type.

**[PROVEN]** The proposed unit tests are adequate for the new class itself.

---

### 12. Migrate lookups to `RunResultsIndex` — **rewrite**

**[PROVEN]** The before pattern appears in both runtime and data classifiers.

**[PROVEN]** The title overstates the migration. `enrich._find_result()` remains a linear scan, `DagWalker` still builds its own status map, and `run_identity._end_time_for()` reconstructs a fresh index each time instead of using the one already stored in context.

**[PROVEN]** The dynamic import plus blanket `except Exception` in `_end_time_for()` can hide programming defects introduced by the new view module.

**[PROVEN]** A test showing that malformed entries do not raise would pass through the legacy fallback and would not prove that the central index is used.

**Required correction:** construct one index per diagnosis and pass it to every reader, including enrichment and run-identity recovery.

---

### 13. Add edge-preserving lineage graph — **reject as written**

**[PROVEN]** The before excerpt reflects the column-lineage call pattern.

**[PROVEN]** The shown `dag_walker.py` patch references `LineageGraph` and `LineageEdge` but does not add imports. `dag_walker.py` lacks `from __future__ import annotations`; applying the shown patch literally fails while defining `trace_column_graph()`. Python 3.11 does not make postponed annotation evaluation mandatory. ([Python documentation][4])

**[PROVEN]** The plan says “classifiers assigning lineage” without enumerating all call sites. At minimum, both runtime invalid-identifier handling and schema-change handling must set `lineage_graph`.

**[PROVEN]** `trace_column_lineage()` changes existing display order from BFS insertion order to sorted `(depth, node_id)` order. That may be desirable, but it is a user-visible change and needs golden-output updates.

**[PROVEN]** Object lineage remains list-only. Thus the most important missing-object path still uses the old non-edge-preserving representation.

**[PROVEN]** JSON serialization and templates do not expose graph edges.

**[PROVEN]** The proposed edge-list test would not catch missing imports, forgotten call sites, changed output order, object-lineage omission, or verdict failure.

---

### 14. Use graph edges for disconnect inference — **reject**

**[PROVEN]** The before excerpt is accurate.

**[PROVEN]** The edge direction is sensible: `upstream_id -> downstream_id`.

**[PROVEN]** The candidate condition is usually impossible for the most important edge. The downstream root is populated from the failing run result, so after change 5 it is not “passing.” A missing or no-column parent connected to a failed root therefore produces no candidate.

**[PROVEN]** If a graph exists but has no candidate, the function returns immediately and does not produce even the old low-confidence fallback.

**[PROVEN]** Because object lineage was not migrated in change 13, object-not-found findings remain on the legacy adjacent-list algorithm.

**[PROVEN]** The sibling-order test can pass simply because the new algorithm produces no verdict anywhere. It must also assert a correct verdict on a known true edge and no verdict on siblings.

---

### 15. Restrict object lineage to reachable ancestors — **rewrite**

**[PROVEN]** The before excerpt correctly shows a global manifest search.

**[PROVEN]** Restricting candidates to ancestors fixes the global false-match defect.

**[PROVEN]** `_reachable_upstream_ids()` returns a set. If multiple reachable nodes share a physical relation, selection becomes nondeterministic.

**[PROVEN]** The actual path and depth are discarded. `trace_object_lineage()` will still append only the root and matched node and label the match as depth 1 even when it is several edges away.

**[PROVEN]** The hard-coded depth limit of 20 has no truncation indicator. “Not found” can therefore mean “beyond the hidden limit.”

**[PROVEN]** The proposed test catches only the unrelated-global-node case, not nondeterminism, true depth, intervening path nodes, or truncation.

---

### 16. Add enrichment requests, evidence, and resolution — **rewrite**

**[PROVEN]** The before fields accurately show the current partial enrichment contract.

**[PROVEN]** The new dataclasses compile and are additive.

**[PROVEN]** Only timeout and object-not-found examples are updated. The plan does not enumerate requests for contract parameters and parameter level, invalid-identifier source descriptions, privilege checks, lineage checks, write-access checks, or query identity.

**[PROVEN]** `FindingResolution` is introduced but no later change computes or renders it.

**[PROVEN]** `Evidence.value: Any` permits arbitrary connector rows and dictionaries in a supposedly stable JSON API. Evidence needs typed payloads or an explicit versioned serialization contract.

**[PROVEN]** The proposed test proves only that one classifier copied one parameter name into a new field. It does not validate evidence collection or final output.

---

### 17. Introduce class-agnostic evidence collection — **reject until parity is specified**

**[PROVEN]** The before class-tag dispatch exists.

**[PROVEN]** The shown collector compiles.

**[PROVEN]** `_try_enrich()` then executes both:

```python
collector.collect(reports)
enrich_reports(conn, reports, run_results)
```

This duplicates existence, description, parameter, and query-history probes for overlapping findings.

**[PROVEN]** The two paths do not have feature parity. The collector does not retrieve `TIMESTAMP_TYPE_MAPPING` level, does not reproduce contract reconciliation, does not infer an invalid identifier’s source relation, does not enrich lineage steps, and does not perform write-access checks.

**[PROVEN]** Timeout parameters may be collected, but `timeout_error.j2` never displays `finding.enrichment`. They become visible only if the JSON change is also present.

**[PROVEN]** Its query-history call is still broken by `EXECUTION_STATUS = 'FAIL'`.

**[PROVEN]** It reintroduces a linear `_find_result()` despite the immediately preceding index work.

**[PROVEN]** The proposed test checks collection for timeout but would not catch doubled queries, missing terminal output, parity loss, or conflicting evidence.

**Required correction:** create a probe-count/parity matrix first. Switch one finding capability at a time and remove the equivalent legacy path in the same change.

---

### 18. Stop rendering root-cause members twice — **rewrite**

**[PROVEN]** The before renderer call causes root-cause members to remain eligible for ordinary grouping.

**[PROVEN]** Excluding collapsed IDs removes duplicate presentation.

**[PROVEN]** It can also hide member-specific findings entirely. The root-cause template renders only `representative_finding`; even verbose output does not iterate all excluded member reports.

**[PROVEN]** The independent false grouping algorithm remains unchanged for reports not covered by a root-cause group.

**[PROVEN]** A one-report test is insufficient. Tests need multiple members with distinct locations, messages, and findings in both normal and verbose modes.

---

## Wave 3

### 19. Typed metadata gateway — **reject as an implementation, retain the concept**

**[PROVEN]** The before interface is accurate.

**[PROVEN]** `ProbeResult` is an improvement over `Optional[bool]`.

**[PROVEN]** The compatibility wrapper creates a new `SnowflakeMetadata` for every call, so `_exists_cache` is discarded immediately. The advertised cache never helps legacy callers.

**[PROVEN]** Exact post-filtering on `row[1]` addresses `_` and `%` wildcard false positives. Snowflake documents both the wildcard semantics and `name` as the second output column. ([Snowflake Documentation][1])

**[PROVEN]** It still uses `SHOW TABLES`, so generic `relation_exists()` reports false for views and other relation kinds.

**[PROVEN]** It still executes under the diagnostic role and therefore cannot distinguish hidden from nonexistent objects.

**[PROVEN]** Uppercasing the returned name destroys quoted, case-sensitive identifier semantics.

**[PROVEN]** `_validate_fq_name()` and `.split(".")` still cannot parse quoted identifiers containing periods. Snowflake explicitly permits names such as `"My.DB"."My.Schema"."Table.1"`. ([Snowflake Documentation][3])

**[PROVEN]** `describe_relation()` retains the old `[]`-on-any-failure ambiguity.

**[PROVEN]** Fake-row unit tests cannot establish visibility, quoted-name, or relation-kind correctness. Live contract tests are necessary.

---

### 20. Identifier/role parser — **reject as incomplete**

**[PROVEN]** The before snippets identify real interpolation sites.

**[PROVEN]** The proposed relation parser is never wired into the shown `schema_inspector.py` code despite that file being listed in the location.

**[PROVEN]** It duplicates existing identifier regexes rather than replacing them.

**[PROVEN]** `RelationName.fqn` concatenates raw parts without warehouse-specific quoting or preservation of quoted/unquoted state.

**[PROVEN]** It deliberately rejects valid quoted roles and quoted relation segments. That may be a temporary compatibility limitation, but the proposed test incorrectly treats it as the completed security behavior.

**[PROVEN]** It does not escape the string literal passed to `LIKE`.

---

### 21. `WarehouseAdapter` shell — **defer and redesign**

**[PROVEN]** The protocol compiles in isolation once its new package is importable.

**[PROVEN]** No call site constructs, injects, or invokes a `WarehouseAdapter`. The package remains entirely Snowflake-driven after this change.

**[PROVEN]** The supposedly generic `adapters.base` imports `ProbeResult` from `enrichers.metadata`, a Snowflake implementation module.

**[PROVEN]** `SnowflakeAdapter` imports private regexes from `classifiers.runtime_error`. This points the dependency from adapter infrastructure back into application diagnosis.

**[SPECULATIVE]** Once classifiers are changed to import the adapter, that reversed dependency is likely to become a real import cycle.

**[PROVEN]** `normalize_error()` does not populate `error_code` and ignores code-only variants that the current classifier recognizes.

**[PROVEN]** The protocol omits profile parsing, connection creation, query-history lookup, parameter lookup, grants, write access, run-role recovery, relation-kind discovery, identifier quoting, type semantics, and platform-specific fixes.

**[PROVEN]** A unit test that normalizes three hand-written messages establishes only a regex wrapper, not portability.

---

## Wave 4

### 22. Complete the consumed-path registry and strengthen schema diff — **rewrite**

**[PROVEN]** Several proposed registry additions correspond to real reads. The first-party run-results v6 schema confirms `compiled_code`, `failures`, and timing `name`/`completed_at`; `compiled_code` is nullable but required as a key in v6. ([dbt JSON Schemas][5])

**[PROVEN]** `_present_on_same_defs()` is not actually integrated; “use it before `present_anywhere()`” is an instruction, not a complete patch.

**[PROVEN]** It compares `Presence.defn`, which is only a best-effort title, `$id`, or type label. Labels can collide or change between schema versions even when semantic node kinds do not.

**[SPECULATIVE]** Whether first-party dbt schemas currently contain enough stable unique titles for this set comparison to work must be checked against the committed schema cache.

**[PROVEN]** The new comparison still ignores the type, nullability, and requiredness information already captured by `Presence`.

**[PROVEN]** `safe.py` remains manually hard-coded and does not derive its fallback order from `REGISTRY`; the claimed executable single source of truth is still not true.

**[PROVEN]** A synthetic schema with clean unique titles will not expose title collision or real `allOf`/union behavior. The real first-party schema cache and real artifacts are prerequisites.

---

### 23. Remove dead `_is_lagging()` code — **accept**

**[PROVEN]** The second half of `_is_lagging()` is unreachable in the supplied snapshot.

**[PROVEN]** The replacement is simpler and uses the already-present `_to_aware_utc()` helper.

**[PROVEN]** The proposed naive/aware and malformed-time tests are appropriate.

**[PROVEN]** Closed issue #50 already tracks the datetime comparison repair, so this should be treated as residual cleanup rather than a new capability.

---

### 24. Centralize provenance constants — **accept**

**[PROVEN]** The duplicated constants and “must stay in sync” comment exist.

**[PROVEN]** Moving them to a dependency-light module preserves imported names because both existing modules re-import the constants.

**[PROVEN]** The proposed regression test is adequate.

---

### 25. Consolidate discovery and dotenv loading — **rewrite**

**[PROVEN]** Profile discovery is duplicated, and forwarding to `discover.find_profiles_yml()` preserves that search order.

**[PROVEN]** The proposed shared dotenv helper changes behavior. The current connection helper always checks `Path.cwd() / ".env"` even when `project_dir` is `None`; the replacement checks the current directory only inside `if project_dir:`.

**[PROVEN]** It also removes current warnings for an explicit missing `--env-file` and for a missing `python-dotenv` installation.

**[PROVEN]** The proposed test covers only profiles search priority and would miss both dotenv regressions.

---

### 26. Diagnose explicit artifacts without a project — **rewrite**

**[PROVEN]** The before ordering forces project discovery before artifact overrides.

**[PROVEN]** The patch makes offline explicit-artifact diagnosis possible.

**[PROVEN]** Live mode remains on by default. With no project, the patch assigns `project_dir=Path.cwd()`, later defaults the profile to `default` and target to `dev`, searches current/parent `.env` files and `~/.dbt/profiles.yml`, and may initiate an unintended connection. The proposed test includes `--no-live` and therefore misses this risk.

**[PROVEN]** `models_dir` and `compiled_dir` are guessed from the current directory, which may be unrelated to the supplied artifacts. That must be surfaced as unavailable context rather than silently treated as project paths.

---

### 27. Defer the live-default decision — **not an implementation change**

**[PROVEN]** This item explicitly defers a product decision, so OUTPUT_THREE contains 26 implementation proposals and one unresolved decision, not 27 implementable changes.

**[PROVEN]** Switching the default conflicts with the current `main.py` documentation and CLI description, and requires coordinated docs and tests.

**[PROVEN]** The proposed parser allows both `--live` and `--no-live` simultaneously rather than using a mutually exclusive group.

**[PROVEN]** The issue belongs under the live-verification epic because that epic treats live database evidence as the project’s central thesis.

---

## Material changes missing from OUTPUT_THREE

* **[PROVEN] Fix `EXECUTION_STATUS = 'FAIL'`.** Use Snowflake’s documented failed states or filter on non-null `ERROR_CODE`/`ERROR_MESSAGE` as appropriate. ([Snowflake Documentation][2])
* **[PROVEN] Replace schema-only report grouping with normalized root-cause signatures.**
* **[PROVEN] Add a top-level degradation boundary around `enrich_reports()` and root-cause probing.** `_try_enrich()` currently falls back only on connection failure; unexpected enrichment exceptions abort the CLI.
* **[PROVEN] Close the cursor in `get_current_role()`, and protect cursor creation and closure consistently in every wrapper.**
* **[PROVEN] Align the identity used for object visibility, grant inspection, and write-access verdicts.**
* **[PROVEN] Model relation kinds.** `SHOW TABLES` is not a generic existence probe for views or other objects.
* **[PROVEN] Validate `manifest["nodes"]`, `sources`, and `parent_map` shapes before constructing `DagWalker`.
* **[PROVEN] Render and serialize structured evidence/resolution rather than continuing to mutate `fix_suggestion`.
* **[PROVEN] Inject the adapter into classifier context, tracers, enrichment, and root-cause resolution; merely defining it changes nothing.
* **[PROVEN] Add semantic tests that prove a correct positive diagnosis, not merely absence of the previous false one.**

---

# 2. Claims left unverified by the absence of real fixtures and external checks

## What external sources settle

| Claim                                                                                  | Red-team result                                                                                                                                                                                                                                                                                    |
| -------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `run_results.json` can carry `compiled_code`                                           | **[PROVEN]** In run-results schema v6, `compiled_code` is a required key whose value may be string or null. Timing `name` is required; start and completion times are nullable. ([dbt JSON Schemas][5])                                                                                            |
| `adapter_response.query_id` and `rows_affected` are guaranteed                         | **[SPECULATIVE]** The first-party schema defines `adapter_response` only as an arbitrary object. It does not guarantee either Snowflake key. Real dbt-snowflake artifacts from success, compilation failure, execution failure, test failure, and cancellation are needed. ([dbt JSON Schemas][5]) |
| Catalog columns have `name` and `type`                                                 | **[PROVEN]** Catalog v1 defines node/source column entries with required `type`, `index`, and `name`. ([dbt JSON Schemas][6])                                                                                                                                                                      |
| Catalog evidence is validated against a real healthy/broken pair                       | **[PROVEN]** It is not yet established by the issue tracker: open issue #52 exists specifically to capture the missing real catalog fixture and activate skipped contract tests.                                                                                                                   |
| `DESCRIBE TABLE` tuple positions 0 and 1 are name/type                                 | **[PROVEN]** Snowflake documents output beginning with `name`, `type`, `kind`, `null?`, and so on. The current accesses are correct. ([Snowflake Documentation][7])                                                                                                                                |
| `SHOW GRANTS TO ROLE` tuple positions 1, 2, 3 are privilege/granted_on/name            | **[PROVEN]** The documented output starts `created_on`, `privilege`, `granted_on`, `name`. Those indices are correct. ([Snowflake Documentation][8])                                                                                                                                               |
| `SHOW PARAMETERS` has six columns ending in `type`                                     | **[PROVEN]** The code comment is wrong or outdated. The documented output shown is `key`, `value`, `default`, `level`, `description`. The code’s row indices 0–3 remain correct. ([Snowflake Documentation][9])                                                                                    |
| `SHOW TABLES LIKE` is an exact existence test                                          | **[PROVEN]** It is not. `LIKE` supports `%` and `_`, and output is restricted to objects visible to the current role. Post-filtering exact `name` helps wildcard ambiguity but not visibility or relation-kind ambiguity. ([Snowflake Documentation][1])                                           |
| Query history is seven-day, near-current, and role/user scoped                         | **[PROVEN]** The Information Schema table function is limited to the last seven days and has explicit visibility rules. It exposes `role_name`, `warehouse_name`, `error_code`, and `error_message`. ([Snowflake Documentation][2])                                                                |
| Failed query status is `FAIL`                                                          | **[PROVEN]** It is wrong. Documented statuses include `failed_with_error` and `failed_with_incident`. ([Snowflake Documentation][2])                                                                                                                                                               |
| Codes 002003, 000904, 003001, and 001003 are Snowflake patterns                        | **[PROVEN]** Official examples show these codes for missing/unauthorized objects, invalid identifiers, insufficient privileges, and syntax/compilation errors. ([Snowflake Documentation][10])                                                                                                     |
| Exact Snowflake message wrappers are stable                                            | **[PROVEN]** They are not uniform across contexts. Official examples show 002003 with different SQLSTATE values and stored-procedure exception wrappers, and 000904 can report unusual line/position values. ([Snowflake Documentation][11])                                                       |
| Current identifier splitting handles Snowflake names                                   | **[PROVEN]** It does not handle quoted identifiers containing periods or case-sensitive segments. Snowflake documents exactly those forms. ([Snowflake Documentation][3])                                                                                                                          |
| SQLGlot qualification expands `SELECT *` with schema                                   | **[PROVEN]** I verified that behavior under installed SQLGlot 27.29.0, inside the package’s declared `>=26,<28` range. SQLGlot’s public API also exposes schema and lineage facilities. ([SQLGlot][12])                                                                                            |
| SQLGlot behavior is uniform across every allowed 26.x–27.x version and complex dbt SQL | **[SPECULATIVE]** One installed-version probe is not a compatibility matrix. Tests are needed for both range boundaries and real compiled SQL containing CTEs, unions, stars, lateral constructs, quoted names, and macros already rendered by dbt.                                                |
| The Jinja list-style fallback works                                                    | **[PROVEN]** I executed the exact include-list form under Jinja 3.1.6; it selected the fallback template.                                                                                                                                                                                          |
| Change 13’s unresolved annotation is harmless                                          | **[PROVEN]** It is not. The supplied module has no postponed-annotations import, and Python 3.11 still treats that future feature as optional rather than mandatory. ([Python documentation][4])                                                                                                   |

## Real artifacts still required

* **[SPECULATIVE]** The exact presence of `query_id` and `rows_affected` across dbt-snowflake versions and failure categories remains unknown. Settle it with versioned `real_*_run_results.json` captures.
* **[SPECULATIVE]** Whether failed run-results consistently include usable `compiled_code`, and whether it is bare SELECT SQL or adapter-wrapped DDL, remains unverified. Capture real object-missing, invalid-identifier, permission, timeout, and test failures.
* **[SPECULATIVE]** The classifier regex coverage remains unverified across connector/dbt wrappers. A real error corpus must include all supported code families and quoted/case-sensitive names.
* **[SPECULATIVE]** Actual cursor tuple types and null behavior should be recorded from the supported Snowflake connector versions even where documentation establishes column order.
* **[SPECULATIVE]** Role visibility and grant conclusions need fixtures using different diagnostic and execution roles, inherited roles, no-USAGE schemas, and hidden existing objects.
* **[SPECULATIVE]** Cross-version compatibility is not established until open issues #12 and #44 produce real artifacts across the intended dbt versions.
* **[SPECULATIVE]** Catalog drift behavior requires the healthy catalog capture tracked by #52; synthetic catalog entries cannot establish reality.

---

# 3. Issue tracking

## Existing tracker inventory

**[PROVEN]** The broad connector queries returned issues. Two narrower searches—for lineage/disconnect grouping and for JSON enrichment/diff output—returned zero results. Therefore I cannot claim that a dedicated lineage-graph or JSON-parity issue already exists.

### Open epics

* **[PROVEN] #4 — Live Verification Engine.** This is the umbrella for live probes, root-cause grouping, role recovery, and the live-vs-offline evidence policy.
* **[PROVEN] #48 — Cross-Version Artifact Compatibility.** This is the umbrella for consumed-path handling, first-party schemas, safe accessors, and real cross-version artifacts.

### Other open issues returned by the connector

* **[PROVEN] Fixtures/compatibility:** #52 real catalog fixture; #47 compatibility watch file; #46 partial-parse spike; #45 structured log/event spike; #44 cross-version real-artifact matrix; #43 sources.json consumption; #41 newer-than-validated dbt version note; #12 replacement of guessed fixtures with real dbt-run goldens.
* **[PROVEN] Live/product work:** #28 timestamp type-hazard enricher; #8 UNION attribution; #10 grain-consistency cross-check; #15 attested run identity; #5 upstream grain tracing; #6 orphan-FK detection; #9 incremental low-row differential diagnosis.
* **[PROVEN] Release:** #33 automated PyPI trusted publishing.

### Recently closed issues returned by the connector

**[PROVEN]** The relevant recently closed set includes: #42 catalog consumption, #40 first-party schema cache/CI gate, #39 artifact version skew, #38 malformed read-path hardening, #37 safe-accessor wiring, #50 datetime comparison, #34/#35 compatibility foundation stubs, #30/#32 branch protection, #25 linter removal, #23 chaos/property/nightly testing, #24 defensive artifact handling, #7 root-cause aggregator, #20/#21 schema-version detection, #17/#19 run-identity hooks, and duplicate #18.

## Mapping all 27 changes

| Change | Existing issue or proposed new issue                                               |
| -----: | ---------------------------------------------------------------------------------- |
|      1 | **N1** — evidence-safe probe semantics                                             |
|      2 | **N1** — existence/grant identity and certainty                                    |
|      3 | **N1**, then **N7** — effective write access and identifier handling               |
|      4 | **N2** — query-history correctness                                                 |
|      5 | **N1 + N3** — evidence precedence and lineage semantics                            |
|      6 | **N3** — lineage capability boundaries                                             |
|      7 | **N6**, with real confirmation supplied by open **#52**                            |
|      8 | **N5** — additive JSON evidence/graph contract                                     |
|      9 | **N4** — output assembly and fallback rendering                                    |
|     10 | **N10**; closed #24/#38 covered artifact robustness, not all profile/config shapes |
|     11 | **N9**, under epic #48                                                             |
|     12 | **N9**, under epic #48                                                             |
|     13 | **N3**                                                                             |
|     14 | **N3**                                                                             |
|     15 | **N3**                                                                             |
|     16 | **N6**                                                                             |
|     17 | **N6**                                                                             |
|     18 | **N4**                                                                             |
|     19 | **N7**                                                                             |
|     20 | **N7**                                                                             |
|     21 | **N8** portability spike, not an implementation PR                                 |
|     22 | **N9**, linked to #48, #44, and #12                                                |
|     23 | Already substantially covered by closed **#50**; residual cleanup can join N2      |
|     24 | Fold into N2 or N7; no standalone issue warranted                                  |
|     25 | **N10**                                                                            |
|     26 | **N11**                                                                            |
|     27 | **N11** product decision, linked to epic #4                                        |

## Genuinely new issue proposals

### N1 — `fix: make live existence and grant verdicts evidence-safe`

**[PROVEN] Scope:** introduce typed probe outcomes, record the identity used, split database/schema usage, and prohibit confirmed absence/denial when visibility or access checks are inconclusive.

**Labels:** `bug`, `live`, `correctness`, `security`.

**Sequence:** first; blocks N3, N6, and N7.

---

### N2 — `fix: repair Snowflake query-history matching and cursor lifecycle`

**[PROVEN] Scope:** use documented failure statuses, harden timing entries, preserve query visibility/provenance, close every cursor, and retain error details instead of converting failures to empty results.

**Labels:** `bug`, `live`, `snowflake`, `test`.

**Sequence:** first wave, parallel with N1.

---

### N3 — `refactor: preserve DAG edges and resolve disconnects on real paths`

**[PROVEN] Scope:** graph representations for both column and object lineage, reachable paths with actual depths, deterministic selection, truncation indicators, and positive/negative disconnect tests on real edges.

**Labels:** `architecture`, `lineage`, `bug`.

**Dependency:** N1’s evidence precedence.

---

### N4 — `fix: group by normalized root cause and render each report exactly once`

**[PROVEN] Scope:** replace `error_class:schema` grouping, preserve verbose member details, use explicit generic-template fallback, and eliminate duplicate root-cause/ordinary rendering.

**Labels:** `bug`, `output`, `root-cause`.

**Dependency:** normalized signatures from N3/N6 where relevant.

---

### N5 — `feat: define the additive JSON contract for evidence, lineage graphs, and diffs`

**[PROVEN] Scope:** serialize structured evidence, unknown states, graph edges, resolutions, diffs, and redaction policy; validate with golden CLI JSON.

**Labels:** `enhancement`, `json`, `api`, `test`.

**Dependency:** N3 and N6 data models.

---

### N6 — `refactor: replace mutable enrichment prose with requests, evidence, and resolutions`

**[PROVEN] Scope:** capability-based requests, one class-agnostic collector, typed evidence payloads, explicit resolution, no doubled probes, and parity for every existing enricher before legacy removal.

**Labels:** `architecture`, `live`, `correctness`.

**Dependency:** N1 and N2.

---

### N7 — `refactor: centralize Snowflake metadata, relation kinds, and identifier quoting`

**[PROVEN] Scope:** one long-lived gateway per connection, exact table/view/object probes, quoted-name parser, role validation/quoting, typed describe/grant results, and identity-aware caches.

**Labels:** `architecture`, `live`, `security`, `snowflake`.

**Dependency:** N1 and N2.

---

### N8 — `spike: define the real warehouse-neutral adapter contract`

**[PROVEN] Scope:** specify connection/profile, dialect, normalized error, relation metadata, parameters, query history, identity, access, type semantics, and fix-generation capabilities before adding adapter classes.

**Labels:** `spike`, `architecture`, `portability`.

**Dependency:** N7 must first expose the actual Snowflake contract.

---

### N9 — `fix: make the consumed-path registry and schema gate semantically complete`

**[PROVEN] Scope:** inventory all reads, centralize accessor fallback declarations, compare relevant definitions plus type/nullability/requiredness, and run against first-party schemas and real goldens.

**Labels:** `bug`, `compat`, `test`.

**Dependency:** epic #48, open #44 and #12.

---

### N10 — `fix: validate config/profile shapes without silent fallback`

**[PROVEN] Scope:** distinguish missing from malformed YAML, validate nested types, preserve explicit-env warnings, and consolidate discovery without changing search behavior.

**Labels:** `bug`, `cli`, `config`.

**Dependency:** none.

---

### N11 — `feat: support standalone artifacts with an explicit live-connection policy`

**[PROVEN] Scope:** artifact-only paths, unavailable source context, no accidental CWD/profile connection, mutually exclusive live flags, and a documented default decision.

**Labels:** `enhancement`, `cli`, `security`, `decision`.

**Dependency:** N1 and epic #4’s product decision.

---

### N12 — `test: enforce real-artifact contracts and gated live-Snowflake CI`

**[PROVEN] Scope:** committed `real_*` contracts, first-party schema tests, package/build matrix, required CI contexts, pre-commit, and a secret-gated live job.

**Labels:** `test`, `ci`, `live`.

**Dependency:** #12, #44, #52 and the corrected probe APIs.

## Creation timing

**[PROVEN] Create now:** N1, N2, N3, N4, N9, and N12. They describe already-demonstrated correctness or test gaps and do not require unresolved product design.

**[PROVEN] Create in a follow-up chat:** N5, N6, N7, N8, N10, and N11. Their scopes should be refined after the first correctness fixes establish typed probe behavior and after the live-default/portability decisions are made.

---

# 4. Snowflake-agnostic architecture

## Verdict on change 21

**[PROVEN] Change 21 is a thin shell with zero effective separation.** After all 27 changes, all production paths still call Snowflake-specific modules directly.

### Snowflake assumptions still outside the adapter

* **[PROVEN] Connection:** `parse_profile()` rejects every profile type except `snowflake`; `open_connection()` imports `snowflake.connector` and maps account, warehouse, role, and Snowflake authentication fields.
* **[PROVEN] Error ownership:** runtime, timeout, data, contract, and schema-change classifiers directly parse Snowflake codes/messages and generate Snowflake SQL.
* **[PROVEN] Type semantics:** classifiers and reconciliation directly encode `TIMESTAMP_LTZ`, `TIMESTAMP_NTZ`, `TIMESTAMP_TYPE_MAPPING`, `CURRENT_TIMESTAMP`, and `SYSDATE`.
* **[PROVEN] SQL dialect:** `ColumnTracer` hard-codes `dialect="snowflake"` in parse, qualify, and serialization calls.
* **[PROVEN] Metadata:** `SHOW TABLES`, `DESCRIBE TABLE`, `SHOW PARAMETERS`, `SHOW GRANTS`, and Snowflake’s query-history table function remain in enrichers.
* **[PROVEN] Identity:** role, warehouse, user, and query-history recovery remain Snowflake concepts in `run_identity.py`.
* **[PROVEN] Root-cause fixes:** `root_cause.py` directly emits Snowflake `SHOW` and `GRANT` statements.
* **[PROVEN] Identifiers:** uppercase folding and exactly three dot-separated segments remain distributed through classifiers, grouping, tracers, and enrichers.
* **[PROVEN] Output prose:** models and templates say “Snowflake” directly.
* **[PROVEN] Artifact interpretation:** `adapter_response.query_id` is treated as Snowflake query identity outside any adapter.

## What breaks on a second warehouse

### BigQuery

**[PROVEN]** Snowflake role/warehouse recovery and `QUERY_HISTORY(...)` are unusable. BigQuery exposes project/region-scoped job metadata through `INFORMATION_SCHEMA.JOBS`, with IAM permissions, job IDs, user/principal fields, `error_result`, and region qualification. That is a different capability and security model. ([Google Cloud Documentation][13])

**[PROVEN]** Project/dataset/table names and BigQuery error payloads cannot be normalized by the current three-part Snowflake identifier regexes and message parsers.

### PostgreSQL

**[PROVEN]** Identifier folding is different: PostgreSQL folds unquoted names to lowercase and supports arbitrary quoted identifier characters. The package’s unconditional uppercase normalization changes identity. ([PostgreSQL][14])

**[PROVEN]** PostgreSQL privilege metadata uses information-schema views such as `role_table_grants`; Snowflake `SHOW GRANTS TO ROLE` tuple logic does not transfer. ([PostgreSQL][15])

**[PROVEN]** Warehouse, Snowflake session parameters, and Snowflake query-history table functions have no adapter implementation.

### DuckDB

**[PROVEN]** DuckDB is commonly an in-process database connected via a file or in-memory connection. Snowflake account, warehouse, role, and remote query-history assumptions are inapplicable. ([DuckDB][16])

**[PROVEN]** DuckDB’s `SHOW` is an alias for `DESCRIBE`, not Snowflake’s object-listing command, and its metadata is exposed through its own information schema and pragmas. ([DuckDB][17])

## What a real seam must cover

**[PROVEN]** A useful `WarehouseAdapter` must provide or explicitly declare unsupported capabilities for:

1. connection and profile resolution;
2. identifier parsing, normalization, and quoting;
3. SQLGlot dialect;
4. error normalization, including structured adapter responses;
5. relation kinds, existence, and column description;
6. session/account parameters;
7. execution identity and query-history correlation;
8. effective read/write access;
9. platform type semantics;
10. platform-specific remediation SQL.

**[PROVEN]** The adapter must be injected into `DiagnosticContext` and used by classifiers, `ColumnTracer`, enrichment, and root-cause resolution. Until that happens, defining a protocol has no architectural effect.

---

# 5. CI and shift-left testing

## What CI runs now

### `guards`

**[PROVEN]** Checks out full history and runs only `check_no_attribution.sh`.

### `test`

**[PROVEN]** Runs on Python 3.12 only, installs `.[dev,live]`, and executes unfiltered `pytest -q`.

### `compat-schema-gate`

**[PROVEN]** Runs only when `fixtures/schemas/manifest/v12.json` exists. If that sentinel is absent, the entire gate reports a message and succeeds.

**[PROVEN]** Adjacent manifest and run-results pairs are silently skipped when individual files are missing.

**[PROVEN]** Catalog and sources self-diffs fail only after the manifest-v12 sentinel enables the job steps.

### Branch protection

**[PROVEN]** Both policy JSON files require only the `test` context. `guards` and `compat-schema-gate` can fail without blocking merge.

## What CI misses

* **[PROVEN]** Python 3.11, despite `requires-python = ">=3.11"`.
* **[PROVEN]** A wheel/sdist build and installed-wheel smoke test.
* **[PROVEN]** Explicit tier execution and reporting for `unit`, `contract`, `property`, `robustness`, `e2e`, `chaos`, and `live`.
* **[PROVEN]** A guarantee that every claimed real contract fixture actually has a `real_*` name and provenance.
* **[PROVEN]** Real-artifact schema validation and classifier expectations.
* **[PROVEN]** Live Snowflake behavior.
* **[PROVEN]** Static import/compile checks that would catch change 13’s missing annotation import.
* **[PROVEN]** Pre-commit hooks.
* **[PROVEN]** Coverage or mutation thresholds.
* **[PROVEN]** Required status checks for the guard and compatibility jobs.
* **[PROVEN]** A visible nightly workflow in the authoritative CI snapshot, despite closed issue #23 describing one.

## Shift-left tests requiring no warehouse

1. **[PROVEN] Real `real_*` artifact contracts can run fully offline.** Commit scrubbed manifest, run-results, and catalog artifacts and assert exact classification, structured fields, JSON output, and degradation behavior.

2. **[PROVEN] First-party schema contracts can run offline.** The published schema cache can validate actual consumed paths and all `real_*` artifacts.

3. **[PROVEN] Robustness/property tests need no warehouse.** Run malformed-shape, unknown-version, missing-field, and Hypothesis invariants on every PR.

4. **[PROVEN] CLI e2e tests need no warehouse when passed `--no-live`.** Test text, JSON, exit status, explicit-artifact mode, redaction, and missing-template fallback.

5. **[PROVEN] Adapter contract tests can use recorded connector rows.** Feed exact documented/recorded tuple shapes into the metadata parser without executing SQL.

6. **[PROVEN] Build/import checks need no warehouse.** Add:

```bash
python -m compileall dbt_diagnostics
python -m build
python -m venv smoke-venv
pip install dist/*.whl
dbt-diagnostics --help
```

7. **[PROVEN] Test Python 3.11 and 3.12.** The missing-import/annotation class of failure is precisely the sort of issue a version matrix catches early.

8. **[PROVEN] Make the schema cache mandatory once committed.** Remove the sentinel-based success path; absence of the source-of-truth cache should fail.

## Tests requiring a real Snowflake account

* **[PROVEN]** Visibility differences between diagnostic and run roles.
* **[PROVEN]** Direct versus inherited/effective grants.
* **[PROVEN]** Exact behavior for tables, views, quoted identifiers, and inaccessible schemas.
* **[PROVEN]** Query-history visibility, documented failure statuses, query-ID correlation, and bounded lag/retry behavior.
* **[PROVEN]** Session parameter values and level.
* **[PROVEN]** Real connector tuple shapes and exception behavior.
* **[PROVEN]** End-to-end capture of `real_*` artifacts.

A live job should be gated by credentials, an approved GitHub environment, manual/scheduled invocation or a trusted-PR condition, and a dedicated disposable schema/role. It should never expose secrets to forked PRs.

## Pre-commit

**[PROVEN]** No pre-commit configuration or dependency appears in the snapshot.

A minimal first pass should run YAML/JSON validation, trailing-whitespace/end-of-file checks, `python -m compileall`, the attribution guard on changed files, and a fast unit subset. Ruff or a type checker should be added only as an explicit, pinned tool decision rather than assumed by this review.

**[PROVEN]** AGENTS.md says the coding-agent token cannot modify workflow files, so any CI workflow change must be committed by the maintainer through an environment with workflow permission.

---

# 6. What the human missed

1. **[PROVEN] Four passes from the same model family are not four independent reviews.** They share priors, wording habits, and likely blind spots. OUTPUT_THREE’s polished patches inherit conclusions from OUTPUT_ONE and OUTPUT_TWO rather than independently validating every external contract.

2. **[PROVEN] The reviews repeatedly treated executable-looking prose as executable code.** Change 2 contains a literal ellipsis, change 13 omits required imports, change 17 deliberately doubles live operations, and change 21 creates an unused shell. Formatting created false confidence.

3. **[PROVEN] No review has established end-to-end behavior.** No package test suite, real artifact corpus, live probe, rendered report, or installable wheel was exercised from the supplied snapshot.

4. **[PROVEN] Tracker state is already drifting from code state.** Epic #4’s June 16 body says the linter package is still present, while the authoritative snapshot contains no such package and #25 is closed.  Epic #48 still presents completed supporting work as an unchecked build sequence while several corresponding issues are closed.

5. **[PROVEN] Closed issue state is not proof that the promised deliverable exists in this snapshot.** Issue #23 describes a nightly workflow, but the authoritative CI source supplied here contains only the ordinary CI workflow.

6. **[PROVEN] The code’s deepest problem is epistemic, not merely structural.** It repeatedly confuses:

   * not visible with nonexistent,
   * no direct grant row with no effective access,
   * manifest declaration with physical truth,
   * a same-named ancestor column with proven lineage,
   * failed probe with negative fact.

   A graph class or adapter protocol does not fix those mistakes unless evidence identity, status, provenance, and confidence are first-class.

7. **[PROVEN] The 27-change plan is too large to review or ship as one coherent unit under the repository’s own “one issue per PR” convention.** Several changes also build temporary compatibility layers that are immediately superseded, increasing code and test surface before correctness is established.

8. **[PROVEN] Analysis paralysis is now a real risk.** A complete warehouse abstraction, evidence ontology, graph rewrite, JSON revision, config cleanup, and CI redesign are not prerequisites for correcting the immediate false diagnoses.

9. **[PROVEN] The immediate shipping slice should be much smaller:**

   1. fix query-history failure statuses;
   2. make live probes typed and identity-aware;
   3. prohibit high-confidence absence/denial from inconclusive evidence;
   4. add real regression fixtures for those cases;
   5. then replace lineage adjacency with real edges.

10. **[PROVEN] Chat documents are not the repository source of truth.** AGENTS.md explicitly says chat notes are disposable. None of these conclusions matter operationally until they become narrowly scoped issues, tested PRs, and merged code.

## Final judgment

**[PROVEN] Do not implement OUTPUT_THREE wave by wave as currently written.** Keep changes 4, 6, 9, 23, and 24 as small candidates; retain change 7 as a wording correction; rewrite most of the remaining items around typed, identity-aware evidence; and redesign changes 13–21 before coding them.

**[PROVEN] The highest-priority defect is not portability. It is that the current and proposed Snowflake logic can report a confident cause that the available evidence does not prove.**

[1]: https://docs.snowflake.com/en/sql-reference/sql/show-tables "https://docs.snowflake.com/en/sql-reference/sql/show-tables"
[2]: https://docs.snowflake.com/en/sql-reference/functions/query_history "https://docs.snowflake.com/en/sql-reference/functions/query_history"
[3]: https://docs.snowflake.com/sql-reference/identifiers-syntax "https://docs.snowflake.com/sql-reference/identifiers-syntax"
[4]: https://docs.python.org/3.11/library/__future__.html "https://docs.python.org/3.11/library/__future__.html"
[5]: https://schemas.getdbt.com/dbt/run-results/v6.json "https://schemas.getdbt.com/dbt/run-results/v6.json"
[6]: https://schemas.getdbt.com/dbt/catalog/v1.json "https://schemas.getdbt.com/dbt/catalog/v1.json"
[7]: https://docs.snowflake.com/en/en/sql-reference/sql/desc-table "https://docs.snowflake.com/en/en/sql-reference/sql/desc-table"
[8]: https://docs.snowflake.com/en/sql-reference/sql/show-grants "https://docs.snowflake.com/en/sql-reference/sql/show-grants"
[9]: https://docs.snowflake.com/en/en/sql-reference/sql/show-parameters "https://docs.snowflake.com/en/en/sql-reference/sql/show-parameters"
[10]: https://docs.snowflake.com/en/en/sql-reference/sql/execute-immediate-from "https://docs.snowflake.com/en/en/sql-reference/sql/execute-immediate-from"
[11]: https://docs.snowflake.com/ja/user-guide/budgets/troubleshoot "https://docs.snowflake.com/ja/user-guide/budgets/troubleshoot"
[12]: https://sqlglot.com/sqlglot/schema.html "https://sqlglot.com/sqlglot/schema.html"
[13]: https://docs.cloud.google.com/bigquery/docs/information-schema-jobs "https://docs.cloud.google.com/bigquery/docs/information-schema-jobs"
[14]: https://www.postgresql.org/docs/current/sql-syntax-lexical.html "https://www.postgresql.org/docs/current/sql-syntax-lexical.html"
[15]: https://www.postgresql.org/docs/16/infoschema-role-table-grants.html "https://www.postgresql.org/docs/16/infoschema-role-table-grants.html"
[16]: https://duckdb.org/docs/stable/connect/overview.html "https://duckdb.org/docs/stable/connect/overview.html"
[17]: https://www.duckdb.org/docs/stable/sql/statements/show "https://www.duckdb.org/docs/stable/sql/statements/show"
