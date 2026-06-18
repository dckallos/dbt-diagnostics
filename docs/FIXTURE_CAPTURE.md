# Capturing real dbt fixtures

> Read this before adding or regenerating any file under
> `dbt_diagnostics/fixtures/`.

## Principle (non-negotiable)

Fixtures are **real dbt artifacts** captured from real `dbt` runs against a real
Snowflake warehouse. We do **not** hand-author or AI-generate fixture files.
A fabricated artifact looks real, drifts from what dbt actually emits, and
quietly poisons every test that trusts it. This mirrors the project thesis:
first-party artifacts are the source of truth.

Two narrow, clearly-labeled exceptions that are NOT fixtures:

- **Inline dict literals inside a test** used as inputs to a pure function (e.g.
  `safe.catalog_column_type({...}, ...)`). These exercise parser logic, live in
  the test body (never under `fixtures/`), and make no claim to be a captured
  artifact. This is the existing convention in `test_safe_artifact_accessors.py`
  and `test_compat_schema_diff.py`.
- **Synthetic JSON Schemas** for the compat engine's `unit` tests (again inline,
  not under `fixtures/`). Real first-party schemas are exercised at the
  `contract` tier instead.

If a test needs a real artifact that does not exist yet, gate it with
`@pytest.mark.skipif(not FIXTURE.exists(), ...)` and document the capture step
here, rather than fabricating the file.

## Where real fixtures come from: dckallos/artwork-db

The `real_*` fixtures are produced by the failure-injection harness in the
companion repo **dckallos/artwork-db** (the dbt project lives in
`artwork_pipeline/`). `inject_failures.sh` runs a full
inject -> trigger -> capture -> revert cycle and is the standard mechanism:

```
# from the artwork-db repo root, with the dbt venv active and Snowflake configured
./inject_failures.sh --list        # show the 12 scenarios
./inject_failures.sh 12             # run scenario 12, capture, then revert
./inject_failures.sh --all          # regenerate every fixture
```

For each scenario it copies, into `dbt_diagnostics/fixtures/`:

- `target/run_results.json` -> `<name>.json`
- `target/manifest.json`    -> `<name>_manifest.json`

The change is reverted automatically (`inject_failures.py --discard-change`), so
the dbt project is only *temporarily* broken and nothing is committed to
artwork-db.

Scenario -> fixture map (from `inject_failures.sh`):

| # | fixture name |
|---|--------------|
| 1 | real_compilation_source_not_found |
| 2 | real_compilation_ref_not_found |
| 3 | real_syntax_error_001003 |
| 4 | real_division_by_zero_100035 |
| 5 | real_numeric_overflow_100132 |
| 6 | real_string_too_long_100078 |
| 7 | real_object_not_exist_002003 |
| 8 | real_privileges_003001 |
| 9 | real_invalid_identifier_000904 |
| 10 | real_invalid_identifier_lateral_000904 |
| 11 | real_contract_violation_extra_column |
| 12 | real_schema_change_missing_column |

## catalog.json (issue #42): the one extra artifact the harness does not capture

`inject_failures.sh` captures `run_results.json` and `manifest.json` only.
catalog.json is produced separately by `dbt docs generate`, and for the
schema-drift case its whole value is that it reflects the **last-known healthy
schema** -- the column that the injected failure removes must still be present in
the catalog (that is the "before" state the live warehouse is compared against).

So the catalog is captured from a **clean (un-injected) state**, not from the
broken run. Procedure for scenario 12
(`real_schema_change_missing_column`, model `stg_met__artworks`, dropped column
`OBJECT_ID`):

```
# In dckallos/artwork-db, on a clean checkout (NO failure injected):
cd artwork_pipeline

# 1. Build the model so the relation exists in Snowflake with OBJECT_ID present.
dbt build --select stg_met__artworks

# 2. Generate the catalog from that healthy state.
dbt docs generate --select stg_met__artworks

# 3. Copy the real catalog into this repo's fixtures with the scenario name.
cp target/catalog.json \
   ../dbt_diagnostics/fixtures/real_schema_change_missing_column_catalog.json
```

Notes:

- Do this BEFORE (or after a full revert of) any `inject_failures.sh 12` run, so
  `OBJECT_ID` is still in the model. If `dbt docs generate` runs while the model
  is broken, the catalog will be missing the column (or carry an error entry) and
  the fixture loses its meaning.
- `dbt docs generate` runs catalog queries against the warehouse, so a live
  Snowflake connection is required (same as the other `real_*` captures).
- Commit `real_schema_change_missing_column_catalog.json` to dbt-diagnostics.
  Once present, `tests/test_catalog_consumption.py::TestSchemaChangeUsesRealCatalog`
  stops skipping and enforces real-catalog consumption.

### Optional: teach the harness to capture catalog too

If we want catalog capture standardized in artwork-db, extend `inject_failures.sh`
to, for schema-relevant scenarios, run `dbt docs generate` from the clean state
and `cp target/catalog.json "${FIXTURES_DIR}/${name}_catalog.json"` BEFORE the
inject step. That is an artwork-db change (separate repo); raise it there rather
than vendoring a copy here.

## Naming convention

- `real_<scenario>.json`            -- run_results.json
- `real_<scenario>_manifest.json`   -- manifest.json
- `real_<scenario>_catalog.json`    -- catalog.json (healthy, last-known schema)

All three share the `real_<scenario>` stem so a test can load the matching trio.
