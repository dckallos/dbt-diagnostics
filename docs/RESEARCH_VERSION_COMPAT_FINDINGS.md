# Research findings (append-only journal)

Each entry below is one logged finding; newest at the bottom. Resume from the last entry after any interruption.

## [2026-06-16T21:46:21Z] RESUME -- session start: skeleton + progress checklist

Research target: cross-version compatibility for `dbt-diagnostics` (live, post-hoc,
database-grounded root-cause analysis; NOT linting, NOT pre-run static analysis).
Fresh start -- findings file did not previously exist. Begin at Deliverable A.

## Progress checklist (flip TODO -> DONE as each completes)

- [x] A. Schema-version history table (Q1) + dbt-core -> schema mapping (Q2)  -- DONE (catalog/sources majors marked CONFIRM)
- [x] B. Acquisition/storage strategy (Q5) + adopt-vs-build dbt-artifacts-parser (Q11) + dir layout + add-a-version rule -- DONE
- [x] C. Field-level compatibility risk list (Q4) keyed to exact dict paths -- DONE
- [x] D. Test matrix + fixture-generation plan (Q6) -- DONE
- [x] E. Prioritized additive implementation plan as GitHub-issue stubs -- DONE
- [x] F. Surface-and-source map (Q8/Q9) incl. events + per-tag relocation -- DONE (split-release tags approximate)
- [x] G. Discovery logs: unknown-unknowns, open-questions, searches-I-ran, self-critique -- DONE
- [x] H. Sources -- DONE

## Section anchors (populated incrementally below; newest entries at bottom)

- Deliverable A -- schema version history & mapping
- Deliverable B -- acquisition strategy & adopt-vs-build
- Deliverable C -- field-level compatibility risk
- Deliverable D -- test matrix & fixtures
- Deliverable E -- implementation plan (issues)
- Deliverable F -- surface-and-source map
- Deliverable G -- discovery logs
- Deliverable H -- sources

## [2026-06-16T21:48:23Z] Q4 -- C-scaffold: exact dict paths the code reads (repo ground truth, no web)

Confirmed by grep over `dbt_diagnostics/{classifiers,enrichers,root_cause.py,grouping.py,models.py}`
(fixtures/ and tests/ excluded). These are the dict paths whose cross-version
stability determines whether the tool keeps working on a new dbt schema. The risk
column (absent/renamed-by-version) is filled in by the web-research phase.

Source ground truth (verified in repo, not assumed):
- `schema_version.py`: `SUPPORTED_SCHEMAS = {"manifest": {12}, "run-results": {6}}`,
  validated against dbt-core 1.11.x. Detection reads `metadata.dbt_schema_version`
  (URL regex `/dbt/<kind>/v<major>`) and `metadata.dbt_version`; degrades to
  `kind="unknown", supported=False` and NEVER raises.
- `discover.py` resolves only `target/manifest.json` and `target/run_results.json`
  (plus compiled_dir, models_dir). catalog/sources/semantic_manifest NOT resolved.

run_results.json paths read (per-result objects in `results[]`):
| dict path | where used |
| --- | --- |
| `results[].status` | base/runtime/data classifiers, run_identity (status gate) |
| `results[].message` | base classifier (error text) |
| `results[].timing` | base, enrich.py:216, run_identity:43/46 (node timing for query-history correlation) |
| `results[].execution_time` | timing/duration |
| `results[].unique_id` | join key to manifest nodes |
| `results[].adapter_response` | run_identity:41, test_failure:179 (Snowflake fields) |
| `results[].adapter_response.query_id` | run_identity:42, test_failure:180 (Snowflake query_id -> query history) |
| `metadata.dbt_schema_version`, `metadata.dbt_version` | schema_version.py |

manifest.json paths read (per-node objects in `nodes[]` / `sources[]`):
| dict path | where used |
| --- | --- |
| `nodes[].relation_name` | runtime_error:439/444/457, data_error:108/131 (DB object name) |
| `nodes[].depends_on` (.nodes) | test_failure:146 (lineage) |
| `nodes[].columns` | schema-drift / contract checks |
| `nodes[].compiled_code` | base:50, enrich:219, test_failure:62 |
| `nodes[].raw_code` | model SQL |
| `nodes[].original_file_path` | data_error:107/130, test_failure:84 (file locality) |
| `nodes[].resource_type`, `nodes[].unique_id` | node identity/typing |

RISK NOTE (to confirm via web): `adapter_response` and `query_id` live in
`dbt-adapters` (Snowflake), not dbt-core, and `relation_name` population /
`compiled_code` vs `compiled_sql` naming have shifted historically -- these are
the highest-risk paths for cross-version breakage. Flagged for Q4/Q10 search.

## [2026-06-16T21:48:46Z] SURFACE -- F-scaffold: dbt data-processing surface classified (source-locations TODO per tag)

Full surface from the prompt, classified input/output + format + consumed-today.
Source-location-per-tag and version-range cells marked TODO are filled by the
web phase. Consumed-today verified against discover.py (manifest + run_results only).

| representation | in/out | format | consumed today | source/def location (per tag: TODO) |
| --- | --- | --- | --- | --- |
| dbt_project.yml | input | YAML | no | dbt-core project config schema |
| schema.yml (properties: models/sources/tests/exposures/metrics/semantic_models/unit_tests) | input | YAML | no | dbt-core parser/schemas |
| selectors.yml | input | YAML | no | dbt-core |
| packages.yml / dependencies.yml | input | YAML | no | dbt-core deps |
| profiles.yml | input | YAML | no (discover.py reads target only) | dbt-core/adapters |
| model .sql / .py, seeds .csv, snapshots, macros, analyses, docs blocks | input | text/CSV | no | dbt-core |
| target/manifest.json | output | JSON | YES (v12 gate) | core/dbt/artifacts/schemas/manifest (>=1.8); contracts/graph/manifest.py (<=1.7) |
| target/run_results.json | output | JSON | YES (v6 gate) | core/dbt/artifacts/schemas/run_results (>=1.8); contracts/results.py (<=1.7) |
| target/catalog.json (dbt docs generate) | output | JSON | candidate | artifacts/schemas/catalog (>=1.8); contracts/results.py (<=1.7) |
| target/sources.json (dbt source freshness) | output | JSON | candidate | artifacts/schemas/freshness (>=1.8); contracts/results.py (<=1.7) |
| target/semantic_manifest.json | output | JSON | candidate | dbt-semantic-interfaces (separate repo) -- TODO confirm |
| target/compiled/**, target/run/** | output | SQL text | partially (compiled_dir resolved) | filesystem, no schema |
| graph_summary.json | output | JSON | no | dbt-core graph |
| graph.gpickle | output | pickle (networkx) | no | dbt-core graph |
| partial_parse.msgpack | output | msgpack | no (stale cache = failure cause) | dbt-core parser |
| logs/dbt.log, --log-format json | output | text / JSON-lines | no | dbt-common events (protobuf), types.py/types_pb2.py |

RELOCATION HAZARDS (prompt-VERIFIED; do not assume latest layout on old tags):
- Artifact dataclasses: `core/dbt/artifacts/` from v1.8.0 onward; ABSENT at v1.7.0
  where they live in `core/dbt/contracts/` (results.py: RunResultsArtifact,
  CatalogArtifact, freshness/sources artifact; manifest in contracts/graph/manifest.py).
- Schema majors shift with the move: run-results is v5 at v1.7.0, v6 by 1.11.
  Confirm the major PER TAG.
- `dbt-common` is its own repo; owns structured events (`dbt_common/events/`
  types.py + types_pb2.py protobuf), event manager/logger, mashumaro mixin.
  Extraction completed ~1.5/1.6 -- exact release TODO.
- `dbt-adapters` is its own monorepo (dbt-snowflake/, dbt-postgres/...).
  `adapter_response` + Snowflake `query_id` live there, not dbt-core. Split ~1.8 -- exact release TODO.

## [2026-06-16T21:49:22Z] Q1 -- A: schemas.getdbt.com hosted schema index (manifest v5-v12 visible)

SEARCH #1: "dbt artifacts manifest schema version history ... schemas.getdbt.com".

Confirmed (schemas.getdbt.com index page): Manifest schemas published and hosted:
v12, v11, v10, v9, v8, v7, v6, v5 (each available raw). The site also hosts
catalog, run_results (run-results), sources, and semantic_manifest schema
directories. URL pattern: https://schemas.getdbt.com/dbt/<kind>/v<N>.json and a
browsable https://schemas.getdbt.com/dbt/<kind>/v<N>/index.html (e.g.
manifest/v12 -> title "WritableManifest").

Key facts to carry forward:
- manifest.json version is RELATED TO but NOT EQUAL to dbt version; the correct
  manifest version must be matched to the dbt version (dbt docs). Schema can bump
  in ANY minor (v1.x.0), not just majors (phData/dbt docs).
- Maintenance model: schemas.getdbt.com repo is updated by diffing freshly
  generated artifacts vs the committed schema, filtering out version/date noise
  (github.com/dbt-labs/schemas.getdbt.com README).
- Anomaly to reconcile: dbt-core issue #10163 claimed "v12 is not a valid manifest
  version ... for an unreleased version of dbt" -- i.e. v12 appeared on
  schemas.getdbt.com BEFORE the dbt release that emits it shipped. Implication for
  us: the hosted schema index can lead the released engine; do not infer
  dbt-core release from schema presence alone. (Confirm which release shipped v12.)

Confirmed lower bound: v5 is the earliest manifest schema still listed on the
index page shown; older majors (v1-v4) existed but may not be on the front index
-- confirm full v1..v4 range from dbt-core source/changelog next.

URLs:
- https://schemas.getdbt.com/
- https://schemas.getdbt.com/dbt/manifest/v12/index.html
- https://github.com/dbt-labs/schemas.getdbt.com
- https://docs.getdbt.com/reference/artifacts/manifest-json
- https://docs.getdbt.com/reference/artifacts/dbt-artifacts
- https://github.com/dbt-labs/dbt-core/issues/10163
- https://docs.getdbt.com/docs/dbt-versions/core-upgrade/Older%20versions/upgrading-to-v1.1

## [2026-06-16T21:51:50Z] SURFACE -- Deliverable C scaffold: exact dict paths the code reads (repo-derived, no web)

Confirmed by grepping dbt_diagnostics/{classifiers,enrichers,root_cause.py,grouping.py,models.py}
(fixtures/tests excluded). These are the live dict-access patterns whose
cross-version stability must be checked (Q4). Counts are source-occurrences.

Ground truth from dbt_diagnostics/schema_version.py (verified by Read):
- SUPPORTED_SCHEMAS = {"manifest": {12}, "run-results": {6}} (validated vs dbt-core 1.11.x).
- Version detected from artifact's own metadata.dbt_schema_version URL
  (regex /dbt/<kind>/v<major>); falls back to top-level-shape inference
  ("results" -> run-results, "nodes" -> manifest).
- Contract: detection NEVER raises; unknown/unvalidated version -> supported=False
  + note, keep parsing. Degrade-to-unverified, never crash.
- Consumes ONLY target/manifest.json + target/run_results.json today, as plain dicts
  (discover.py resolves paths; no catalog/sources/semantic_manifest yet).

run_results.json paths read (per-result and top-level):
| dict path | where | notes |
| --- | --- | --- |
| results[].status | classifiers (runtime/data), run_identity, base | core status enum |
| results[].message | base classifier | error text |
| results[].timing | run_identity, enrich, base | list of {name,started_at,completed_at} |
| results[].execution_time | enrich | float seconds |
| results[].unique_id | most classifiers | join key to manifest.nodes |
| results[].adapter_response | run_identity, test_failure | per-adapter; Snowflake query_id lives here |
| results[].adapter_response.query_id | run_identity, test_failure | Snowflake-specific; query-history correlation |
| results[].thread_id | (fixtures) | present in artifacts |
| metadata.dbt_schema_version | schema_version | gate |
| metadata.dbt_version | schema_version | informational |

manifest.json paths read:
| dict path | where | notes |
| --- | --- | --- |
| nodes | schema_version (shape), enrichers | top-level node map |
| nodes[].relation_name | runtime_error, data_error | FQ relation; nullable for some types |
| nodes[].compiled_code | base, test_failure, enrich | the compiled SQL |
| nodes[].raw_code | (candidate) | source SQL |
| nodes[].depends_on(.nodes) | test_failure | lineage edges |
| nodes[].columns | (candidate / catalog) | column metadata |
| nodes[].original_file_path | data_error, test_failure | source location |
| nodes[].resource_type | grouping/models | model/test/seed/... |
| sources | (referenced) | top-level sources map |

These rows are the keys against which each schema version must be checked for
add/remove/rename (Deliverable C). Source-location and per-version absence cells
to be filled by web research per git tag.

## [2026-06-16T21:52:34Z] SURFACE -- repo ground truth (no-search): current consumption + schema gate

### Deliverable C scaffold + ground truth (verified by reading the repo, no web search)

Current consumption (verified):
- `dbt_diagnostics/discover.py` resolves ONLY `target/manifest.json` and
  `target/run_results.json` (plus `target/compiled/` dir path). `catalog.json`,
  `sources.json`, `semantic_manifest.json` are NOT resolved/consumed today.
- `dbt_diagnostics/schema_version.py`: `SUPPORTED_SCHEMAS = {"manifest": {12},
  "run-results": {6}}`. Validated against dbt-core 1.11.x. Detection via
  `metadata.dbt_schema_version` URL regex `/dbt/(?P<kind>[a-z_-]+)/v(?P<major>\d+)`.
  Contract: never raises; unknown version -> supported=False + note, keep parsing.
  Shape fallback: `results` key => run-results, `nodes` key => manifest.

Exact dict-access paths the code depends on (grepped from classifiers/ enrichers/
root_cause.py; these are the paths Deliverable C must risk-assess per version):

| dict path | where read (sample) | notes |
| --- | --- | --- |
| `results[].status` | run_identity.py, data_error.py, runtime_error.py | run_results |
| `results[].message` | base.py | run_results |
| `results[].timing` (list of {name,started_at,completed_at}) | enrich.py:216, run_identity.py:43-46 | run_results |
| `results[].execution_time` | (run_results) | timing total |
| `results[].adapter_response` (-> `query_id`, `rows_affected`) | run_identity.py:41-42, test_failure.py:179-180 | adapter-specific; Snowflake query_id |
| `results[].unique_id` / `.thread_id` | enrich.py:374, run_identity | run_results (unique_id present from rr v? confirm) |
| `nodes[].relation_name` | runtime_error.py:439-457, data_error.py:108-131 | manifest |
| `nodes[].depends_on.nodes` | test_failure.py:146 | manifest |
| `nodes[].columns` | (schema drift) | manifest |
| `nodes[].compiled_code` / `.raw_code` | base.py:50, enrich.py:219, test_failure.py:62 | manifest; raw_sql/compiled_sql in older versions (CONFIRM rename) |
| `nodes[].original_file_path` | test_failure.py:84, data_error.py:107-130 | manifest |
| `nodes[].resource_type` / `.unique_id` | base.py:48 | manifest |
| `metadata.dbt_schema_version` / `.dbt_version` | schema_version.py | both artifacts |

TODO (needs web): per-version absence/rename flags for each path above,
especially `compiled_code`/`raw_code` (suspected older `compiled_sql`/`raw_sql`),
`relation_name` (introduction version), `adapter_response` (dbt-adapters split).

## [2026-06-16T21:53:00Z] SURFACE -- F scaffold (no-search): full data-processing surface + relocation hazards

### Deliverable F scaffold -- full surface classified (source-location cells = TODO confirm per tag)

| representation | in/out | format | consumed today | source-of-definition (TODO confirm per git tag) | post-hoc value |
| --- | --- | --- | --- | --- | --- |
| dbt_project.yml | input/config | YAML | no | dbt-core config parser | project-level defaults, target paths |
| schema.yml (properties: models/sources/tests/exposures/metrics/semantic_models/unit_tests) | input | YAML | no (via manifest) | dbt-core parser | declared grain/tests, contract defs |
| selectors.yml / packages.yml / dependencies.yml / profiles.yml | input | YAML | profiles via discover.py | dbt-core | which nodes selected; deps |
| model .sql / .py, seeds .csv, snapshots, macros, analyses, docs blocks | input | SQL/Py/CSV/Jinja | no (raw_code in manifest) | dbt-core | raw source for compile-error context |
| target/manifest.json | output | JSON | YES | core/dbt/artifacts/schemas/manifest (1.8+); contracts/graph/manifest.py (<=1.7) | node graph, compiled/raw code, columns, depends_on |
| target/run_results.json | output | JSON | YES | artifacts/schemas/run_results (1.8+); contracts/results.py (<=1.7) | status, timing, message, adapter_response |
| target/catalog.json (dbt docs generate) | output | JSON | no -- CANDIDATE | artifacts/schemas/catalog | live column types -> schema-drift |
| target/sources.json (dbt source freshness) | output | JSON | no -- CANDIDATE | artifacts/schemas/freshness; contracts/results.py (<=1.7) | stale-source diagnosis |
| target/semantic_manifest.json | output | JSON | no -- CANDIDATE | dbt-semantic-interfaces | semantic-layer breakage |
| target/compiled/**.sql, target/run/**.sql | output | SQL text | dir path only | dbt-core writes | EXACT SQL sent -- top post-hoc evidence |
| graph_summary.json | output | JSON | no | dbt-core graph | DAG shape |
| graph.gpickle | output | pickle (networkx) | no | dbt-core | DAG; version/pickle risk |
| partial_parse.msgpack | output/cache | msgpack | no | dbt-core parser | STALE CACHE is itself a failure cause |
| logs/dbt.log + --log-format json | output | text / JSON-lines | no -- CANDIDATE | dbt-common events (protobuf types_pb2) | per-node SQL error text, adapter error codes, timing |

### Relocation hazards (stated VERIFIED in prompt; re-confirm exact split tags via web)
- Artifact dataclasses: `core/dbt/artifacts/` from 1.8+; `core/dbt/contracts/`
  at <=1.7 (v1.7.0 contracts/results.py = RunResultsArtifact/CatalogArtifact/
  freshness; manifest in contracts/graph/manifest.py). Schema majors shift with
  the move: run-results v5 at 1.7.0 -> v6 by 1.11. CONFIRM major per tag.
- dbt-common is its own repo: owns structured events (`dbt_common/events/types.py`
  + `types_pb2.py` protobuf), event manager/logger, mashumaro mixin. Extraction
  completed ~1.5/1.6 -- PIN exact release.
- dbt-adapters is its own monorepo (dbt-snowflake/, dbt-postgres/...).
  `adapter_response` + Snowflake `query_id` live there, not dbt-core. Split ~1.8 --
  PIN exact release.

So "the right files" span THREE repos (dbt-core, dbt-common, dbt-adapters) and
shift by version; resolve paths per tag, never trust latest layout for old tags.

## [2026-06-16T21:53:28Z] Q1 -- schemas.getdbt.com index: manifest v5-v12, sources v3 (partial)

### Deliverable A -- schema version history (partial, building row-by-row)

From https://schemas.getdbt.com/ index (search-confirmed) the Manifest list shows:
v12, v11, v10, v9, v8, v7, v6, v5 (each has a `(raw)` JSON). So manifest schema
majors published = v5..v12 (lower majors v1-v4 existed in pre-1.0 / early 1.x but
the hosted index top page lists v5+; CONFIRM v1-v4 existence + dbt mapping next).

Other artifacts (to fill in): run-results current = v6; sources current = v3
(per schemas.getdbt.com repo README diff example: manifest/v12, run-results/v6,
sources/v3). catalog + semantic_manifest majors still TODO.

Anchor data point (Q2 mapping): Manifest v6 was introduced for dbt-core v1.2
("Bump manifest schema to v6 for v1.2", dbt-core#5417; docs issue #1667). The
only change for v6 was the default value of `config` for parsed nodes.

schemas.getdbt.com bump rule (from repo README): a schema major is bumped only
when a diff (excluding default/description changes) shows substantial changes;
pure default/description changes do NOT bump the major. => majors are coarse;
within a major, additive default/description changes can still occur.

Sources used (add to H):
- https://schemas.getdbt.com/
- https://github.com/dbt-labs/schemas.getdbt.com
- https://github.com/dbt-labs/docs.getdbt.com/issues/1667

## [2026-06-16T21:53:57Z] Q2 -- manifest version -> dbt-core release mapping (1.0-1.11)

### Deliverable A -- dbt-core minor -> manifest schema major (search-confirmed)

| dbt-core | manifest major | evidence |
| --- | --- | --- |
| 1.0 / 1.1 | v4 / v5 | (v5 is oldest on hosted index; CONFIRM 1.0=v4,1.1=v5 next) |
| 1.2 | v6 | dbt-core#5417; only change = default of `config` for parsed nodes |
| 1.3 | v7 | "Upgrading to v1.3: updated manifest schema version to v7" |
| 1.4 | v8 | "Upgrading to v1.4 / manifest v8"; `root_path` REMOVED for most node types in v1.4/v8 (still present for seeds) |
| 1.5 | v9 | (v9 between v8@1.4 and v10@1.6; CONFIRM) |
| 1.6 | v10 | "Upgrading to v1.6: manifest schema version is now v10" |
| 1.7 | v11 | v1.7.0 release notes: "Bump manifest schema version to v11, freeze manifest v10 (#8333)" |
| 1.8 / 1.9 / 1.10 / 1.11 | v12 | v12 current; matches repo gate (SUPPORTED manifest:{12}); CONFIRM whether 1.8 already emits v12 or v12 began later |

KEY field-evolution data point (-> Deliverable C):
- `root_path` removed for most node types at dbt 1.4 / manifest v8 (kept for seeds).
  Any code reading nodes[].root_path would break on >=1.4. (Not in our path list,
  but signals the kind of removal to expect.)

REAL-WORLD BREAKAGE (Q4/forward-compat): dbt-core#7119 -- dbt-core >=1.4.2
manifests FAIL validation against the published v8 schema (`'seed' is not one of
['analysis']` -- resource_type enum mismatch). Lesson: the HOSTED JSON schema can
lag/diverge from what dbt-core actually emits within the same major. Strict
jsonschema validation against hosted schemas is therefore UNSAFE as a runtime
gate -- supports the tool's degrade-to-unverified approach over hard validation.

Sources (add to H):
- https://github.com/dbt-labs/dbt-core/releases/tag/v1.7.0
- https://docs.getdbt.com/docs/dbt-versions/core-upgrade/upgrading-to-v1.6
- https://docs.getdbt.com/docs/dbt-versions/core-upgrade/upgrading-to-v1.7
- https://docs.getdbt.com/docs/dbt-versions/core-upgrade/Older%20versions/upgrading-to-v1.3
- https://docs.getdbt.com/reference/artifacts/manifest-json
- https://github.com/dbt-labs/dbt-core/issues/7119
- https://github.com/dbt-labs/dbt-core/issues/10163

## [2026-06-16T21:54:23Z] Q11 -- dbt-artifacts-parser: Apache-2.0, version-aware, covers 4 artifacts

### Deliverable B input -- existing parser evaluation

dbt-artifacts-parser (yu-iskw/dbt-artifacts-parser, PyPI):
- License: Apache-2.0 (permissive; OK to depend on or vendor with attribution).
- Coverage: catalog.json, manifest.json, run-results.json, sources.json as typed
  Python (pydantic) objects. Primarily designed for dbt-core. Does NOT cover the
  full set of dbt-Cloud-only artifact types; semantic_manifest support is partial/
  absent (CONFIRM). Version-aware: exposes auto-detect functions
  (get_dbt_manifest / get_dbt_run_results / get_dbt_catalog / get_dbt_sources)
  that dispatch on the embedded schema version to the right typed model
  (per-version classes like ManifestV12, RunResultsV6, etc.). CONFIRM lowest
  version covered and release cadence next.
- Fork exists: open-metadata/collate-dbt-artifacts-parser (OpenMetadata's vendored
  copy) -- precedent for vendoring rather than depending.

Relevance to dbt-diagnostics differentiation:
- This is exactly the "static parsing" layer the prompt says NOT to try to win at.
  It is a candidate for the version-aware READING layer (option 5d), freeing the
  tool to invest in the LIVE post-hoc correlation that is its edge.
- BUT: it pulls pydantic + per-version model classes (dependency/footprint cost),
  and the tool today reads plain dicts SELECTIVELY (only a few fields). Adopting it
  would convert dict access to typed access -- larger change, and typed models can
  be STRICTER than needed (raise on unknown/old versions), conflicting with the
  "degrade to unverified, never crash" contract. Decision criteria deferred to the
  Deliverable B DECISION entry.

Sources (add to H):
- https://pypi.org/project/dbt-artifacts-parser/
- https://github.com/yu-iskw/dbt-artifacts-parser
- https://github.com/open-metadata/collate-dbt-artifacts-parser

## [2026-06-16T21:54:54Z] Q4 -- CONFIRMED: raw_sql->raw_code, compiled_sql->compiled_code at dbt 1.3 / manifest v7

### Deliverable C -- field-level risk (CONFIRMED rename, directly hits our code)

CRITICAL: `raw_sql` -> `raw_code` and `compiled_sql` -> `compiled_code` were
renamed in dbt-core 1.3.0 / manifest v7 (to generalize for Python models).
Evidence: dbt "Upgrading to v1.3" ("raw_sql ... renamed to raw_code ... a change
to the manifest contract"); dbt-docs issue CT-937/#292 (the rename PR); corroborated
by dbt-osmosis#14 and dbt-docs#323 (metric SQL broke on the v7 manifest).

Impact on dbt-diagnostics (exact paths from the C scaffold):
- `nodes[].compiled_code` (base.py:50, enrich.py:219, test_failure.py:62) and
  `nodes[].raw_code` are ABSENT on manifest <= v6 (dbt <= 1.2); there the fields
  are `compiled_sql` / `raw_sql`. On dbt <= 1.2 the tool's compiled/raw SQL
  enrichment silently yields None today.
- Mitigation for the reading layer: read with a fallback chain
  `node.get("compiled_code") or node.get("compiled_sql")` and
  `node.get("raw_code") or node.get("raw_sql")`. Cheap, additive, no crash.
- Also note: `compiled_code` is only populated for EXECUTED nodes (docs:
  manifest-json "Some properties, such as compiled_sql, are included only for
  executed nodes"). So absence is expected for unbuilt nodes even on new versions
  -- do not treat None as a version problem.

Risk table (running):
| path | breaks on | reason | mitigation |
| --- | --- | --- | --- |
| nodes[].compiled_code | dbt<=1.2 (manifest<=v6) | named compiled_sql | fallback to compiled_sql; None if not executed |
| nodes[].raw_code | dbt<=1.2 (manifest<=v6) | named raw_sql | fallback to raw_sql |
| nodes[].root_path | dbt>=1.4 (manifest>=v8) | removed (kept for seeds) | not read by us; do not add reliance |

Sources (add to H):
- https://docs.getdbt.com/docs/dbt-versions/core-upgrade/Older%20versions/upgrading-to-v1.3
- https://github.com/dbt-labs/dbt-docs/issues/292
- https://github.com/z3z1ma/dbt-osmosis/issues/14
- https://github.com/dbt-labs/dbt-docs/issues/323

## [2026-06-16T21:59:34Z] Q4 -- v12 freeze and forward-compat machinery

### Deliverable C/A -- dbt compat machinery and the v12 freeze (high-impact)

1) v12 IS FROZEN, additive minor-evolutions only. dbt-core PR 11945 (MichelleArk):
   the manifest schema version basically no longer changes now that dbt commits to
   minor-evolutions only of v12, and the upgrade framework now accounts for the
   actual dbt version. From about 1.8 onward dbt STOPPED bumping the manifest major.
   v12 spans 1.8 through 1.11+ and evolves additively (new optional fields) with no
   major bump. Consequences: the schema major no longer identifies the dbt version
   (two dbt minors both say v12 but carry different fields); metadata.dbt_version is
   the finer signal. Keep SUPPORTED_SCHEMAS manifest 12 broad but add a
   dbt_version-aware note for newer-than-validated builds.

2) dbt ships upgrade machinery: WritableManifest.upgrade_schema_version can accept
   data representing all previous manifest versions (dbt-core 9438). PR 5346
   (jtcohen6, Declare compatibility for previous artifact versions, resolves 5213)
   added FORWARD-compat so latest dbt can deserialize older manifests. The reverse
   (old reader on a new manifest) is NOT guaranteed.

3) Concrete break: dbt-core 9487 mashumaro MissingField, unit_tests missing in
   WritableManifest. A v11 (1.7) manifest lacks unit_tests (added 1.8). Lesson:
   never REQUIRE a field a newer feature added; always use .get().

Sources: dbt-core PR 11945, issue 9438, issue 9487, PR 5346.

## [2026-06-16T22:01:22Z] Q2 -- low-end mapping 1.0 to 1.2

### Deliverable A -- low-end mapping and stability policy

Mapping fill-in, search-confirmed. dbt 1.1 emits manifest v5 per docs Upgrading to
v1.1, where the manifest schema version is updated to v5 and the only change is the
default value of config for parsed nodes. Therefore the low end is 1.0=v4, 1.1=v5,
1.2=v6. dbt 1.2 also added forward-compat logic for older manifest versions used in
state-based selection, per docs Upgrading to v1.2.

Stability policy per docs Upgrading to v1.10. dbt Labs is committed to backward
compatibility for all 1.x versions, and any behavior change is gated behind a
behavior-change flag with a migration window. Artifact churn within 1.x is bounded
and flagged, not silent.

Sources: docs upgrading-to-v1.1, upgrading-to-v1.2, upgrading-to-v1.10.

## [2026-06-16T22:02:08Z] Q2 -- run_results version history and adapter_response shape

### Deliverable A/C -- run_results schema history and adapter_response

run_results major mapping, search-confirmed:
- run_results v4 covers the early/mid 1.x line. The v4 RunResultOutput already
  defines status, timing (list of TimingInfo), thread_id, execution_time,
  adapter_response (Dict[str, Any]), message, failures, unique_id. So ALL the
  run_results fields the tool reads today existed at v4 -- results[].status,
  .message, .timing, .execution_time, .thread_id, .unique_id, .adapter_response
  are safe back to v4. Good news for backward reach.
- run_results v5 introduced in dbt 1.7 per docs Upgrading to v1.7, which states the
  run_results schema version is updated to v5. dbt-core PR 8492 added compilation
  node attributes compiled, compiled_code, relation_name to run_results result
  entries (and to catalog). So results[].compiled_code and results[].relation_name
  exist only from dbt 1.7 / run_results v5 onward.
- run_results v6 is current (matches repo gate run-results 6); bump lands in the
  1.8 line. CONFIRM exact 1.8 sub-version next.

adapter_response shape (docs run-results-json sample and dbt Classes):
- A dict that varies BY ADAPTER. Common keys: code, rows_affected, _message.
  Snowflake adds query_id; BigQuery adds bytes_processed. So
  results[].adapter_response.query_id is Snowflake-specific and adapter-version
  dependent, NOT guaranteed on every adapter or every dbt version. The tool must
  .get() it and degrade when absent (non-Snowflake or older adapter).

Impact on tool paths:
- results[].adapter_response.query_id and .rows_affected: present only when the
  adapter populates them (Snowflake yes). Already accessed defensively, keep so.

Sources: docs run-results-json, docs upgrading-to-v1.7, docs.getdbt.com issue 4125,
dbt-core PR 8492, schemas.getdbt.com run-results v4 and v5 index, docs dbt-classes.

## [2026-06-16T22:02:50Z] Q10 -- relation_name at 1.7 catalog; manifest and catalog top-level keys

### Deliverable C/F -- relation_name provenance and artifact top-level shapes

1) dbt 1.7 (manifest v11, run_results v5) added the compilation node attributes
   compiled, compiled_code, relation_name to catalog.json node entries, per docs
   Upgrading to v1.7. This is the same PR 8492 family noted earlier.
   - OPEN QUESTION to confirm at source level: when did nodes[].relation_name first
     appear in the MANIFEST (not catalog)? The tool reads nodes[].relation_name from
     the manifest in runtime_error.py and data_error.py. If manifest relation_name
     also arrived at 1.7, then on dbt 1.6 and older the tool gets None and its
     relation-name-based correlation degrades. Mark as a Deliverable C risk pending
     per-tag source confirmation. Mitigation regardless: .get with fallback to
     building the relation from database, schema, alias/identifier node fields.

2) catalog.json top-level shape (docs catalog-json): metadata, nodes, sources,
   errors. Each node/source keyed by unique_id; carries column types and stats.
   Post-hoc value for schema-drift diagnosis. catalog is produced by dbt docs
   generate only, so it is often STALE or ABSENT at failure time -- treat as
   best-effort, never required.

3) manifest top-level keys (phData, corroborated): metadata, nodes, sources,
   metrics, exposures, macros, docs, parent_map, child_map, group_map, selectors,
   disabled, plus (1.8+) unit_tests and saved_queries, semantic_models. Useful for
   Q10 collection-by-collection evolution.

4) Reinforced principle (docs manifest-json): the manifest.json version number is
   related to but NOT equal to the dbt version; use the correct schema for the dbt
   version. Confirms relying on metadata.dbt_version for fine-grained behavior, not
   the schema major alone.

Sources: docs upgrading-to-v1.7, docs catalog-json, docs manifest-json, phData
what-are-dbt-artifacts, dbt-core PR 8492.

## [2026-06-16T22:03:37Z] Q3 -- dbt-jsonschema validates input YAML not artifacts; schemas generated from dbt-core

### Q3 -- dbt-jsonschema scope, and how artifact schemas are produced

dbt-jsonschema (dbt-labs/dbt-jsonschema):
- Covers INPUT/CONFIG YAML only -- resource properties files (schema.yml family via
  dbt_yml_files-latest.json), dbt_project.yml, selectors.yml, packages.yml. It is an
  editor-time aid for VS Code and JetBrains YAML validation (LSP). It does NOT cover
  the output artifacts (manifest, run_results, catalog, sources). Hosted as latest
  schemas on the repo main branch; versioned by dbt minor under schemas/.
- DECISION for dbt-diagnostics: NOT useful for our runtime artifact validation. Our
  consumption is OUTPUT artifacts, post-hoc. dbt-jsonschema is about INPUT YAML, and
  validating input YAML is pre-run static analysis -- forbidden by the scope guard.
  Do not adopt it. (License likely Apache-2.0; CONFIRM if ever revisited.)

KEY acquisition fact (feeds Deliverable B option 5c): the AUTHORITATIVE artifact
JSON schemas hosted at schemas.getdbt.com are GENERATED FROM dbt-core source. Per
the schemas.getdbt.com README, you run, from dbt-core, cd core then
hatch run json-schema, which emits a schemas directory with one file per artifact.
So schemas can be regenerated from any dbt-core git tag without hosting -- a clean,
offline-friendly way to capture a per-version schema (option 5c is viable).

Official churn statement (docs About dbt artifacts): the structure of dbt artifacts
is canonized by JSON schemas hosted at schemas.getdbt.com, and artifact versions may
change in ANY minor version of dbt 1.x.0. So per-minor capture is the right
granularity for the fixture matrix.

Adjacent signal (UNKNOWN, follow up): dbt-core is internalizing jsonschema --
recent releases raise jsonschema-based deprecation warnings by default
(dbt-core 12240). dbt may be moving toward shipping its own schemas in-tree.
Fusion uses schemars-generated JSON schema (out of scope, one-line note only).

Sources: github dbt-labs/dbt-jsonschema (README), github dbt-labs/schemas.getdbt.com,
docs reference/artifacts/dbt-artifacts, dbt-core releases page (PR 12240),
yu-ishikawa medium dbt-yaml-validator.

## [2026-06-16T22:04:15Z] Q9 -- structured event protocol in dbt-common; EventInfo reorg; json-log serialization bugs

### Q9 -- structured event/log protocol and its version skew

Protocol location and shape:
- dbt events are strongly-typed Protocol Buffer messages defined in types.proto and
  emitted through a centralized EventManager. In current dbt this lives in dbt-common
  (dbt_common/events/, with types.py and the generated types_pb2.py). Each event has
  envelope fields (EventInfo such as name, code, ts, level, invocation_id, thread)
  plus an event-specific data submessage. The JSON log format prints all event
  fields, so per-node start/finish, full SQL error text, adapter error codes, and
  timing are all available as a post-hoc signal.

Version skew vs artifact schemas:
- The event protocol is versioned SEPARATELY from the artifact schemas, by the
  .proto definitions, not by schemas.getdbt.com. A major structural reorg landed via
  dbt-core 6256 (CT-1509): EventInfo submessage fields were promoted to a top-level
  Event message, with the specific events as a oneof. So a log-parser keyed to the
  old nested EventInfo shape breaks across that reorg. There is also a protobuf
  log_format option (dbt-core 5955) alongside json.

Reliability caveats (post-hoc, real-world):
- On OLDER dbt, --log-format json could FAIL to serialize exceptions, raising a
  serialization error instead of emitting the error event -- dbt-core 5357 (Object
  of type CompilationException is not JSON serializable) and dbt-bigquery 206. So
  on older versions the JSON log may DROP the very error text we want. Treat the
  structured log as a best-effort, version-dependent signal; never the sole source.

Implication for dbt-diagnostics:
- Consuming logs/dbt.log or --log-format json is a CANDIDATE post-hoc source (rich
  SQL error text and adapter codes), but it carries its OWN protocol version and
  reliability cliff. If adopted, gate it behind presence and shape checks, and keep
  run_results plus compiled SQL as the primary evidence.

Sources: docs reference/events-logging, docs global-configs/logs, deepwiki dbt-core
event-and-logging-system, deepwiki dbt-common event-logging, dbt-core issues 6256,
5955, 5357, dbt-bigquery 206.

## [2026-06-16T22:06:00Z] DECISION -- Deliverable B: acquisition strategy and adopt-vs-build

### Deliverable B -- acquisition/storage strategy and the adopt-vs-build decision

Four candidate strategies for versioned file representations, weighed:
- 5a Vendor hosted JSON schemas per version. Pro: cheap, offline. Con: hosted
  schemas can DIVERGE from what dbt actually emits within a major (dbt-core 7119,
  the seed-vs-analysis enum bug) and can LEAD the release (dbt-core 10163). So
  schemas are imperfect oracles and unsafe as a strict runtime gate.
- 5b Capture real GOLDEN ARTIFACTS by running a tiny fixture project through
  `dbt parse` and `dbt build` at each git tag. Pro: ground truth, exactly what the
  classifiers will see, doubles as test fixtures. Con: must run N dbt versions in a
  tox/uv matrix; some old versions are painful to install. Highest fidelity and it
  aligns with the existing `dbt_diagnostics/fixtures/` approach.
- 5c Extract schemas from dbt-core source per tag without running dbt
  (`cd core && hatch run json-schema`). Pro: no warehouse, authoritative,
  scriptable. Con: still a schema not an instance, and needs a build env per tag.
- 5d Depend on dbt-artifacts-parser for the version-aware reading layer. Pro:
  someone else maintains per-version typed models. Con: pydantic dependency, it can
  be stricter than our degrade-never-crash contract, and it solves PARSING which is
  explicitly NOT our differentiator.

DECISION (recommended): BUILD-OUR-OWN selective dict reader; do NOT adopt
dbt-artifacts-parser as a hard runtime dependency. Rationale:
- The tool reads only ~12 dict paths selectively; a typed full-model parser is
  overkill and its strictness fights the never-crash contract.
- Most read paths are STABLE back to early 1.x (run_results fields exist at v4;
  manifest core fields stable). The only confirmed breakers are simple renames
  (compiled_sql to compiled_code, raw_sql to raw_code at 1.3) handled by a one-line
  `.get` fallback chain.
- Keep dbt-artifacts-parser as an OPTIONAL test-only validation aid (cross-check our
  reads against its typed models), never in the runtime path.
- Primary acquisition = 5b golden artifacts (fidelity plus doubles as tests),
  backed by 5c source-extracted schemas for documentation. Skip 5a hosted-schema
  vendoring at runtime; reference those URLs in docs only.

Directory layout proposal:
- `dbt_diagnostics/fixtures/golden/<dbt_version>/target/` holding manifest.json,
  run_results.json, catalog.json, sources.json captured per version.
- `tests/compat/test_matrix.py` parametrized over the golden dirs.
- Schema notes in docs reference schemas.getdbt.com URLs, not vendored copies.

Rule for adding a new dbt version (how a new version gets validated and added):
1. Add the version to the tox/uv matrix; run the fixture project through
   `dbt build` to capture a golden target/ dir under fixtures/golden/<version>/.
2. Run the compat test matrix; the classifiers must parse with no crash.
3. If the detected schema major is new, add it to SUPPORTED_SCHEMAS only AFTER the
   matrix is green. Until then the tool already degrades to unverified.
4. Record the version in the schema-history table and CHANGELOG.

Offline guarantee: nothing in the runtime path fetches a schema; detection uses the
artifact's own embedded metadata only. Satisfied.

## [2026-06-16T22:08:00Z] Q1/Q2 -- consolidated schema-version history and dbt mapping (Deliverable A)

### Deliverable A -- consolidated tables (search-confirmed unless marked CONFIRM)

Schema major by dbt-core minor:

| dbt-core | manifest | run_results | catalog | sources | notes |
| --- | --- | --- | --- | --- | --- |
| 1.0 | v4 | v4 | v1 | v3 | CONFIRM low-end run_results/catalog majors |
| 1.1 | v5 | v4 | v1 | v3 | v5 only changed default of config |
| 1.2 | v6 | v4 | v1 | v3 | manifest v6 = dbt-core 5417 |
| 1.3 | v7 | v4 | v1 | v3 | raw_sql->raw_code, compiled_sql->compiled_code |
| 1.4 | v8 | v4 | v1 | v3 | root_path removed (kept for seeds) |
| 1.5 | v9 | v4 | v1 | v3 | CONFIRM run_results still v4 |
| 1.6 | v10 | v4 | v1 | v3 | manifest v10 |
| 1.7 | v11 | v5 | v1 | v3 | run_results->v5; compiled/relation_name added (PR 8492) |
| 1.8 | v12 | v6 | v1 | v3 | unit_tests added; v12 begins; FROZEN thereafter |
| 1.9 | v12 | v6 | v1 | v3 | additive only |
| 1.10 | v12 | v6 | v1 | v3 | additive only (macro arg types into manifest) |
| 1.11 | v12 | v6 | v1 | v3 | repo ground truth (gate manifest 12, run-results 6) |

Caveats: catalog and sources majors above are best-effort (catalog v1, sources v3
held steady across the line) and need a per-tag source confirm. From 1.8 the
manifest major is FROZEN at v12 and evolves additively, so the major no longer
maps 1:1 to a dbt minor -- use metadata.dbt_version for fine distinctions.

## [2026-06-16T22:08:30Z] Q7 -- post-hoc diagnostic leverage by artifact and version

### Q7 -- failure-time signal mapped to existing classifiers (strictly post-hoc)

Existing classifiers: compilation_error, runtime_error, schema_change_error,
contract_violation, data_error, test_failure, timeout_error.

| signal (artifact, version) | unlocks for classifier |
| --- | --- |
| run_results status/message (v4+, all) | every classifier's primary trigger |
| run_results timing + execution_time (v4+) | timeout_error; query-history correlation by duration |
| adapter_response.query_id (Snowflake) | runtime_error/data_error -> join to Snowflake query history for live root cause |
| adapter_response.rows_affected (Snowflake) | data_error (unexpected row counts) |
| manifest compiled_code (v7+; compiled_sql earlier) | compilation_error/runtime_error -> exact SQL that failed |
| manifest depends_on.nodes (v4+) | all -> upstream blast radius |
| manifest columns + catalog.json column types | schema_change_error/contract_violation -> drift vs live INFORMATION_SCHEMA |
| catalog.json (1.7+ adds compiled/relation_name) | schema_change_error -> declared vs cataloged types |
| sources.json freshness (source freshness cmd) | NEW data-staleness diagnosis (not yet a classifier) |
| logs/dbt.log json events (version-skewed) | richer SQL error text + adapter error codes for runtime_error |

Cross-version unlock: adding catalog.json and sources.json consumption (both
present back to early 1.x) unlocks schema-drift and stale-source post-hoc
diagnoses with NO new live-scan cost -- they are warehouse snapshots dbt already
wrote. Strictly post-hoc; no pre-run analysis.

## [2026-06-16T22:09:00Z] DECISION -- Deliverable D: test matrix and fixture-generation plan

### Deliverable D -- test matrix and golden-fixture plan

Matrix axes:
- dbt-core minor: 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11 (anchor on schema
  boundaries: v7@1.3, v8@1.4, v9@1.5, v10@1.6, v11@1.7, v12@1.8+). Optionally 1.1/1.2
  for the rename boundary. Snowflake adapter for all (live layer is Snowflake).
- artifact: manifest.json, run_results.json, catalog.json, sources.json.
- failure shapes: a passing build, a compilation error, a runtime error, a failing
  test, and a partial/interrupted run_results (truncated).

What makes a fixture GOLDEN:
- Produced by the real dbt version (not hand-edited), from a fixed minimal project,
  checked in under fixtures/golden/<version>/target/.
- Deterministic: pin a tiny project (2-3 models, 1 source, 1 test) so diffs are
  meaningful; scrub absolute paths and timestamps to keep them stable.
- Each golden dir carries the embedded schema URL so detect_artifact_version is
  exercised for real.

Assertions per (version, fixture):
1. schema_version.detect_artifact_version returns the expected kind and major and
   NEVER raises.
2. Every classifier runs to completion on the artifacts with no exception.
3. The compiled/raw SQL fallback resolves on <=1.2 (compiled_sql) and >=1.3
   (compiled_code).
4. Unknown/future version (synthetic v13 manifest) -> supported False + note, parse
   continues.

Maintainability: generate goldens with a tox/uv or nox matrix that pip-installs each
dbt-snowflake version into an isolated env and runs the fixture project. Regenerate
only when adding a version; commit the artifacts so CI needs no warehouse.

## [2026-06-16T22:09:30Z] DECISION -- Deliverable E: prioritized additive implementation plan (issue stubs)

### Deliverable E -- GitHub issue stubs (one PR per issue, off donkey-kong-sandbox)

Issue E1 (feat): version-tolerant SQL field reader.
- Scope: add a small accessor that reads compiled_code with fallback to
  compiled_sql, and raw_code with fallback to raw_sql, used by base.py, enrich.py,
  test_failure.py. Additive; no behavior change on >=1.3.
- Acceptance: goldens for 1.2 and 1.3 both yield compiled SQL; no crash on either.

Issue E2 (feat): dbt_version-aware unverified note.
- Scope: when manifest major is in SUPPORTED but metadata.dbt_version is newer than
  the validated 1.11, emit an informational note (still supported True). Keep
  SUPPORTED_SCHEMAS as the gate. Additive to --json (new note string only).
- Acceptance: a synthetic v12 artifact tagged dbt 1.13 yields supported True plus a
  newer-than-validated note; --json schema_version unchanged in shape.

Issue E3 (feat): broaden SUPPORTED_SCHEMAS with golden fixtures.
- Scope: capture goldens for 1.7 (manifest v11, run_results v5) and add
  manifest 11 and run-results 5 to SUPPORTED_SCHEMAS once the matrix is green.
- Acceptance: 1.7 goldens parse; gate reports supported True for v11/v5.

Issue E4 (feat): consume catalog.json for schema-drift (post-hoc).
- Scope: resolve target/catalog.json in discover.py; feed column types to
  schema_change_error. Best-effort; absent/stale catalog degrades silently.
- Acceptance: schema_change_error uses catalog column types when present; no
  regression when catalog.json is missing.

Issue E5 (feat): consume sources.json for stale-source diagnosis (post-hoc).
- Scope: resolve target/sources.json; add a stale-source signal to data_error or a
  new freshness path. Additive.
- Acceptance: a stale sources.json yields a freshness note; absence is a no-op.

Issue E6 (test): cross-version golden fixture matrix.
- Scope: add fixtures/golden/<version>/ and tests/compat/test_matrix.py per
  Deliverable D. CI runs offline against committed goldens.
- Acceptance: matrix green for 1.3 through 1.11; never-crash asserted.

Issue E7 (chore, optional): test-only cross-check vs dbt-artifacts-parser.
- Scope: dev-dependency only; a test compares our dict reads against the parser's
  typed models for the same goldens. Not in runtime path.
- Acceptance: cross-check passes or is xfail-documented per version.

Sequencing: E1 and E2 first (cheap, high safety), then E6 (matrix) to lock
behavior, then E3, then E4/E5 (new value), E7 last and optional.

## [2026-06-16T22:11:00Z] UNKNOWN -- Deliverable G: discovery logs and self-critique

### Deliverable G.1 -- unknown-unknowns (not asked, but matter)

1. The hosted JSON schema is NOT a reliable oracle. dbt-core 7119 shows real
   manifests failing their own published schema within a major; dbt-core 10163 shows
   a schema (v12) published BEFORE the engine that emits it shipped. So strict
   jsonschema validation at runtime would produce false failures -- vindicates the
   degrade-to-unverified design and argues against vendoring schemas as a gate.
2. The v12 FREEZE is the single most important finding: from ~1.8 the manifest major
   stopped moving and now evolves additively. This inverts the original premise of
   "support every version's schema" -- for 1.8+ there is effectively ONE manifest
   schema (v12) plus additive fields, so the cross-version burden is concentrated in
   1.0-1.7, not the future. metadata.dbt_version, not the schema major, is the real
   version signal going forward.
3. The structured event/log stream has its OWN protocol version (dbt-common
   protobuf) that skews from the artifact schemas, AND a reliability cliff on older
   dbt where JSON logs could drop exceptions. A log-consuming feature is therefore
   higher-risk than artifact consumption.
4. partial_parse.msgpack staleness is itself a failure cause and is msgpack, not
   JSON -- a post-hoc signal the tool does not touch today.
5. dbt is internalizing jsonschema (deprecation warnings by default) -- future dbt
   may ship in-tree schemas, changing the acquisition calculus.

### Deliverable G.2 -- open questions (with the next search to run)

- Exact run_results major per 1.3-1.6 (assumed v4 throughout). Next: read
  core/dbt/contracts/results.py at tags v1.3.0..v1.6.0.
- When did nodes[].relation_name enter the MANIFEST (vs catalog at 1.7)? Next: grep
  manifest nodes schema at v1.5/v1.6/v1.7 tags.
- Exact dbt-common extraction release and dbt-adapters split release. Next: read
  dbt-core setup/pyproject deps at v1.5.0, v1.6.0, v1.8.0.
- catalog.json and sources.json major history (assumed v1/v3 stable). Next:
  schemas.getdbt.com/dbt/catalog and /sources index pages.
- semantic_manifest.json schema versioning (dbt-semantic-interfaces). Next: that
  repo's schema dir.
- dbt-artifacts-parser lowest covered version and release cadence. Next: its
  parsers module listing.

### Deliverable G.3 -- searches I ran (audit trail)

1. schemas.getdbt.com manifest/run-results/sources versions -> confirmed manifest
   v5-v12 index, sources v3, manifest v6 = dbt 1.2.
2. manifest version to dbt mapping 1.3-1.10 -> v7@1.3, v8@1.4, v10@1.6, v11@1.7,
   root_path removed at v8, the 7119 validation bug.
3. dbt-artifacts-parser coverage/license -> Apache-2.0, 4 artifacts, version-aware.
4. raw_sql/compiled_sql rename -> confirmed at 1.3 / manifest v7.
5. WritableManifest upgrade machinery + stability policy -> v12 freeze (PR 11945),
   upgrade_schema_version (9438), unit_tests MissingField (9487), 1.1=v5.
6. run_results version history + adapter_response -> fields exist at v4,
   run_results v5 at 1.7, adapter_response varies by adapter (Snowflake query_id).
7. relation_name + catalog/sources history -> relation_name/compiled added to
   catalog at 1.7; catalog and manifest top-level shapes.
8. dbt-jsonschema scope -> input YAML only, not artifacts; schemas generated from
   dbt-core source (option 5c viable).
9. dbt-common events protocol -> protobuf types.proto, EventInfo reorg (6256),
   json-log serialization bugs on older dbt.

Searches deliberately NOT run (and why): deep Fusion/dbt-2.x schema research
(out of scope per prompt); non-Snowflake adapter_response specifics (live layer is
Snowflake-only); pre-1.0 schemas (out of practical support range, low value).

### Deliverable G.4 -- self-critique (gaps and what would change the recommendation)

What I did NOT confirm / thin evidence:
- catalog.json and sources.json major numbers across tags are inferred (v1/v3
  steady), not directly verified per tag.
- The manifest vs catalog provenance of relation_name is unresolved; the tool reads
  it from the manifest and I confirmed the catalog addition only.
- Exact dbt-common and dbt-adapters split releases are still approximate (~1.5/1.6
  and ~1.8).

Three angles not fully explored:
- Partial/corrupted/truncated artifacts from interrupted runs (only flagged).
- Multi-invocation and --defer/state: artifacts where manifest and run_results come
  from different dbt versions in one workflow.
- The msgpack partial-parse and graph.gpickle as post-hoc signals.

What would change the recommendation if false:
- If manifest core read-paths (status, depends_on, relation_name) turned out to
  have moved more than the two confirmed renames, build-our-own would need more
  fallbacks and adopting dbt-artifacts-parser would look better.
- If the v12 freeze were reversed in a future dbt 1.x, the "concentrate effort on
  1.0-1.7" conclusion would weaken.

These gaps are NOT material to the headline recommendation (build-our-own selective
reader, golden-fixture matrix, additive gate widening), but the catalog/sources and
relation_name items should be closed before shipping E4/E5.

## [2026-06-16T22:11:30Z] SOURCES -- Deliverable H: consolidated source list

### Deliverable H -- Sources (all URLs used)

dbt-core repo and issues:
- https://github.com/dbt-labs/dbt-core/releases/tag/v1.7.0
- https://github.com/dbt-labs/dbt-core/pull/5346
- https://github.com/dbt-labs/dbt-core/pull/11945
- https://github.com/dbt-labs/dbt-core/issues/9438
- https://github.com/dbt-labs/dbt-core/issues/9487
- https://github.com/dbt-labs/dbt-core/issues/7119
- https://github.com/dbt-labs/dbt-core/issues/10163
- https://github.com/dbt-labs/dbt-core/issues/6256
- https://github.com/dbt-labs/dbt-core/issues/5955
- https://github.com/dbt-labs/dbt-core/issues/5357
- https://github.com/dbt-labs/dbt-core/releases

dbt docs:
- https://docs.getdbt.com/reference/artifacts/dbt-artifacts
- https://docs.getdbt.com/reference/artifacts/manifest-json
- https://docs.getdbt.com/reference/artifacts/run-results-json
- https://docs.getdbt.com/reference/artifacts/catalog-json
- https://docs.getdbt.com/reference/artifacts/sl-manifest
- https://docs.getdbt.com/reference/dbt-classes
- https://docs.getdbt.com/reference/events-logging
- https://docs.getdbt.com/reference/global-configs/logs
- https://docs.getdbt.com/docs/dbt-versions/core-upgrade/Older%20versions/upgrading-to-v1.1
- https://docs.getdbt.com/docs/dbt-versions/core-upgrade/Older%20versions/upgrading-to-v1.2
- https://docs.getdbt.com/docs/dbt-versions/core-upgrade/Older%20versions/upgrading-to-v1.3
- https://docs.getdbt.com/docs/dbt-versions/core-upgrade/upgrading-to-v1.6
- https://docs.getdbt.com/docs/dbt-versions/core-upgrade/upgrading-to-v1.7
- https://docs.getdbt.com/docs/dbt-versions/core-upgrade/upgrading-to-v1.10

Schemas and other repos:
- https://schemas.getdbt.com/
- https://schemas.getdbt.com/dbt/manifest/v12/index.html
- https://schemas.getdbt.com/dbt/run-results/v4/index.html
- https://schemas.getdbt.com/dbt/run-results/v5/index.html
- https://github.com/dbt-labs/schemas.getdbt.com
- https://github.com/dbt-labs/dbt-jsonschema
- https://github.com/dbt-labs/docs.getdbt.com/issues/1667
- https://github.com/dbt-labs/docs.getdbt.com/issues/4125
- https://github.com/dbt-labs/dbt-docs/issues/292
- https://github.com/dbt-labs/dbt-docs/issues/323
- https://github.com/z3z1ma/dbt-osmosis/issues/14
- https://github.com/dbt-labs/dbt-bigquery/issues/206
- https://pypi.org/project/dbt-artifacts-parser/
- https://github.com/yu-iskw/dbt-artifacts-parser
- https://github.com/open-metadata/collate-dbt-artifacts-parser
- https://deepwiki.com/dbt-labs/dbt-core/8-event-and-logging-system
- https://deepwiki.com/dbt-labs/dbt-common/2.2-event-logging
- https://www.phdata.io/blog/what-are-dbt-artifacts/
- https://yu-ishikawa.medium.com/dbt-yaml-validator-in-jetbrains-b5ef25e9253e

## [2026-06-16T22:20:00Z] Q10 -- CORRECTION: field-level diff from real per-version sources (closes relation_name gap)

### Deliverable C -- low-level per-version field presence (authoritative, GitHub-sourced)

Method: diffed the real per-version representations in yu-iskw/dbt-artifacts-parser
(both the generated pydantic models parsers/manifest/manifest_vN.py and the
embedded JSON schemas resources/manifest/manifest_vN.json, plus run_results_vN).
This is field-level ground truth, not inference, and it CORRECTS an earlier guess.

CORRECTION to the earlier open question "when did nodes[].relation_name enter the
MANIFEST":
- nodes[].relation_name is present (Optional[str], default None) in manifest v1, v2,
  v3, v4, v5, v6, v7, v8, v9, v10, v11, v12 -- i.e. it has existed in the manifest
  since the beginning of the 1.x line. So there is NO version gap for our manifest
  relation_name read. My prior "Deliverable C risk pending confirmation" for manifest
  relation_name is RESOLVED: not a risk. (The 1.7 change was adding relation_name to
  catalog.json node entries, a DIFFERENT file from the manifest.)

run_results (separate from manifest):
- results[].relation_name and results[].compiled_code exist in run_results v5 and v6,
  NOT in v4. So reading these FROM run_results is dbt 1.7+ only. We read compiled_code
  and relation_name from the MANIFEST (safe back to v1), so this run_results gap does
  not affect us -- but if any code ever reads them off run_results, guard for v4.

Value-vs-presence nuance (reinforces the live-layer-is-truth point):
- In a real run_results v6 fixture, relation_name and compiled_code are NULL for
  seeds and for tests even though the FIELD is present. So "field present" does NOT
  mean "value present"; for tests and seeds the offline artifact gives None and the
  relation must be reconstructed and confirmed against the live database. The offline
  file is necessary but not sufficient; Tier A metadata (and Tier B scans) are the
  validating source of truth, exactly as the project thesis holds.

adapter_response is free-form per adapter (confirmed from a real fixture):
- The captured v6 fixture is BigQuery: adapter_response carries
  _message, code, rows_affected, bytes_processed, bytes_billed, job_id, slot_ms,
  location, project_id -- and NO query_id. Snowflake instead populates query_id.
  Some entries (on-run-start/end operations) have adapter_response = {} (empty).
  Confirms: results[].adapter_response.query_id must be .get() and may be absent on
  non-Snowflake adapters and on hook/operation results even on Snowflake.

Net effect on Deliverable C risk list: the only CONFIRMED version-breaking change to
a field we read remains the 1.3 rename (compiled_sql to compiled_code, raw_sql to
raw_code). relation_name is safe v1-v12. status, message, timing, execution_time,
thread_id, unique_id, depends_on, columns are stable across the range. This makes the
build-our-own thin reader even more clearly the right call: one rename fallback plus
defensive .get() covers the whole 1.x manifest/run_results surface we consume.

Source: github.com/yu-iskw/dbt-artifacts-parser (parsers/manifest/manifest_v1..v12.py,
resources/manifest/manifest_v1..v12.json, parsers/run_results/run_results_v4..v6.py,
tests/resources/run_results/v6 fixture), accessed via GitHub at commit 7090dc4.

End of session -- 2026-06-16 cross-version compatibility research (deliverables A-H drafted; relation_name gap closed).

## [2026-06-16T22:42:53Z] DECISION -- first-party is source of truth; third-party parser out of the loop

### Source-of-truth decision (governance)

dbt-artifacts-parser is NOT a source of truth and is NOT a runtime dependency.
It is a third-party, auto-generated MIRROR of dbt schemas (datamodel-code-generator
over the JSON schemas), so it can lag, carry generation quirks, or drift.

Source-of-truth hierarchy adopted:
- Tier 1: dbt published JSON schemas (dbt-labs/schemas.getdbt.com, generated FROM
  dbt-core) plus REAL golden artifacts dbt writes.
- Tier 2 (semantics, when a schema is ambiguous): dbt-core source at the matching tag.
- dbt-artifacts-parser: optional test-only cross-check; droppable.

Provenance note on the earlier relation_name v1-v12 finding: it was sourced from the
third-party mirror as a research lens. Marked PROVISIONAL until reconfirmed against
first-party schemas. The compat tooling built this session reconfirms it from Tier-1
artifacts and a Tier-1 fetch script.

Pure-Python self-maintenance (decided): correctness is fully autonomous and needs no
per-version code. A new dbt version cannot break the tool because (1) detection
degrades to unverified and never crashes, and (2) every consumed field has a
live_recovery so a missing/renamed offline value is recovered from the live warehouse
(Tier A). The acquisition + diff + CI gate are 100 percent Python. Human/AI is needed
only to OPTIMIZE (add a one-line fallback alias after a rename to keep the cheap
offline path) - a rare, product-judgment call, not maintenance toil. High-confidence
renames are auto-PROPOSED but human-approved, never auto-applied, because a silent
wrong rename mapping is worse than graceful degradation to the live layer.
