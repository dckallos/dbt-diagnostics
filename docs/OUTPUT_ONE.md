# Technical review

## Overall assessment

The package has a credible layered design: artifact loading, classification, tracing, optional live enrichment, structured models, and rendering are separated. The compatibility work in `dbt_diagnostics.compat` is especially deliberate, and the core dependency footprint is restrained.

The main weakness is **confidence calibration**. Several paths turn “the probe failed,” “the diagnostic role could not see it,” or “the manifest merely declares it” into a definitive diagnosis such as “never built,” “schema drift,” or “role lacks access.” Those are correctness risks rather than style concerns.

| Severity | Finding                                                                                                                                                                       |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| High     | Live existence/grant failures are frequently collapsed into negative facts and high-confidence fixes.                                                                         |
| High     | Lineage data is non-linear, but disconnect logic scans it as a linear sequence; displayed status can also mark a failed node as passing.                                      |
| High     | `grouping.py` can group unrelated runtime errors by schema and prescribe an incorrect materialization fix.                                                                    |
| High     | `--json` omits most live enrichment, live lineage state, and diff analysis despite running those features.                                                                    |
| High     | Identifier and role interpolation has concrete SQL-injection and correctness gaps.                                                                                            |
| Medium   | The advertised “degrade, never crash” behavior is not consistently enforced at artifact, profile, classifier, or cursor boundaries.                                           |
| Medium   | Snowflake execution is fairly concentrated, but Snowflake diagnostic semantics are spread across more than a dozen modules, making future portability a substantial refactor. |

For the ambiguous `__init__.py` files, I infer the instance importing `connection`, `enrich`, and `grants` is `dbt_diagnostics.enrichers.__init__`; the comment-only instance is `dbt_diagnostics.compat.__init__`; the instance importing `dag_walker`, `column_tracer`, and `snippet` is `dbt_diagnostics.tracers.__init__`; the instance importing classifiers is `dbt_diagnostics.classifiers.__init__`; and the instance importing `.tracers` and `.models` appears to be the root `dbt_diagnostics.__init__`.

---

# 1. Complexity and architecture

## Architectural shape

The roughly 33 runtime Python modules fall into understandable groups:

* `main.py`, `discover.py`, `models.py`, `renderer.py`, `grouping.py`, and `root_cause.py` form the application shell.
* `classifiers/*` turn failed dbt results into `DiagnosticReport` objects.
* `tracers/*` inspect the manifest, compiled SQL, and prior manifests.
* `enrichers/*` execute Snowflake metadata queries and mutate findings.
* `compat/*` handles artifact-field and schema-version variation.

The primary pipeline in `main.py` is:

1. Resolve project/profile paths.
2. Load artifacts.
3. Check artifact schema versions.
4. Classify each failure.
5. Annotate cascades.
6. Optionally calculate manifest diffs.
7. Mutate reports with live enrichment.
8. Reconcile findings based on live values.
9. Build root-cause groups.
10. Independently group reports for presentation.
11. Render text or JSON.

That is substantial but mostly reflects essential domain complexity: dbt exposes several artifacts, errors are heterogeneous, lineage is a graph, and live metadata is optional.

## What is well-factored

Several boundaries are strong:

* `BaseClassifier` and `DiagnosticContext` in `classifiers/base.py` give classifiers a consistent, side-effect-free interface. Classifiers return models rather than printing.
* `models.py` provides a useful typed boundary between diagnosis and presentation. `DiagnosticFinding`, `LineageStep`, `EnrichmentData`, and `DiagnosticReport` are coherent domain concepts.
* `renderer.py` and the Jinja templates keep terminal formatting out of the classifiers.
* `safe.py` centralizes tolerant access to renamed artifact fields such as `compiled_code`/`compiled_sql`.
* `schema_version.py` has a clear contract and generally implements it carefully: malformed metadata becomes a note rather than a hard failure.
* `ArtifactLoadError` in `main.py` distinguishes a missing artifact from a present-but-corrupt artifact, producing materially better CLI behavior than a raw JSON exception.
* `snippet.py` is small, cohesive, and handles invalid and out-of-range line numbers cleanly.
* The live connector is an optional dependency, and `sqlglot`, PyYAML, and Jinja2 are a reasonable core set. Avoiding a runtime dependency on dbt-core keeps installation and version coupling lower.

## Accidental complexity and coupling

The complexity is concentrated in `main.py`, `enrichers/enrich.py`, `classifiers/runtime_error.py`, and `root_cause.py`. The issue is less their size than the number of ordering-dependent mutations.

`enrich_reports()` mutates findings, then `_reconcile_findings()` rewrites fixes, then `_check_write_access_for_unmaterialized()` may prepend another fix. Root-cause grouping subsequently interprets those reports, while `renderer.render_text()` separately invokes `group_reports()`. A finding’s final meaning therefore depends on which passes ran and in what order.

Specific coupling examples:

* `enrich.py` switches on string values such as `"contract_violation"` and `"runtime_error"` rather than dispatching through an enrichment capability.
* It imports the private `_edit_distance` helper from `schema_inspector.py`.
* `RuntimeErrorClassifier` dynamically imports and delegates to `SchemaChangeErrorClassifier`.
* `root_cause.py` dynamically imports enrichers to avoid cycles.
* `run_identity.py` duplicates provenance constants from `root_cause.py` with the comment that the values “must stay in sync.” That is an explicit synchronization hazard.
* `grouping.py` and `root_cause.py` implement two overlapping notions of report aggregation.

A small normalized intermediate model would reduce this: parsed database error, relation identifier, confidence/evidence, and probe outcomes. That would avoid repeatedly rediscovering structured facts from summaries and raw messages.

## Data structures and control flow

The package uses typed output objects but raw dictionaries for all input artifacts. That is pragmatic, but it creates many scattered assumptions about shape and type. For example:

* `DagWalker.__init__()` assumes `manifest` and `manifest["nodes"]` are dictionaries.
* Multiple classifiers scan `run_results["results"]` linearly.
* `diff_node()` assumes node `columns` values are dictionaries.
* `enrich.py` assumes timing entries contain `"name"`.

An indexed artifact context would help without introducing a full dbt schema model: `nodes_by_id`, `sources_by_id`, `results_by_id`, `status_by_id`, and perhaps `relation_to_node`.

Current complexity is unnecessarily quadratic in places. `_find_result()`, classifier `_get_run_status()` methods, and repeated `_build_run_status_map()` calls scan the same run-results list. `ContractViolationClassifier` rebuilds the sqlglot schema once per mismatched column. On the live side, an invalid-identifier finding can issue a table description, then repeat existence and description calls for every lineage step, followed by another existence query in `LiveObjectProbe`.

A per-diagnosis cache keyed by relation and a few artifact indexes would remove most of this without changing the design.

---

# 2. Database-platform portability

Snowflake-only behavior is explicitly declared in `pyproject.toml`, so this is not a current scope defect. It does, however, establish significant future migration cost.

## Where Snowflake assumptions live

### Connection and identity

`enrichers/connection.py`:

* Rejects profiles unless `target_config["type"] == "snowflake"`.
* Maps directly to `snowflake.connector.connect()`.
* Understands Snowflake-specific account, warehouse, role, authenticator, and key-pair fields.

`enrichers/run_identity.py` and `grants.py` assume:

* Query history exposes `ROLE_NAME`, `USER_NAME`, and `WAREHOUSE_NAME`.
* Identity is role-based.
* Access can be reasoned about using `SHOW GRANTS TO ROLE`.
* `CURRENT_ROLE()` is meaningful.

Those assumptions do not transfer mechanically to IAM-based platforms.

### Live metadata and query history

The live SQL is strongly Snowflake-specific:

* `SHOW PARAMETERS IN SESSION`
* `SHOW PARAMETERS LIKE ... IN SESSION`
* `DESCRIBE TABLE`
* `SHOW TABLES LIKE ... IN db.schema`
* `INFORMATION_SCHEMA.QUERY_HISTORY(...)` as a table function
* Named query-history arguments such as `END_TIME_RANGE_START`
* `TO_TIMESTAMP_LTZ`
* `SHOW GRANTS TO ROLE`
* `SELECT CURRENT_ROLE()`

The code also depends on Snowflake-specific result-column positions from `SHOW` and `DESCRIBE` commands.

### Error classification and advice

Snowflake semantics are spread through classifiers:

* `runtime_error.py` hardcodes `002003`, `000904`, `003001`, and `001003`.
* `data_error.py` hardcodes Snowflake error wording and recommends `TRY_CAST`, `NUMBER(38,0)`, `IFF`, and Snowflake’s maximum `VARCHAR` size.
* `timeout_error.py` emits Snowflake warehouse DDL.
* `contract_violation.py` and `enrich.py` reason about `TIMESTAMP_LTZ`, `TIMESTAMP_NTZ`, and `TIMESTAMP_TYPE_MAPPING`.
* Many fixes emit Snowflake `GRANT`, `SHOW`, or cast syntax.

The SQL execution is concentrated in enrichers, but the **meaning and remedy** of errors is diffuse.

### SQL parsing and identifiers

`tracers/column_tracer.py` hardcodes `dialect="snowflake"` for parsing, qualification, and serialization. It uppercases identifiers and removes quotes when building schemas.

`schema_inspector.py` requires exactly three-part `DB.SCHEMA.TABLE` names and implements Snowflake unquoted-identifier rules. Several classifiers likewise assume three-part names with regexes such as `\w+\.\w+\.\w+`.

### dbt artifact layer

The artifact compatibility layer is largely platform-neutral. `schema_version.py`, `compat/safe.py`, most of `DagWalker`, `diff_tracer.py`, the output models, and the renderer should survive a new database backend with limited changes.

`adapter_response.query_id` and `rows_affected` are correctly marked adapter-specific in `consumed_paths.py`, which is a good start.

## Required abstraction boundary

A useful boundary would need to cover more than executing SQL:

```text
WarehouseAdapter
  connection_from_profile(...)
  sqlglot_dialect
  parse_relation(...) / quote_identifier(...)
  normalize_database_error(result, message)
  relation_status(...)
  describe_relation(...)
  query_history_match(...)
  session_parameters(...)
  recover_execution_identity(...)
  inspect_read_access(...)
  inspect_write_access(...)
  type_semantics / platform-specific fixes
  capabilities
```

The normalized error should carry fields such as:

```text
category: object_missing | invalid_identifier | permission | timeout | data
error_code
relation
identifier
required_privilege
line
position
raw_message
```

Classifiers could then operate on this normalized evidence instead of Snowflake regexes. Platform-specific fix generation should sit with the adapter or a platform policy object, not in otherwise generic classifiers.

Identifier parsing deserves its own type. Splitting on `"."` and uppercasing cannot correctly represent quoted identifiers, names containing dots, case-sensitive identifiers, or databases that use different qualification depths.

## Realistic effort and risk

This is a moderate-to-large extraction, not a rewrite. Most of `compat`, `models`, rendering, schema-version detection, artifact loading, and basic DAG navigation can remain.

The first extraction would touch more than a dozen modules because platform semantics appear in:

* all seven enricher modules,
* `root_cause.py`,
* `column_tracer.py`,
* several classifiers,
* profile discovery and CLI text,
* identifier handling and generated fixes.

After a Snowflake adapter faithfully reproduces current behavior, a second backend would primarily require a connector/profile implementation, metadata probes, error normalization, dialect/type rules, and fixtures.

The principal risk is not mechanical code movement. It is assuming concepts transfer when they do not: role inheritance, object visibility, relation kinds, query-history retention, timestamp types, and privilege models vary substantially.

---

# 3. Code-quality and correctness risks

## High: live probes confuse “unknown” with “false”

This is the most important issue.

`check_role_grants()` and `check_write_access()` in `enrichers/grants.py` catch every exception and return ordinary negative-looking results. There is no `query_succeeded` or `error` field.

That becomes a false diagnosis in multiple places:

* `_check_write_access_for_unmaterialized()` in `enrich.py` interprets `can_create=False` as “Role X does NOT have CREATE TABLE,” even when `SHOW GRANTS` itself failed.
* `root_cause._apply_verdict()` treats `exists=False` plus no `grants_found` as `VERDICT_NEVER_BUILT` with high confidence.
* When `exists is None`, `LiveObjectProbe.access_check()` still returns a truthy default dictionary with `has_access=False`; `_apply_verdict()` can therefore classify the case as denied even if the grant query failed too.

There are further evidence mismatches:

* `table_exists()` executes under the diagnostic connection’s current role, while `access_check()` may inspect a recovered or declared dbt role. Existence and privilege evidence may therefore describe different identities.
* `enrich._check_write_access_for_unmaterialized()` uses `get_current_role()` rather than the run-role recovery logic used by `LiveObjectProbe`.
* `check_write_access()` combines database and schema USAGE into one `has_usage` boolean. Having either is treated as having the prerequisite access, so generated grant advice can omit the other.
* The implementation examines returned grant rows but does not model role hierarchy or inherited privileges.

The minimal remediation is a structured probe result:

```text
value: True | False | None
status: confirmed | not_found | denied | query_failed | unsupported
identity_used
error_summary
```

Only `confirmed` evidence should produce “VERIFIED,” “CONFIRMED,” or high confidence.

## High: relation existence is not an exact check

`schema_inspector.table_exists()` runs:

```python
SHOW TABLES LIKE '{table}' IN {db}.{schema}
```

and returns `len(rows) > 0`.

Problems:

* `LIKE` treats `_` and `%` as pattern characters. `_` is valid in the package’s own identifier regex, so a similarly named table can produce a false positive.
* The result is not post-filtered to the exact object name.
* The implementation has no explicit handling for relation kinds other than tables, although it is used as a general object-existence probe.
* It requires exactly three name segments.
* Quoted identifiers containing dots cannot survive `fq_name.split(".")`.

An adapter-level exact relation lookup, with exact post-filtering and relation-kind awareness, would be safer.

## High: lineage is represented as a list but is actually a graph

`DagWalker.trace_column_lineage()` performs BFS over all upstream branches and appends nodes into one list. `_identify_disconnect()` in `enrich.py` then scans adjacent list entries:

```python
for i in range(len(trail) - 1):
    current = trail[i]
    next_step = trail[i + 1]
```

Adjacent BFS entries may be siblings rather than parent and child. The resulting `DisconnectVerdict` can name a break between unrelated nodes.

`trace_object_lineage()` has a related issue: it scans all manifest sources and nodes for a matching `relation_name`; it does not verify that the matched node is reachable from the failing node. The renderer may therefore show a globally matching but unrelated relation as lineage.

`LineageStep.status_emoji` and `status_text` also prioritize `manifest_status == "declared"` ahead of `run_status == "error"`. A declared model that failed can display a green pass icon. `_is_passing()` repeats that ambiguity, while `_is_failing()` can simultaneously consider the same step failing.

The minimal fix is to retain explicit edges or parent IDs and calculate disconnects per actual path. At minimum, statuses should have a documented precedence in which execution failure cannot be hidden by manifest declaration.

## High: schema drift is asserted too early

`RuntimeErrorClassifier._diagnose_invalid_identifier()` delegates to `SchemaChangeErrorClassifier` whenever `find_column_origin()` finds the column in an ancestor manifest node.

That evidence means only that an ancestor declaration or compiled alias contains the same name. It does not prove the live relation lost the column. Other explanations include a wrong table alias, quoted-case mismatch, an unrelated projection, or stale manifest metadata.

`SchemaChangeErrorClassifier._diagnose_drift()` nevertheless says:

> “This means the upstream table’s schema was altered outside dbt.”

Live lineage enrichment may later contradict that statement, but there is no reconciliation pass that changes the classification or wording.

Use “possible schema drift” until live description confirms that the relevant reachable relation exists and lacks the column.

## High: report grouping can create incorrect fixes

`grouping.group_reports()` groups by only:

```python
f"{report.error_class}:{schema_prefix}"
```

For any two `runtime_error` reports in the same schema, it emits:

> “N tests failed — SCHEMA models not yet materialized”

and a combined `dbt run`/`dbt test` fix.

Those reports could instead be invalid identifiers, permissions failures, syntax failures, or unrelated missing external sources. `_extract_model_names()` may also derive selector names from `target_object` relation names rather than dbt node names.

Grouping should require a normalized root-cause signature, not merely class and schema. The more evidence-aware grouping in `root_cause.py` is a better basis, although its verdict logic also needs correction.

`report.j2` renders `root_cause_groups` and then independently renders all reports through `group_reports()`. Because root-cause members are not removed, the same failure may be shown twice. The snapshot does not include template tests establishing whether that duplication is intentional.

## High: JSON output does not contain the work live mode performed

`DiagnosticReport._finding_to_dict()` in `models.py` omits:

* `finding.enrichment`,
* actual parameter values,
* actual columns,
* matched query history,
* `session_params_to_check`,
* `diagnostic_params`,
* lineage `relation_name`,
* lineage `live_status` and `live_detail`,
* most lineage manifest detail.

It also omits `report.diff`.

Consequences:

* `--live --json` performs live queries but does not expose most results.
* `--previous-manifest --json` calculates diffs but silently drops them.
* Text and JSON consumers receive materially different diagnoses.

The top-level output declares schema version `"1.2"`, while each report declares `"1.0"`. That may be intentional nested versioning, but the snapshot does not document the distinction.

Keep explicit serializers for API stability, but add the missing fields and golden JSON tests. Sensitive `matched_query_text` could be separately gated rather than silently discarded.

## High: unsafe and incomplete SQL construction

There is good parameter binding in `query_history.py`, and parameter names in `params.py` are allowlisted. Other paths are weaker.

`schema_inspector._QUOTED_IDENT_RE` allows any character except a double quote, including apostrophes. `table_exists()` then inserts the table segment inside a single-quoted `LIKE` literal. A quoted identifier containing an apostrophe can break that literal.

`grants.py` interpolates `role_name` directly into:

```python
SHOW GRANTS TO ROLE {role_name}
```

without validation or identifier quoting. `role_name` can come from `profiles.yml`.

Generated grant commands also concatenate artifact-derived names. Those commands are not executed automatically, which lowers immediate risk, but they can still be malformed or dangerous when copied.

A relation/identifier parser with backend-specific quoting should be used everywhere; regex validation plus string interpolation is not sufficient for quoted identifiers.

## Medium: “never crash” is inconsistently enforced

Examples:

* `load_json()` accepts any valid JSON value despite its `dict` annotation. A manifest containing `[]` passes loading and version detection, then `DagWalker(manifest)` calls `.get()` and crashes.
* `parse_profile()` assumes `yaml.safe_load()` returned a dictionary. An empty file makes `profile_name not in raw` raise `TypeError`; malformed YAML raises `yaml.YAMLError`. `open_connection()` catches only `ValueError`.
* `_try_enrich()` has no catch around `enrich_reports()`, so any unexpected live-enrichment exception aborts the CLI rather than falling back offline.
* Per-result classifier failures are not isolated in `_diagnose_all()`. One malformed result or unexpected sqlglot exception can prevent all other reports.
* Several live helpers call `cursor = conn.cursor()` before their `try` blocks. Cursor acquisition failures therefore escape their advertised graceful degradation. A failing `cursor.close()` in `finally` can also replace the original swallowed exception.
* `check_role_grants()`, `check_write_access()`, and `get_current_role()` do not close their cursors.
* `_is_lagging()` in `run_identity.py` contains a complete duplicated implementation after unconditional returns; that block is unreachable.

The package needs fewer blanket catches inside low-level functions and one reliable degradation boundary around each classifier and each live probe.

## Medium: regex parsing is brittle and inconsistent

Several classifiers match exact case-sensitive phrases:

* `"enforced contract that failed"`
* `"Compilation Error"`
* `"Database Error"`

Runtime error-code regexes are also mostly case-sensitive. Identifier and relation patterns frequently exclude quoted names, dollar signs, or alternate message forms.

`enrich._extract_from_table()` says it extracts from “raw_message or compiled code,” but only searches `report.raw_message`. Snowflake error messages generally need not contain the `FROM` clause, so the “did you mean?” live-column feature can often have no source relation to inspect.

`TestFailureClassifier` similarly recognizes only a narrow threshold SQL form and only unquoted three-part relations. Its blanket explanation that “The model SQL is correct — the DATA is the problem” is stronger than the evidence: a failing assertion can also reflect a wrong test definition or threshold.

A normalized platform error parser with fixture-backed cases would be less fragile than independent regexes embedded in each classifier.

---

# Cross-cutting concerns

## Compatibility layer

This is one of the better-designed areas, but its implementation does not fully match its claims.

Strengths:

* `safe.py` is defensive and small.
* `schema_version.py` provides explicit validation status and cross-artifact skew notes.
* `SchemaDoc` and `path_resolver.py` avoid a heavyweight JSON Schema dependency.
* The schema acquisition script is runtime-decoupled.

Gaps:

* `consumed_paths.py` says the registry is the “full set” of fields consumed, but code also reads fields not represented there, including `parent_map`, `sources`, `path`, `columns.*.data_type`, result `failures`, timing `name` and `completed_at`, and several metadata fields.
* `safe.py` does not actually consume `REGISTRY`; it independently hardcodes fallbacks. Synchronization therefore depends on tests, not a single executable source of truth.
* `schema_diff.py` uses `present_anywhere()`. A field can disappear from relevant model definitions but remain on one unrelated union member and still be reported stable.
* The diff gate does not compare the captured `required`, `types`, or `nullable` information, only presence.
* `SchemaDoc.deref()` resolves references by the final path component from one top-level definitions mapping. Nested definitions, mixed `$defs`/`definitions`, external references, and more complex `allOf` structures are not handled.

The snapshot references tests for these components, but the test bodies are not present, so the degree to which real dbt schemas exercise these limitations cannot be judged.

## Testing strategy

`pyproject.toml` advertises a strong taxonomy: unit, contract, property, robustness, e2e, chaos, and live tests. `compat/DESIGN.md` also describes synthetic and real-schema tests. That is encouraging, but actual coverage and pass status cannot be assessed from this snapshot.

The most valuable missing-or-essential regression cases are:

1. Probe query fails versus confirmed negative result.
2. Diagnostic connection role differs from recovered run role.
3. Branching DAGs with siblings at the same BFS depth.
4. A declared node with `run_status="error"` must not display as passing.
5. Two unrelated runtime failures in the same schema must not group.
6. Live and diff fields must appear in JSON.
7. Quoted identifiers containing dots, apostrophes, spaces, and mixed case.
8. Empty or structurally invalid YAML and valid-but-wrong-shaped JSON.
9. Message variants and error codes represented as strings and integers.
10. Schema fields disappearing from only a subset of union members.

## Performance

Offline performance should be adequate for ordinary projects, but repeated scans and live round trips will become noticeable on large runs:

* Result/status lookup is repeatedly linear.
* `trace_object_lineage()` scans all nodes and sources per error.
* sqlglot schemas are rebuilt per contract mismatch.
* Relation existence and descriptions are not cached across enrichment, lineage, and root-cause probing.
* Query-history matching runs once per runtime finding.
* `run_identity` limits history to the newest 1,000 entries, which can miss an older query in a busy environment despite the broader stated retention window.

A run-scoped context with indexes and caches would address most of this.

## Security and live-query behavior

Positive aspects:

* YAML uses `safe_load`.
* Query-history timestamps use connector parameters.
* Parameter names are allowlisted.
* The live queries shown are metadata/query-history operations rather than data-scanning model queries.
* The Snowflake connector is optional.

Risks:

* Identifier and role interpolation needs correction as described above.
* Live mode is enabled by default, and `.env` files are auto-loaded from the project, its parent, or the working directory. Running the CLI in an unfamiliar checkout can therefore initiate a connection using locally discovered credentials without an explicit `--live`.
* Query-history enrichment retrieves up to 50 failed query texts. Those texts may contain sensitive literals. `matched_query_text` is currently not serialized, but the data is retained in memory and should be treated as sensitive if later exposed.
* Raw artifact messages and live error text are written to terminals without control-character sanitization, allowing misleading ANSI sequences in untrusted artifacts or logs.

## CLI and public surface

Good:

* Text and JSON modes are explicit.
* Exit status is useful for CI.
* `--no-fail`, color controls, and offline fallback are practical.
* Optional live dependencies are lazily imported.

Gaps:

* `_resolve_from_args()` requires discovering a dbt project before applying explicit `--run-results` and `--manifest` paths. Standalone artifacts therefore cannot be diagnosed outside a project even though the flags appear to support that.
* `resolve_project_paths()` hardcodes `target/` and `models/`, ignoring custom dbt `target-path` and `model-paths`.
* `cmd_demo()` checks `args.json` for color decisions but always renders text.
* `sys.exit()` calls are embedded in application functions, making library reuse and testing harder.
* Jinja includes use `ignore missing`; adding a classifier without a matching template can silently produce an incomplete report instead of falling back to `generic.j2`.

---

# Recommended order of remediation

1. **Make all live evidence explicitly tri-state or multi-state.** Do not mutate fixes or issue high-confidence verdicts when a query failed or used the wrong identity.
2. **Correct lineage and grouping semantics.** Preserve graph edges, fix status precedence, restrict object matching to reachable nodes, and group only on normalized root-cause signatures.
3. **Repair the JSON contract.** Serialize enrichment, live lineage, and diffs; add golden CLI output tests.
4. **Centralize identifier handling and Snowflake access behind an adapter.** This resolves current injection/correctness issues and creates the eventual portability seam.
5. **Add robust orchestration boundaries and run-scoped indexes/caches.** Validate top-level artifact/profile shapes, isolate classifier failures, manage cursors consistently, and eliminate repeated scans.
6. **Tighten the compatibility gate.** Cover all actually consumed paths and compare per-definition presence and type/nullability changes rather than only “present anywhere.”

The package does not need a rewrite. Its core layering, structured output model, compatibility intent, and optional live architecture are sound foundations. The highest-value changes are about preserving uncertainty and ensuring that graph, role, and probe evidence cannot be converted into a stronger diagnosis than the code has actually established.
