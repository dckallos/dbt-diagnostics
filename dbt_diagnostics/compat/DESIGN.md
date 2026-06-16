# Low-level design: `dbt_diagnostics/compat`

Cross-version compatibility for the dbt artifacts dbt-diagnostics consumes. This
package lets the tool parse and diagnose artifacts from ANY dbt-core version with
known confidence, while keeping the runtime offline and never-crashing. It is the
static (file-level) half of the version story; the live warehouse layer (Tier A /
Tier B) is the validating source of truth.

## Design thesis (read first)

1. The offline artifact is a HINT, not the truth. The live database is the truth.
   Every field we read carries a `live_recovery` describing how Tier A re-derives the
   same fact from Snowflake when the offline value is missing, renamed, or None.
2. First-party is the only source of truth. Tier 1 = dbt's published JSON schemas
   (`schemas.getdbt.com`, generated from dbt-core) plus real golden artifacts. Tier 2
   (semantics) = dbt-core source at the matching tag. The third-party
   `dbt-artifacts-parser` is NOT used here (optional test-only cross-check at most).
3. Correctness needs zero per-version code. Detection degrades to "unverified" and
   never raises; a missing/renamed field falls through to `live_recovery`. A new dbt
   version cannot break the tool unattended.
4. No static linting / no pre-run analysis. This package only reasons about artifacts
   that already exist after a run, consistent with the repo scope guard.

## Module map

| module | responsibility |
| --- | --- |
| `consumed_paths.py` | The registry: every dict path we read, its version fallbacks, nullable expectation, adapter-specificity, and `live_recovery`. Single declarative source shared by the differ and the runtime reader. |
| `schema_model.py` | `SchemaDoc`: minimal JSON Schema resolver (`$ref`, `$defs` vs `definitions`, `allOf` merge, `anyOf`/`oneOf` unions, collection member schemas, type normalization). Stdlib-only. |
| `path_resolver.py` | `resolve(doc, path)`: walk a dot-path (with `[]` collection descent) across node-type unions into per-definition `Presence` records. `present_anywhere(...)` convenience. |
| `safe.py` | Runtime accessors that mirror the registry fallbacks and never raise (return None to trigger live recovery). |

Tooling (not shipped in the runtime path):

| file | responsibility |
| --- | --- |
| `scripts/compat/schema_diff.py` | CLI/CI gate. Diffs two first-party schemas by consumed-path presence; exits nonzero only when a consumed field disappears with no surviving fallback. |
| `scripts/compat/fetch_schemas.py` | The ONLY networked piece. Caches first-party schemas into `dbt_diagnostics/fixtures/schemas/<artifact>/vN.json` and writes `PROVENANCE.json` (url + sha256). Run in dev/CI, never at runtime. |

## Data model: `ConsumedPath`

```
ConsumedPath(
    artifact,            # "manifest" | "run-results"
    path,                # e.g. "nodes[].relation_name"; "[]" descends into members
    fallbacks=(),        # historical sibling keys tried in order (e.g. compiled_sql)
    nullable_expected,   # None is a normal value (seeds/tests relation_name)
    adapter_specific,    # may be absent on non-Snowflake adapters
    live_recovery,       # Tier-A recovery when the offline value is missing/None
    classifiers,         # which classifiers read it (blast-radius reporting)
)
```

`path` grammar: `.` separates property steps; a `[]` suffix descends into a
collection's member schema (a dict's `additionalProperties`/`patternProperties`, or an
array's `items`). Example: `nodes[].relation_name` = property `nodes` -> each node
value -> property `relation_name`. `results[].timing[].started_at` chains two descents.

## Algorithm: schema resolution

`schema_model.SchemaDoc` primitives tolerate dbt's schema variety: `deref` follows a
`$ref` chain (both `#/$defs/X` and `#/definitions/X`) with a cycle guard; `members`
flattens `anyOf`/`oneOf` unions and merges `allOf` (this is what lets us reason about
`nodes` being a union of node types); `item_schema` gives a collection's member schema
for `[]` descent; `norm_type` collapses `type` lists and `anyOf [..., {type:null}]`
into `(non_null_types, nullable)`.

`path_resolver.resolve(doc, path)` starts at `root_object()` (the root may itself be a
`$ref` to e.g. `WritableManifest`), descends each token (into the member schema when
the token ends with `[]`, re-flattening unions), and returns one
`Presence(defn, present, required, types, nullable)` per concrete object reached, so a
field present on some node kinds and absent on others is captured precisely.
`present_anywhere` is True if the leaf is present on at least one object.

## The static gate: `schema_diff.py`

For each `ConsumedPath`, compute `present_anywhere` in BASE and NEW first-party
schemas: present->absent triggers a fallback check (any declared fallback present in
NEW -> `OK-FALLBACK`, else `BREAK` plus the `live_recovery`); absent->present is
`NEW`; otherwise `STABLE`. Unguarded breaks exit nonzero. This is the CI gate: a future
dbt version that moves a field WE read fails the build loudly and additively.

## The runtime reader: `safe.py`

The diagnosis path reads through never-raising helpers that encode exactly the
registry's fallbacks: `node_compiled_sql` (compiled_code or compiled_sql, the 1.3
rename), `node_raw_sql` (raw_code or raw_sql), `node_relation_name` (present v1-v12;
None for seeds/tests), and `result_query_id`/`result_rows_affected` (dug from
`adapter_response`; None on non-Snowflake adapters or hook/operation results). A unit
test asserts `safe`'s aliases equal the registry's `fallbacks`, preventing drift.

## Self-maintenance (how a new dbt version is handled)

```
poll dbt releases -> fetch_schemas.py (cache first-party schema for the new tag)
                  -> schema_diff.py BASE NEW --artifact ...   (CI gate)
                  -> if a consumed field moved with no fallback: open an issue / fail
                  -> regardless, runtime keeps working (degrade + live_recovery)
```
The ONLY recurring human task is OPTIMIZATION, not correctness: after a confirmed
rename, add a one-line `fallbacks=(...)` alias to keep using the cheap offline value
instead of the (still-correct) live recovery. High-confidence renames may be
auto-proposed but are human-approved, never auto-applied: a silent wrong rename
mapping is worse than graceful degradation.

## How to add a consumed field

1. Add a `ConsumedPath` to `REGISTRY` with its `live_recovery`.
2. Add a matching accessor in `safe.py` if it needs a fallback chain.
3. Add an assertion to the compat tests.
Adding a new dbt VERSION requires none of the above; only product decisions touch the
registry.

## Provenance and offline guarantees

`fixtures/schemas/<artifact>/vN.json` are first-party; `PROVENANCE.json` records source
url + sha256 for each. `schema_diff.py` reads only these. Nothing in the runtime path
performs network I/O; `fetch_schemas.py` is the single networked component and is
decoupled from diagnosis. See `docs/RESEARCH_VERSION_COMPAT_FINDINGS.md` for the
evidence behind every decision.
