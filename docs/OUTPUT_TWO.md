# Independent architecture review

## Executive verdict

**Choose (c): substantial refactor of specific subsystems. Do not rewrite the package.**

The package has a sound high-level decomposition, no import cycles, useful domain-specific parsing, and several cohesive low-level components worth preserving. The main structural problem is not the package layout. It is that classification, lineage inference, live verification, root-cause resolution, grouping, and rendering all independently reinterpret and mutate the same loosely typed report objects.

The highest-priority decisions are:

1. **Replace flat lineage lists with an edge-preserving graph or explicit paths.**
2. **Replace ambiguous Snowflake probe returns with typed tri-state results.**
3. **Separate observations, evidence, verdicts, and rendered prose; stop mutating fix strings during enrichment.**
4. **Centralize raw artifact access in indexed, version-tolerant views.**
5. **Keep the classifier registry and most local `if/elif` logic.** The procedural dispatch itself is not the architectural problem.

The live-enrichment and lineage internals merit substantial replacement behind stable interfaces. The package as a whole does not.

---

# 1. Architecture map

## Scope and size

The snapshot contains:

* **38 importable package modules**

  * 32 substantive modules
  * 5 `__init__.py` modules
  * 1 `__main__.py`
* **2 additional Python maintenance scripts**
* **11 Jinja templates**

Approximate physical LOC below includes comments and docstrings and is rounded from the inline snapshot.

```text
dbt_diagnostics top level: about 2,390 LOC
  __init__.py                         ~4
  __main__.py                         ~4
  colors.py                          ~85
  discover.py                       ~115
  grouping.py                       ~165
  main.py                           ~755
  models.py                         ~300
  renderer.py                       ~145
  root_cause.py                     ~430
  schema_version.py                 ~385

dbt_diagnostics.enrichers: about 1,465 LOC
  __init__.py                        ~23
  connection.py                    ~210
  enrich.py                        ~530
  grants.py                        ~165
  params.py                         ~65
  query_history.py                  ~90
  run_identity.py                  ~285
  schema_inspector.py               ~95

dbt_diagnostics.compat: about 440 LOC
  __init__.py                         ~2
  consumed_paths.py                ~150
  path_resolver.py                  ~80
  safe.py                          ~125
  schema_model.py                   ~85

dbt_diagnostics.tracers: about 885 LOC
  __init__.py                         ~5
  column_tracer.py                 ~340
  dag_walker.py                    ~375
  diff_tracer.py                   ~105
  snippet.py                        ~60

dbt_diagnostics.classifiers: about 1,830 LOC
  __init__.py                        ~28
  base.py                            ~65
  compilation_error.py             ~270
  contract_violation.py            ~210
  data_error.py                    ~215
  registry.py                       ~30
  runtime_error.py                 ~560
  schema_change_error.py           ~160
  test_failure.py                  ~190
  timeout_error.py                 ~105

Package total: approximately 7,000 physical Python lines.
```

The two compatibility scripts add roughly another 150 lines.

## Real internal import graph

This adjacency list follows the actual imports, including re-exporting package initializers. Deferred imports are marked separately.

```text
dbt_diagnostics.__main__
  -> dbt_diagnostics.main

dbt_diagnostics.__init__
  -> dbt_diagnostics.tracers.__init__
  -> dbt_diagnostics.models

dbt_diagnostics.main
  -> dbt_diagnostics.classifiers.__init__
  -> dbt_diagnostics.colors
  -> dbt_diagnostics.discover
  -> dbt_diagnostics.models
  -> dbt_diagnostics.renderer
  -> dbt_diagnostics.root_cause
  -> dbt_diagnostics.schema_version
  -> dbt_diagnostics.tracers.diff_tracer
  -> dbt_diagnostics.tracers.dag_walker
  -> dbt_diagnostics.tracers.column_tracer
  [deferred]
  -> dbt_diagnostics.enrichers.__init__
  -> dbt_diagnostics.enrichers.connection

dbt_diagnostics.renderer
  -> dbt_diagnostics.colors
  -> dbt_diagnostics.models
  -> dbt_diagnostics.grouping

dbt_diagnostics.grouping
  -> dbt_diagnostics.models

dbt_diagnostics.root_cause
  -> dbt_diagnostics.models
  [deferred]
  -> dbt_diagnostics.enrichers.schema_inspector
  -> dbt_diagnostics.enrichers.grants
  -> dbt_diagnostics.enrichers.run_identity

dbt_diagnostics.enrichers.__init__
  -> dbt_diagnostics.enrichers.connection
  -> dbt_diagnostics.enrichers.enrich
  -> dbt_diagnostics.enrichers.grants
  -> dbt_diagnostics.enrichers.params
  -> dbt_diagnostics.enrichers.schema_inspector
  -> dbt_diagnostics.enrichers.query_history

dbt_diagnostics.enrichers.enrich
  -> dbt_diagnostics.compat.safe
  -> dbt_diagnostics.models
  -> dbt_diagnostics.enrichers.params
  -> dbt_diagnostics.enrichers.schema_inspector
  -> dbt_diagnostics.enrichers.query_history
  -> dbt_diagnostics.enrichers.grants

dbt_diagnostics.enrichers.schema_inspector
  -> dbt_diagnostics.models

dbt_diagnostics.enrichers.run_identity
  -> dbt_diagnostics.compat.safe
  [deferred]
  -> dbt_diagnostics.enrichers.grants

dbt_diagnostics.compat.path_resolver
  -> dbt_diagnostics.compat.schema_model

dbt_diagnostics.tracers.__init__
  -> dbt_diagnostics.tracers.dag_walker
  -> dbt_diagnostics.tracers.column_tracer
  -> dbt_diagnostics.tracers.snippet

dbt_diagnostics.tracers.diff_tracer
  -> dbt_diagnostics.models
  -> dbt_diagnostics.compat.safe

dbt_diagnostics.tracers.dag_walker
  -> dbt_diagnostics.models
  -> dbt_diagnostics.compat.safe

dbt_diagnostics.tracers.snippet
  -> dbt_diagnostics.models

dbt_diagnostics.tracers.column_tracer
  -> dbt_diagnostics.compat.safe

dbt_diagnostics.classifiers.__init__
  -> dbt_diagnostics.classifiers.base
  -> dbt_diagnostics.classifiers.contract_violation
  -> dbt_diagnostics.classifiers.runtime_error
  -> dbt_diagnostics.classifiers.compilation_error
  -> dbt_diagnostics.classifiers.timeout_error
  -> dbt_diagnostics.classifiers.data_error
  -> dbt_diagnostics.classifiers.schema_change_error
  -> dbt_diagnostics.classifiers.test_failure
  -> dbt_diagnostics.classifiers.registry

dbt_diagnostics.classifiers.registry
  -> dbt_diagnostics.classifiers.base
  -> dbt_diagnostics.classifiers.contract_violation
  -> dbt_diagnostics.classifiers.compilation_error
  -> dbt_diagnostics.classifiers.timeout_error
  -> dbt_diagnostics.classifiers.data_error
  -> dbt_diagnostics.classifiers.schema_change_error
  -> dbt_diagnostics.classifiers.runtime_error

dbt_diagnostics.classifiers.base
  -> dbt_diagnostics.compat.safe
  -> dbt_diagnostics.models
  -> dbt_diagnostics.tracers.dag_walker
  -> dbt_diagnostics.tracers.column_tracer

dbt_diagnostics.classifiers.contract_violation
  -> dbt_diagnostics.classifiers.base
  -> dbt_diagnostics.models
  -> dbt_diagnostics.tracers.column_tracer

dbt_diagnostics.classifiers.runtime_error
  -> dbt_diagnostics.compat.safe
  -> dbt_diagnostics.classifiers.base
  -> dbt_diagnostics.models
  -> dbt_diagnostics.tracers.snippet
  [deferred]
  -> dbt_diagnostics.classifiers.schema_change_error

dbt_diagnostics.classifiers.test_failure
  -> dbt_diagnostics.compat.safe
  -> dbt_diagnostics.classifiers.base
  -> dbt_diagnostics.models

dbt_diagnostics.classifiers.schema_change_error
  -> dbt_diagnostics.classifiers.base
  -> dbt_diagnostics.compat.safe
  -> dbt_diagnostics.models
  -> dbt_diagnostics.tracers.snippet

dbt_diagnostics.classifiers.compilation_error
  -> dbt_diagnostics.classifiers.base
  -> dbt_diagnostics.models
  -> dbt_diagnostics.tracers.snippet

dbt_diagnostics.classifiers.timeout_error
  -> dbt_diagnostics.classifiers.base
  -> dbt_diagnostics.models

dbt_diagnostics.classifiers.data_error
  -> dbt_diagnostics.compat.safe
  -> dbt_diagnostics.classifiers.base
  -> dbt_diagnostics.models
  -> dbt_diagnostics.tracers.column_tracer
  -> dbt_diagnostics.tracers.snippet
```

Internal leaf modules include `models`, `schema_version`, `colors`, `discover`, most primitive enrichers, `compat.safe`, `compat.schema_model`, and `compat.consumed_paths`.

Outside the package:

```text
scripts.compat.schema_diff
  -> compat.consumed_paths
  -> compat.path_resolver
  -> compat.schema_model

scripts.compat.fetch_schemas
  -> no package modules
```

## Intended layering

The apparent intended layering is:

```text
CLI / application
  main

Post-processing / presentation
  root_cause, grouping, renderer, templates, colors

Diagnosis
  classifiers

Analysis utilities
  tracers

Live infrastructure
  enrichers

Low-level contracts
  models, compat
```

The static dependencies are mostly downward and acyclic:

```text
main
  -> classifiers -> tracers -> models / compat
  -> enrichers   -> models / compat
  -> renderer    -> grouping / models / colors
```

That is a real strength.

The responsibilities do not flow as cleanly as the imports, however:

* `models.LineageStep` contains `status_emoji` and `status_text`, so presentation policy lives in the domain model.
* `renderer.render_text()` invokes `group_reports()`, so presentation performs application-level aggregation.
* `root_cause.LiveObjectProbe` reaches into live infrastructure through deferred imports.
* `enrichers.enrich` rewrites human-facing `fix_suggestion` strings, so infrastructure changes the diagnosis narrative.
* `main.py` is both composition root and a large part of the application service.

The package is syntactically layered but semantically interleaved.

## Import cycles

**There are no current internal import cycles.**

There are several deferred imports:

| Site                                       | Deferred import                           | Assessment                                                                                                                                                                 |
| ------------------------------------------ | ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `main._try_enrich`                         | `dbt_diagnostics.enrichers`               | Reasonable lazy live boundary, though the missing-connector `ImportError` branch is misleading because `snowflake.connector` is imported later inside `open_connection()`. |
| `main._declared_role`                      | `enrichers.connection.parse_profile`      | Avoids eagerly pulling live-profile logic into the CLI module. Acceptable, but duplicate profile parsing is wasteful.                                                      |
| `root_cause.LiveObjectProbe.object_exists` | `enrichers.schema_inspector.table_exists` | Hides a real infrastructure dependency rather than removing it.                                                                                                            |
| `root_cause.LiveObjectProbe.access_check`  | `enrichers.grants.check_role_grants`      | Same.                                                                                                                                                                      |
| `root_cause.LiveObjectProbe.role_identity` | `enrichers.run_identity.recover_run_role` | Part of a would-be cycle smell.                                                                                                                                            |
| `run_identity.current_session_role`        | `enrichers.grants.get_current_role`       | No actual cycle requires this.                                                                                                                                             |
| `runtime_error.diagnose`                   | `SchemaChangeErrorClassifier`             | No actual cycle requires this; `schema_change_error` depends only on `base`, models, compat, and snippet.                                                                  |
| `connection.open_connection`               | `snowflake.connector`                     | Good optional-dependency boundary.                                                                                                                                         |
| `_load_dotenv` functions                   | `dotenv.load_dotenv`                      | Good optional-dependency boundary.                                                                                                                                         |
| `column_tracer.qualify_sql`                | `sqlglot.optimizer.qualify`               | Local fallback boundary; harmless.                                                                                                                                         |

`run_identity.py` explicitly duplicates the provenance constants from `root_cause.py`:

> “kept local to avoid an import cycle; values must stay in sync”

That is the clearest sign that the concepts belong in a lower shared module. There is no present cycle because the constants were copied and the import is deferred, but “must stay in sync” is an architectural defect.

## Fan-in and fan-out hotspots

Static internal fan-in:

| Module                  | Fan-in | Interpretation                                                                                  |
| ----------------------- | -----: | ----------------------------------------------------------------------------------------------- |
| `models`                |     18 | Expected central model, but its broad optional-field design makes every model change high-risk. |
| `compat.safe`           |     10 | A useful compatibility seam.                                                                    |
| `classifiers.base`      |      9 | Normal base-class concentration.                                                                |
| `tracers.snippet`       |      5 | Reusable leaf utility.                                                                          |
| `tracers.column_tracer` |      5 | Important analysis dependency.                                                                  |
| `tracers.dag_walker`    |      3 | Shared classifier/application dependency.                                                       |

Static fan-out:

| Module                 |                   Fan-out | Interpretation                                                                        |
| ---------------------- | ------------------------: | ------------------------------------------------------------------------------------- |
| `main`                 |       10, plus 2 deferred | Expected composition hotspot, but too much application behavior remains inside it.    |
| `classifiers.__init__` |                         9 | Mostly re-export cost.                                                                |
| `classifiers.registry` |                         7 | Expected registry fan-out.                                                            |
| `enrichers.__init__`   |                         6 | Eagerly loads the entire live package when the supposedly lazy package import occurs. |
| `enrichers.enrich`     |                         6 | Real behavioral hotspot.                                                              |
| `root_cause`           | 1 static, plus 3 deferred | Its low static fan-out hides substantial infrastructure coupling.                     |

## Largest functions and responsibility concentration

Approximate sizes matter less than the number of responsibilities inside them:

| Function                                            | Approximate size | Responsibilities combined                                                                                                                    |
| --------------------------------------------------- | ---------------: | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `RuntimeErrorClassifier._diagnose_object_not_found` |       ~150 lines | Parsing, manifest lookup, run-state lookup, source location, snippet extraction, lineage, causal inference, prose, and fix generation.       |
| `root_cause._apply_verdict`                         |             ~120 | Probe orchestration, role identity, access inference, confidence, headline/detail generation, and fixes.                                     |
| `main.cmd_diagnose`                                 |             ~115 | Artifact I/O, compatibility, optional catalog, classification, diffing, live lifecycle, grouping, serialization, rendering, and exit policy. |
| `main.main`                                         |             ~105 | Complete CLI schema and dispatch.                                                                                                            |
| `main._diagnose_all`                                |             ~100 | Artifact normalization, status partitioning, dispatch, warnings, and cascade annotation.                                                     |
| `enrich._check_write_access_for_unmaterialized`     |              ~90 | Lineage interpretation, schema extraction, caching, privilege interpretation, SQL generation, and prose mutation.                            |
| `enrich._enrich_runtime_error`                      |              ~85 | Object probe, identifier probe, suggestions, privilege disambiguation, and query-history matching.                                           |
| `DagWalker.trace_object_lineage`                    |              ~85 | Manifest indexing, ancestry claims, status creation, and synthetic-node generation.                                                          |
| `ColumnTracer.trace_column`                         |              ~75 | SQL parsing, qualification, scope handling, CTE search, and fallback search.                                                                 |
| `schema_version.detect_artifact_version`            |              ~70 | Shape validation, metadata parsing, kind inference, support policy, and notes.                                                               |

The problem functions are not merely long. They cross architectural boundaries.

---

# 2. Design and abstractions

## 2.1 Package decomposition: well chosen

The broad split into classifiers, tracers, enrichers, compatibility, models, and rendering is appropriate.

Concrete strengths:

* Classifiers return `DiagnosticReport` instead of printing.
* `main.py` is the composition root.
* `compat.safe` centralizes several version-sensitive field aliases.
* `schema_version.py` is isolated from classification.
* `schema_model.py` and `path_resolver.py` form a small, coherent schema-analysis subsystem.
* `ColumnTracer` contains SQL-AST work rather than leaking sqlglot into classifiers.
* `ArtifactLoadError` distinguishes absent and corrupt artifacts cleanly.
* `LiveObjectProbe` caches repeated existence/access lookups.

These boundaries should remain.

## 2.2 `DiagnosticFinding` as a universal mutable record: under-abstracted

`DiagnosticFinding` has a large number of optional fields representing mutually different concepts:

```python
summary
location
upstream_origin
explanation
fix_suggestion
session_params_to_check
diagnostic_params
enrichment
definition_type
contract_type
target_object
target_identifier
compiled_snippet
lineage_trail
disconnect
```

This permits invalid and contradictory combinations, and the code already creates them.

The clearest example is `TestFailureClassifier`:

```python
finding = DiagnosticFinding(
    ...
    target_object=tested_model,
    target_identifier=relation,
)
```

Elsewhere:

* `target_object` is treated as a fully qualified Snowflake object.
* `target_identifier` is treated as a column identifier.

Here they mean a dbt unique ID and a fully qualified relation, respectively. The types cannot express the distinction.

Other evidence:

* `ColumnMismatch` exists as a dataclass, but `parse_mismatch_table()` returns `list[dict]`; the abstraction is unused.
* `ColumnTraceResult` carries `line_number` and `file_path`, but every construction in `_find_alias_in_select()` and `_find_bare_column_in_select()` sets both to `None`.
* `ColumnTracer.trace_column()` accepts `source_file_path` but does not use it.
* `ColumnTracer` stores `compiled_dir`, but no shown method uses it.

The package has structured containers, but not a sufficiently structured domain model.

### Consequence

The report object is simultaneously:

* an observation model,
* a hypothesis model,
* a mutable enrichment accumulator,
* a verdict model,
* a renderer view model,
* and part of the JSON API.

That is the central architecture weakness.

## 2.3 Observation, hypothesis, and verdict are conflated

`RuntimeErrorClassifier._diagnose_object_not_found()` chooses a causal explanation before live verification. `root_cause._apply_verdict()` later chooses another causal explanation after probing. Both results are rendered.

For example, the classifier can generate:

> “Run the upstream model that produces …”

The root-cause section can subsequently conclude:

* the object exists now,
* the run role was denied,
* or the state is unverified.

Because `render_text()` receives all reports plus all root-cause groups, and then independently calls `group_reports(reports)`, the same report remains in ordinary output. The user can receive two different fixes for one error.

The same issue appears in schema-drift handling. `RuntimeErrorClassifier` delegates to `SchemaChangeErrorClassifier` when `find_column_origin()` finds a same-named column upstream. No live schema check has occurred at that point. A same-named upstream declaration is a hypothesis, not proof that the physical table was altered outside dbt.

`SchemaChangeErrorClassifier._diagnose_drift()` nevertheless says:

> “This means the upstream table's schema was altered outside dbt”

That conclusion is stronger than the available evidence.

`TestFailureClassifier` similarly states:

> “The model SQL is correct -- the DATA is the problem.”

A test assertion failure proves that the produced data violates an assertion. It does not prove the model SQL is correct.

### Judgment

This is **under-abstracted**. The code needs explicit observation, evidence, hypothesis, confidence, and final verdict concepts. More classifier subclasses will not solve it.

## 2.4 Lineage representation: under-abstracted and capable of incorrect verdicts

This is the most serious structural correctness issue.

`DagWalker.trace_column_lineage()` performs a BFS and returns a flat list:

```python
trail: list[LineageStep] = []
...
queue: deque[tuple[str, int]] = deque()
...
trail.append(step)
```

`_identify_disconnect()` then treats adjacent list elements as connected graph nodes:

```python
for i in range(len(trail) - 1):
    current = trail[i]
    next_step = trail[i + 1]
    if _is_passing(current) and _is_failing(next_step):
```

In a branched DAG, BFS order is not an edge path. A list can be:

```text
failing model
parent A
parent B
grandparent of A
```

`parent A` and `parent B` are siblings, and `parent B` may not connect to `grandparent of A`. The code can issue a disconnect verdict between unrelated nodes.

There is a second problem: every ancestor lacking a same-named column is marked `not_found`. In a join with two parents, only one parent may be expected to supply that column. Absence from the other parent is not failure.

A third problem is `trace_object_lineage()`. It searches every source and node in the manifest for a matching `relation_name`, rather than restricting the match to ancestors of the failing node. It can call a globally matching node part of the “lineage” without establishing an edge.

A fourth problem is `find_column_origin()`. It returns the first ancestor with a declared column or an `AS <name>` regex match. It does not prove that the current model's output column is derived from that ancestor. Contract diagnosis and schema-change classification both rely on this stronger interpretation.

### Judgment

This subsystem requires a **substantial refactor**, including a new graph/path result model. The current list representation cannot faithfully support the verdict algorithm.

## 2.5 Live Snowflake boundary: under-abstracted and semantically unsafe

The project has the right policy: probes should degrade rather than crash. The return types do not preserve enough information to implement that policy honestly.

### Unknown is converted to absent

`table_exists()` documents:

```python
Returns True/False, or None if the check itself failed
```

But `_enrich_lineage_trail()` does this:

```python
if exists:
    ...
else:
    step.live_status = "missing"
```

`None` therefore becomes “table does NOT exist in Snowflake.” That false absence can then drive:

* a high-confidence disconnect,
* a write-access check,
* and a rewritten fix suggestion.

### Negative evidence is overinterpreted

`check_role_grants()` returns the same default structure when:

* there are no relevant grants,
* `SHOW GRANTS` fails,
* the role is invalid,
* or cursor operations fail.

`root_cause._apply_verdict()` can interpret an empty grant result plus an empty table listing as `never_built` with high confidence. Failure, invisibility, inherited-role grants, and genuine absence are not distinguished.

### Write access is modeled incorrectly

`check_write_access()` has one `has_usage` boolean. It sets it for either database-level or schema-level USAGE. Those are separate requirements.

If the role has database USAGE but lacks schema USAGE, `has_usage` becomes true, and `_check_write_access_for_unmaterialized()` will not generate the missing schema-USAGE grant.

### Cursor management is inconsistent

Most wrappers use a `finally`, but create the cursor before the `try`:

```python
cursor = conn.cursor()
try:
    ...
```

A failure in `conn.cursor()` escapes their “never raises” contract. `cursor.close()` can also raise from the `finally`.

`grants.py` is worse: `check_role_grants()`, `check_write_access()`, and `get_current_role()` do not close their cursors at all.

### Identifier handling is inconsistent

* `params.py` validates parameter names.
* `schema_inspector.py` validates object names.
* `grants.py` interpolates `role_name` directly into `SHOW GRANTS TO ROLE {role_name}` without validation or quoting.

### Judgment

The metadata-access layer should be internally replaced with one typed gateway. This is not a reason to rewrite classifiers or the entire package.

## 2.6 State and mutation: under-abstracted

`enrich_reports()` explicitly modifies reports in place. It then performs ordered mutation passes:

1. class-gated enrichment,
2. lineage enrichment,
3. contract reconciliation,
4. write-access rewriting.

`_reconcile_findings()` replaces `fix_suggestion`. `_check_write_access_for_unmaterialized()` prepends more prose to the same field.

The result depends on call order, and evidence is lost inside rewritten text. A consumer cannot reliably distinguish:

* the classifier's original suggestion,
* a live confirmation,
* a warning,
* and the final resolution.

`RootCauseGroup` then holds another parallel verdict rather than updating a single structured resolution.

### Judgment

The pipeline should return new reports with appended structured evidence and a resolved verdict. Rendering should create prose last.

## 2.7 String and type-tag dispatch

### The local `if/elif` logic is mostly fine

The following are appropriate procedural code:

* ordered classifier matching in `CLASSIFIER_REGISTRY`,
* subtype selection inside `RuntimeErrorClassifier.diagnose()`,
* data-error subtype selection,
* artifact-kind normalization,
* the small timestamp reconciliation decision tree.

These are small, closed decision sets. Replacing every branch with subclasses or visitor objects would make the code harder to follow.

### The harmful string dispatch is cross-layer repetition

The problem is the same `error_class` tag selecting behavior independently in multiple layers.

`enrich_reports()`:

```python
if report.error_class == "contract_violation":
    ...
elif report.error_class == "runtime_error":
    ...
```

`_reconcile_findings()` repeats the contract tag. `group_reports()` branches on error-class strings. Templates are selected by concatenating the error-class string into a file path.

This already causes an observable omission: `TimeoutErrorClassifier` sets:

```python
session_params_to_check=["STATEMENT_TIMEOUT_IN_SECONDS"]
```

but live parameter enrichment is only invoked for `contract_violation`. Timeout findings request live information that the pipeline never gathers.

Template dispatch is also unsafe:

```jinja2
{% include 'findings/' + report.error_class + '.j2' ignore missing %}
```

A new classifier with findings but no template silently renders nothing. `generic.j2` exists but is not used as the fallback.

### Recommendation

Keep procedural matching in one place. Replace repeated cross-layer string dispatch with:

* a typed `FindingKind` or `ErrorClass`,
* explicit enrichment requests or capabilities,
* one verdict-resolution stage,
* and a validated template mapping with a generic fallback.

The important change is centralization, not polymorphism.

## 2.8 Compatibility subsystem: strong concept, incomplete contract

The compatibility package is one of the better-designed parts:

* `SchemaDoc` has a focused purpose.
* `Presence` captures presence, requiredness, types, and nullability.
* `safe.py` provides narrow, never-raising accessors.
* Acquisition is separate from runtime.
* Schema checks are offline.

However, its “single source of truth” claim is not true in the shown code.

### `safe.py` does not consume the registry

`safe.py` manually hardcodes aliases such as:

```python
_first(node, "compiled_code", "compiled_sql")
```

It does not import or derive behavior from `consumed_paths.REGISTRY`. Synchronization is manual, even if tests elsewhere may compare them.

### The registry is not the full set of consumed paths

The registry says it is:

> “The full set of dict paths the classifiers/enrichers read today”

Shown code also reads, among others:

* `results[].timing[].name`
* `results[].timing[].completed_at`
* `results[].failures`
* `results[].compiled_code`
* `nodes[].path`
* `nodes[].columns[].data_type`
* `sources[].relation_name`
* `parent_map`
* top-level `sources`

Those are absent from `REGISTRY`.

Notably, `safe.node_compiled_code()` is called on run-results entries, while the registry only declares `manifest.nodes[].compiled_code`.

### The schema gate discards most of its own model

`Presence` records:

* per-definition presence,
* requiredness,
* types,
* nullability.

`schema_diff.py` reduces that to:

```python
present_anywhere(...)
```

A field could disappear from every model node but remain on one unrelated union member and still be considered present. A type change from string to object would also pass.

### Judgment

The compatibility architecture is **well chosen but incompletely implemented**. Preserve the schema walker and registry concept; centralize all artifact reads and make the gate compare relevant definitions and types.

## 2.9 Grouping and rendering: overlapping abstractions

There are two parallel group models:

* `grouping.ReportGroup`
* `root_cause.RootCauseGroup`

Both contain reports, titles, error-class-like tags, and combined presentation information.

`main` constructs root-cause groups. `renderer` separately constructs report groups from the complete report list. Root-cause member reports are not removed from ordinary grouping, so duplication is structural rather than incidental.

Rendering also differs from JSON behavior:

* text output includes `DiffResult`; JSON serialization does not,
* text can include live enrichment; `_finding_to_dict()` omits `enrichment`,
* lineage JSON omits `live_status`, `live_detail`, `relation_name`, and annotations,
* text uses `ReportGroup`; JSON does not expose those groups.

### Judgment

The renderer should consume an already assembled `AnalysisResult`. It should not decide grouping. One application-level grouping pass should establish what appears once, what is collapsed, and what remains ungrouped.

## 2.10 Configuration and CLI: serviceable, but duplicated

`main.py` is legitimately a fan-out hotspot, but several responsibilities should move out:

* project/profile resolution,
* artifact loading,
* analysis pipeline,
* live-connection lifecycle,
* output assembly,
* process exit.

Profile discovery is duplicated in:

* `discover.find_profiles_yml()`
* `enrichers.connection._find_profiles_yml()`

`.env` loading is also duplicated between `main._load_env_file()` and `connection._load_dotenv()`.

`parse_profile()` says it returns `None` if a profile “can't be found or parsed,” but it does not catch YAML parse errors, I/O errors, `yaml.safe_load()` returning `None`, or malformed profile shapes. `open_connection()` catches only `ValueError`.

`run_identity._is_lagging()` contains an entire duplicate implementation after an unconditional return path:

```python
except (ValueError, TypeError, AttributeError) as exc:
    logger.debug(...)
    return False
watermark = _history_watermark(conn)
```

Everything from the second `watermark` assignment onward is unreachable. `_to_aware_utc()` is effectively retained for that unreachable implementation.

These are targeted cleanup items, not reasons to replace the CLI.

---

# 3. Target design in concrete code

## Change 1: Preserve probe failure as “unknown”

### Before

From `schema_inspector.py`:

```python
def table_exists(conn, fq_table_name: str) -> Optional[bool]:
    """
    Check if a table exists by running SHOW TABLES.
    Returns True/False, or None if the check itself failed (e.g., no USAGE on schema).
    """
    if not _validate_fq_name(fq_table_name):
        return None

    parts = fq_table_name.split(".")
    db, schema, table = parts
    cursor = conn.cursor()
    try:
        cursor.execute(f"SHOW TABLES LIKE '{table}' IN {db}.{schema}")
        rows = cursor.fetchall()
        return len(rows) > 0
    except Exception:
        return None
    finally:
        cursor.close()
```

From `enrich.py`:

```python
        if exists:
            step.live_status = "exists"
            ...
        else:
            step.live_status = "missing"
            step.live_detail = "table does NOT exist in Snowflake"
```

### After

```python
# dbt_diagnostics/enrichers/metadata.py
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, Iterator, TypeVar

T = TypeVar("T")


class ProbeStatus(StrEnum):
    OK = "ok"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ProbeResult(Generic[T]):
    status: ProbeStatus
    value: T | None = None
    reason: str | None = None

    @classmethod
    def ok(cls, value: T) -> "ProbeResult[T]":
        return cls(status=ProbeStatus.OK, value=value)

    @classmethod
    def unavailable(cls, reason: str) -> "ProbeResult[T]":
        return cls(status=ProbeStatus.UNAVAILABLE, reason=reason)


@dataclass(frozen=True)
class WriteAccess:
    database_usage: bool
    schema_usage: bool
    create_table: bool


class SnowflakeMetadata:
    def __init__(self, conn: Any) -> None:
        self._conn = conn

    @contextmanager
    def _cursor(self) -> Iterator[Any]:
        cursor = None
        try:
            cursor = self._conn.cursor()
            yield cursor
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass

    def table_exists(self, fq_name: str) -> ProbeResult[bool]:
        if not _validate_fq_name(fq_name):
            return ProbeResult.unavailable("invalid fully-qualified identifier")

        db, schema, table = fq_name.split(".")
        try:
            with self._cursor() as cursor:
                cursor.execute(
                    f"SHOW TABLES LIKE '{table}' IN {db}.{schema}"
                )
                return ProbeResult.ok(bool(cursor.fetchall()))
        except Exception as exc:
            return ProbeResult.unavailable(type(exc).__name__)

    def write_access(
        self, role_name: str, schema_fq: str
    ) -> ProbeResult[WriteAccess]:
        # One implementation owns identifier validation, cursor lifecycle,
        # grant interpretation, and inherited/unknown limitations.
        ...
```

Call site:

```python
probe = metadata.table_exists(step.relation_name)

if probe.status == ProbeStatus.UNAVAILABLE:
    step.live_status = None
    step.live_detail = f"unverified: {probe.reason}"
elif probe.value is True:
    step.live_status = "exists"
    step.live_detail = "table exists"
else:
    step.live_status = "missing"
    step.live_detail = "table does NOT exist in Snowflake"
```

This one distinction prevents failed probes from becoming false high-confidence diagnoses.

---

## Change 2: Represent lineage as edges, not BFS adjacency

### Before

From `enrich.py`:

```python
    for i in range(len(trail) - 1):
        current = trail[i]
        next_step = trail[i + 1]
        if _is_passing(current) and _is_failing(next_step):
            finding.disconnect = DisconnectVerdict(
                between_node_a=next_step.short_name,
                between_node_b=current.short_name,
                explanation=_build_verdict_text(current, next_step, finding),
                confidence="high" if next_step.live_status else "medium",
            )
            return
```

### After

```python
# dbt_diagnostics/models.py
from dataclasses import dataclass, field


@dataclass(frozen=True)
class LineageEdge:
    upstream_id: str
    downstream_id: str


@dataclass
class LineageGraph:
    root_id: str
    nodes: dict[str, LineageStep] = field(default_factory=dict)
    edges: list[LineageEdge] = field(default_factory=list)

    def ordered_nodes(self) -> list[LineageStep]:
        return sorted(
            self.nodes.values(),
            key=lambda step: (step.depth, step.node_id),
        )
```

```python
# dbt_diagnostics/tracers/dag_walker.py
def trace_column_lineage(
    self,
    unique_id: str,
    column_name: str,
    max_depth: int = 5,
    run_results: RunResultsIndex | None = None,
) -> LineageGraph:
    root_node = self.get_node(unique_id)
    root = self._make_step(unique_id, root_node, depth=0)
    root.manifest_status = "declared"
    root.run_status = run_results.status(unique_id) if run_results else None

    graph = LineageGraph(root_id=unique_id, nodes={unique_id: root})
    queue: deque[tuple[str, str, int]] = deque(
        (parent_id, unique_id, 1)
        for parent_id in self.get_parents(unique_id)
    )
    visited: set[str] = {unique_id}

    while queue:
        node_id, downstream_id, depth = queue.popleft()
        graph.edges.append(
            LineageEdge(
                upstream_id=node_id,
                downstream_id=downstream_id,
            )
        )

        if node_id not in graph.nodes:
            node = self.get_node(node_id)
            step = self._make_step(node_id, node, depth)
            step.run_status = run_results.status(node_id) if run_results else None

            if node and self._node_has_column(node, column_name):
                step.manifest_status = "declared"
                step.manifest_detail = f"column '{column_name}' declared"
            else:
                # Absence on an arbitrary parent is not proof of failure.
                step.manifest_status = None
                step.manifest_detail = "column provenance not established"

            graph.nodes[node_id] = step

        if node_id in visited or depth >= max_depth:
            continue
        visited.add(node_id)

        for parent_id in self.get_parents(node_id):
            queue.append((parent_id, node_id, depth + 1))

    return graph
```

Disconnect resolution now examines real edges:

```python
def identify_disconnect(
    graph: LineageGraph,
    finding: DiagnosticFinding,
) -> DisconnectVerdict | None:
    candidates: list[tuple[LineageStep, LineageStep]] = []

    for edge in graph.edges:
        upstream = graph.nodes[edge.upstream_id]
        downstream = graph.nodes[edge.downstream_id]

        if _is_passing(downstream) and _is_failing(upstream):
            candidates.append((downstream, upstream))

    if not candidates:
        return None

    downstream, upstream = min(
        candidates,
        key=lambda pair: pair[1].depth,
    )
    return DisconnectVerdict(
        between_node_a=upstream.short_name,
        between_node_b=downstream.short_name,
        explanation=_build_verdict_text(downstream, upstream, finding),
        confidence="high" if upstream.live_status else "medium",
    )
```

Call sites and templates change from:

```python
finding.lineage_trail = lineage_trail
```

to:

```python
finding.lineage = dag_walker.trace_column_lineage(...)
finding.disconnect = identify_disconnect(finding.lineage, finding)
```

The renderer may still display `lineage.ordered_nodes()`, but verdict logic no longer relies on display order.

---

## Change 3: Enrich by explicit request, not `error_class`

### Before

From `enrich.py`:

```python
        for finding in report.findings:
            if report.error_class == "contract_violation":
                _enrich_contract_violation(conn, finding)
            elif report.error_class == "runtime_error":
                _enrich_runtime_error(conn, finding, report, result_data)

            # Enrich lineage trail steps with live DESCRIBE TABLE data
            if finding.lineage_trail:
                _enrich_lineage_trail(conn, finding)
```

### After

```python
# dbt_diagnostics/models.py
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EnrichmentRequest:
    parameters: tuple[str, ...] = ()
    relation: str | None = None
    column: str | None = None
    match_query_history: bool = False


@dataclass(frozen=True)
class Evidence:
    source: str
    name: str
    value: Any
    detail: str | None = None


@dataclass
class DiagnosticFinding:
    summary: str
    ...
    enrichment_request: EnrichmentRequest = field(
        default_factory=EnrichmentRequest
    )
    evidence: tuple[Evidence, ...] = ()
```

Classifiers declare what evidence they need:

```python
# timeout_error.py
return DiagnosticFinding(
    summary=summary,
    location=location,
    explanation=...,
    fix_suggestion=...,
    enrichment_request=EnrichmentRequest(
        parameters=("STATEMENT_TIMEOUT_IN_SECONDS",),
    ),
)
```

```python
# runtime_error.py
return DiagnosticFinding(
    summary=f"{summary_label} not found: {object_name}",
    location=location,
    explanation=explanation,
    fix_suggestion=fix,
    enrichment_request=EnrichmentRequest(
        relation=object_name,
        match_query_history=True,
    ),
    lineage=lineage,
)
```

The collector is class-agnostic:

```python
# dbt_diagnostics/enrichers/collector.py
from dataclasses import replace


class EvidenceCollector:
    def __init__(
        self,
        metadata: SnowflakeMetadata,
        run_results: RunResultsIndex,
    ) -> None:
        self._metadata = metadata
        self._run_results = run_results

    def collect_report(
        self,
        report: DiagnosticReport,
    ) -> DiagnosticReport:
        result = self._run_results.get(report.unique_id)
        findings = [
            self._collect_finding(finding, report, result)
            for finding in report.findings
        ]
        return replace(report, findings=findings)

    def _collect_finding(
        self,
        finding: DiagnosticFinding,
        report: DiagnosticReport,
        result: RunResultView | None,
    ) -> DiagnosticFinding:
        request = finding.enrichment_request
        evidence = list(finding.evidence)

        if request.parameters:
            values = self._metadata.parameters(request.parameters)
            if values.status == ProbeStatus.OK:
                evidence.append(
                    Evidence(
                        source="snowflake",
                        name="session_parameters",
                        value=values.value,
                    )
                )

        if request.relation:
            exists = self._metadata.table_exists(request.relation)
            evidence.append(
                Evidence(
                    source="snowflake",
                    name="relation_exists",
                    value=exists.value,
                    detail=exists.reason,
                )
            )

        if request.match_query_history and result is not None:
            match = self._metadata.match_query(result)
            if match.status == ProbeStatus.OK and match.value is not None:
                evidence.append(
                    Evidence(
                        source="snowflake",
                        name="query_history_match",
                        value=match.value,
                    )
                )

        return replace(finding, evidence=tuple(evidence))
```

Call site:

```python
collector = EvidenceCollector(
    metadata=SnowflakeMetadata(conn),
    run_results=run_index,
)
reports = [collector.collect_report(report) for report in reports]
reports = [resolve_verdicts(report) for report in reports]
```

A small typed branch inside `resolve_verdicts()` remains appropriate. What disappears is duplicated class-tag selection across enrichment, grouping, and rendering.

Narrative creation then happens after resolution:

```python
rendered_fix = format_fix(finding.verdict, finding.evidence)
```

rather than by repeatedly prepending strings to `fix_suggestion`.

---

## Change 4: Centralize run-results access and indexing

### Before

From `enrich.py`:

```python
def _find_result(run_results: dict, unique_id: str) -> Optional[dict]:
    """Find the run_results entry for a given unique_id."""
    for result in run_results.get("results", []):
        if result.get("unique_id") == unique_id:
            return result
    return None
```

Variants of this scan also appear in:

* `RuntimeErrorClassifier._get_run_status()`
* `DataErrorClassifier._get_run_status()`
* `DagWalker._build_run_status_map()`
* `run_identity._end_time_for()`

### After

```python
# dbt_diagnostics/compat/views.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from dbt_diagnostics.compat import safe


@dataclass(frozen=True)
class ExecuteWindow:
    started_at: str | None
    completed_at: str | None


@dataclass(frozen=True)
class RunResultView:
    raw: Mapping[str, Any]

    @property
    def unique_id(self) -> str | None:
        value = self.raw.get("unique_id")
        return value if isinstance(value, str) else None

    @property
    def status(self) -> str | None:
        value = self.raw.get("status")
        return value if isinstance(value, str) else None

    @property
    def message(self) -> str:
        value = self.raw.get("message")
        return value if isinstance(value, str) else ""

    @property
    def compiled_code(self) -> str | None:
        return safe.node_compiled_code(self.raw)

    @property
    def query_id(self) -> str | None:
        return safe.result_query_id(self.raw)

    def execute_window(self) -> ExecuteWindow | None:
        timing = self.raw.get("timing")
        if not isinstance(timing, list):
            return None

        for item in timing:
            if not isinstance(item, dict) or item.get("name") != "execute":
                continue
            started = item.get("started_at")
            completed = item.get("completed_at")
            return ExecuteWindow(
                started_at=started if isinstance(started, str) else None,
                completed_at=completed if isinstance(completed, str) else None,
            )
        return None


class RunResultsIndex:
    def __init__(self, artifact: object) -> None:
        self._by_id: dict[str, RunResultView] = {}
        self._by_query_id: dict[str, RunResultView] = {}

        raw_results = (
            artifact.get("results")
            if isinstance(artifact, dict)
            else None
        )
        for raw in raw_results if isinstance(raw_results, list) else []:
            if not isinstance(raw, dict):
                continue
            result = RunResultView(raw)
            if result.unique_id:
                self._by_id[result.unique_id] = result
            if result.query_id:
                self._by_query_id[result.query_id] = result

    def get(self, unique_id: str) -> RunResultView | None:
        return self._by_id.get(unique_id)

    def status(self, unique_id: str) -> str | None:
        result = self.get(unique_id)
        return result.status if result else None

    def end_time_for_query(self, query_id: str) -> str | None:
        result = self._by_query_id.get(query_id)
        if result is None:
            return None
        window = result.execute_window()
        return window.completed_at if window else None
```

Composition changes once:

```python
run_index = RunResultsIndex(run_results)

context = DiagnosticContext(
    dag_walker=dag_walker,
    column_tracer=column_tracer,
    models_dir=paths["models_dir"],
    compiled_dir=paths["compiled_dir"],
    manifest=manifest,
    run_results=run_index,
    catalog=catalog,
)
```

Then:

```python
result_data = run_index.get(report.unique_id)
parent_status = run_index.status(parent_id)
run_end_time = run_index.end_time_for_query(query_id)
```

All raw artifact `.get()` access should be confined to compatibility/view modules. `consumed_paths.REGISTRY` must then include every path those views read, including timing names and completion timestamps, run-result compiled code, failures, source relation names, parent maps, and column data types.

---

# 4. Rewrite versus refactor

## Decision

**Option (c): substantial refactor of specific subsystems.**

Not option (a): there are real structural correctness faults.

Not option (b): the required changes cross central models, lineage, enrichment, root-cause resolution, and rendering. These are not isolated cleanups.

Not option (d): the package's major boundaries, parsing knowledge, compatibility code, templates, and tracing utilities remain useful. Rebuilding them would discard working domain logic without solving a fundamentally irredeemable architecture.

## Subsystems to refactor substantially

### 1. Lineage and disconnect resolution

Touch:

* `models.py`
* `tracers/dag_walker.py`
* `classifiers/runtime_error.py`
* `classifiers/schema_change_error.py`
* `classifiers/data_error.py`
* `enrichers/enrich.py`
* lineage templates

Replace the flat trail contract with a graph/path contract. This has high behavioral risk because existing outputs may encode incorrect sibling boundaries, but that is precisely why the change is necessary.

### 2. Live metadata and role/grant probing

Touch or internally replace:

* `enrichers/schema_inspector.py`
* `enrichers/grants.py`
* `enrichers/params.py`
* `enrichers/query_history.py`
* `enrichers/run_identity.py`
* `enrichers/enrich.py`
* `root_cause.py`

Introduce one gateway with:

* guaranteed cursor cleanup,
* identifier validation,
* typed success/unavailable results,
* separate database/schema usage facts,
* explicit query-match confidence,
* typed role identity and provenance.

The existing SQL statements and matching algorithms can mostly be retained.

### 3. Diagnosis/evidence/verdict model

Touch:

* `models.py`
* all classifiers to populate typed observations/requests
* `enrichers/enrich.py`
* `root_cause.py`
* `grouping.py`
* `renderer.py`
* templates
* JSON serialization

Keep current JSON keys for compatibility and add structured evidence/verdict fields additively. Stop using mutable fix text as the storage medium for live facts.

### 4. Artifact access and compatibility contract

Touch:

* `compat/safe.py`
* `compat/consumed_paths.py`
* new `compat/views.py`
* `classifiers/base.py`
* `main.py`
* `dag_walker.py`
* `run_identity.py`
* `enrich.py`
* `schema_diff.py`

Centralize reads, complete the registry, and compare type/requiredness and relevant union members rather than only `present_anywhere()`.

## Components worth keeping

Keep with small or no structural changes:

* `schema_version.py`
* most of `schema_model.py`
* most of `path_resolver.py`
* classifier registry ordering
* regex parsers in individual classifiers
* `snippet.py`
* most of `ColumnTracer`'s sqlglot logic
* `diff_tracer.py`
* `colors.py`
* `load_json()` and `ArtifactLoadError`
* Jinja templates as presentation assets, after changing their input view model

## Cost and risk

| Work                   | Relative cost | Main risk                                                                               |
| ---------------------- | ------------- | --------------------------------------------------------------------------------------- |
| Typed metadata gateway | Medium        | Changing distinctions between absent and unverified will alter verdicts, intentionally. |
| Lineage graph          | High          | Golden text outputs and branching-DAG expectations will change.                         |
| Evidence/verdict model | High          | Central model and JSON/template migration.                                              |
| Artifact index/views   | Medium        | Broad but mostly mechanical call-site changes.                                          |
| Group/render assembly  | Medium        | Avoiding duplicate output while preserving familiar formatting.                         |

The safest migration is additive:

1. Fix immediate correctness defects without changing the public shape.
2. Add `ProbeResult`, metadata gateway, and run-results index behind adapters.
3. Add a lineage graph while temporarily exposing `ordered_nodes()` to old templates.
4. Add structured evidence/verdict fields while retaining existing summary/fix fields.
5. Move grouping out of the renderer and eliminate duplicate root-cause rendering.
6. Deprecate the old mutable enrichment fields after the new JSON/text paths are stable.

## Immediate fixes before the structural work

These should not wait for the larger refactor:

* Preserve `table_exists() is None` as unverified.
* Close every cursor in `grants.py`.
* Split database USAGE and schema USAGE.
* Remove the unreachable duplicate half of `run_identity._is_lagging()`.
* Replace `t["name"]` with validated timing-entry access in `_enrich_runtime_error()`.
* Catch YAML/I/O/shape failures in `parse_profile()` and `_load_config()`.
* Give template dispatch an explicit `generic.j2` fallback.
* Do not run disconnect inference on data-error trails or other findings without a missing-object/column hypothesis.

# Final structural decisions

1. **Keep the current package-level decomposition.**
2. **Keep the classifier registry and local procedural matching.**
3. **Replace the flat lineage list contract.**
4. **Replace the live-probe return conventions and grant dictionaries.**
5. **Separate observations, evidence, verdicts, and rendered text.**
6. **Centralize artifact reads and make the compatibility registry truthful.**
7. **Move grouping out of the renderer and produce one assembled analysis result.**
8. **Do not perform a full package rewrite.**
9. **Perform a substantial refactor of lineage, live verification, and report resolution.**
