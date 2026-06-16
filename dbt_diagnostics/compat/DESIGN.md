# `dbt_diagnostics/compat` -- low-level design

Cross-version compatibility for the dbt artifacts dbt-diagnostics consumes. The
package exists so the tool can parse and diagnose artifacts from any dbt-core
version with known confidence, while keeping the runtime offline and
never-crashing. It is deliberately small: the tool reads about a dozen fields out
of hundreds, so this is a hardening layer around a thin reader, not a
full artifact parser.

See `docs/RESEARCH_VERSION_COMPAT_FINDINGS.md` for the research behind every
decision here.

## Design tenets (do not violate)

1. **First-party is the source of truth.** The published dbt JSON schemas
   (`schemas.getdbt.com`, generated from dbt-core) and the real artifacts dbt
   writes are authoritative. The third-party `dbt-artifacts-parser` is NOT a
   dependency and NOT an oracle; at most an optional test-only second opinion.
2. **Offline at runtime.** Nothing in the diagnosis path fetches anything. The
   only networked code is `scripts/compat/fetch_schemas.py`, run in dev/CI.
3. **Degrade, never crash.** An unknown version parses best-effort; a missing or
   renamed field returns `None` and the caller falls through to the live layer.
4. **The warehouse is truth; the file is a hint.** Every consumed field carries a
   `live_recovery` describing how Tier A (Snowflake metadata) recovers the same
   fact when the offline value is absent or `None`.
5. **Additive only.** Widening support is deliberate: capture/validate, then add.

## Module map

```
consumed_paths.py   registry: what we read + fallbacks + live_recovery (the spine)
schema_model.py     JSON Schema resolver: $ref, $defs/definitions, allOf, anyOf/oneOf
path_resolver.py    resolve a path across node-type unions -> per-definition Presence
safe.py             runtime accessors: read primary, fall back, return None (no raise)
```

Companion (not in-package):

```
scripts/compat/schema_diff.py    CI gate: diff two first-party schemas by consumed path
scripts/compat/fetch_schemas.py  acquire first-party schemas into the offline cache
dbt_diagnostics/tests/test_compat_schema_diff.py   offline unit proof
```

## `consumed_paths.py` -- the registry

`ConsumedPath` is a frozen dataclass; `REGISTRY` is the single declarative list of
every dict path the classifiers/enrichers read (grepped from `classifiers/` and
`enrichers/`). Fields:

- `artifact`  -- `"manifest"` or `"run-results"`.
- `path`      -- dot-path; `"[]"` descends into a collection's member schema
                 (dict values or array items), e.g. `nodes[].relation_name`,
                 `results[].adapter_response.query_id`.
- `fallbacks` -- sibling keys to try when the primary leaf is absent, e.g.
                 `compiled_code` falls back to `compiled_sql` (renamed in dbt 1.3).
- `nullable_expected` -- `None` is a normal value (seeds/tests `relation_name`).
- `adapter_specific`  -- may be absent on non-Snowflake adapters (`query_id`).
- `live_recovery`     -- Tier-A recovery when the offline value is missing/None.
- `classifiers`       -- who reads it (for blast-radius reporting).

Both the static diff and the runtime reader import this list, so they cannot
drift. Adding a new dbt VERSION never edits this file; it changes only when we
decide to consume a new field (product decision) or add a fallback alias after a
confirmed rename (rare optimization).

## `schema_model.py` -- `SchemaDoc`

dbt schemas mix draft-07 (`definitions`) and 2020-12 (`$defs`), reference node
types via `$ref`, and express `nodes`/`results` as `anyOf`/`oneOf` unions of many
node-type objects. `SchemaDoc` provides the minimum resolution to answer "is this
field present, required, and of what type" across everything a path can reach:

- `deref(node)`   -- follow a `$ref` chain to a concrete dict; cycle-guarded.
- `members(node)` -- flatten a union (`anyOf`/`oneOf`) or merge an `allOf` into a
                     list of concrete object subschemas.
- `item_schema(node)` -- the member schema of a collection (`additionalProperties`,
                     `items`, or first `patternProperties`).
- `norm_type(spec)`   -- normalize a field spec to `(non-null types, nullable?)`,
                     handling `["string","null"]` and `anyOf: [..., {type: null}]`.
- `root_object()` -- the top-level object (the root may itself `$ref` into `$defs`,
                     e.g. `WritableManifest`).

Stdlib-only, no network, no jsonschema dependency.

## `path_resolver.py` -- `resolve`

Turns a registry path into authoritative per-node-type facts for ONE schema
version. Because `nodes`/`results` are unions, a field can be present on some node
kinds and absent on others, so `resolve` returns one `Presence` per concrete
object reached:

```
Presence(defn, present, required, types, nullable)
```

Walk algorithm: start from `members(root_object())`; for each path token, descend
into the named property and, if the token ends with `[]`, into the collection's
member schema, re-flattening unions at every step. The final token is checked on
each frontier object for presence/required/type. `present_anywhere(doc, path)` is
the convenience predicate used by the diff tool.

Worked example -- `nodes[].relation_name` on manifest v12 returns a `Presence` for
every node-type definition (model, seed, test, snapshot, ...), confirming the
field exists since v1 and is nullable (`None` for seeds/tests).

## `safe.py` -- runtime accessors

The runtime side of the contract: read the primary key, fall back to known
historical aliases, return `None` (never raise) so the caller can fall through to
live recovery.

- `dig(obj, *keys, default=None)` -- safe nested dict walk.
- `node_compiled_sql(node)` -- `compiled_code` then `compiled_sql` (1.3 rename).
- `node_raw_sql(node)`      -- `raw_code` then `raw_sql` (1.3 rename).
- `node_relation_name(node)`-- present v1-v12; `None` for seeds/tests.
- `result_query_id(result)` -- Snowflake-only; `None` on other adapters/operations.
- `result_rows_affected(result)`.

A test asserts the fallback aliases here match the `fallbacks` declared in the
registry, so the two cannot silently diverge.

## `scripts/compat/schema_diff.py` -- the CI gate

`python scripts/compat/schema_diff.py BASE.json NEW.json --artifact manifest`

For every consumed path it reports `STABLE`, `NEW`, `OK-FALLBACK` (gone but a
declared fallback survives), or `BREAK` (gone with no surviving fallback). Exit
code is nonzero only on an unguarded `BREAK`, so a future dbt version that moves a
field we read fails the build loudly -- additively and offline. Pass FIRST-PARTY
schemas only.

## `scripts/compat/fetch_schemas.py` -- acquisition (the only networked code)

Downloads canonical schemas from `schemas.getdbt.com` into
`dbt_diagnostics/fixtures/schemas/<artifact>/v<N>.json` and writes
`PROVENANCE.json` (source URL + SHA-256 + size per file). Run in dev/CI, never at
runtime. Defaults: manifest v4-v12, run-results v4-v6, catalog v1, sources v3.

## Self-maintenance (why this needs no per-version code)

Correctness is autonomous: a new dbt version cannot break the tool because
detection degrades to "unverified" and never crashes, and every consumed field has
a live recovery. The acquisition + diff + CI gate are 100% Python and run on a
schedule. A human/AI is needed only to OPTIMIZE -- add a one-line fallback alias
after a confirmed rename so the cheap offline path keeps working instead of falling
back to the (correct but costlier) live recovery. High-confidence renames are
auto-PROPOSED but human-approved, never auto-applied: a silent wrong rename mapping
is worse than graceful degradation.

## How a new dbt version gets validated and added

1. `fetch_schemas.py` caches the new version's schema (and capture a golden
   artifact where a warehouse is available).
2. Run `schema_diff.py --artifact ...` old vs new; review any `OK-FALLBACK`/`BREAK`.
3. If a consumed field moved with no fallback, add the alias to the registry (and
   mirror it in `safe.py`); otherwise no code change is needed.
4. If the schema major is new, add it to `schema_version.SUPPORTED_SCHEMAS` only
   after the matrix is green. Until then the tool already degrades to unverified.
5. Record the version in the findings table and `CHANGELOG.md`.

## Test strategy

`test_compat_schema_diff.py` (marker `unit`) proves the engine offline with
synthetic schemas: union crossing + nullable detection, the
`compiled_code`/`compiled_sql` rename boundary, missing-path returns absent (no
raise), `safe` fallbacks, and registry/`safe` alias agreement. Real first-party
schemas are exercised separately (contract tier) once `fetch_schemas.py` has
populated the cache.
