# Classifier Fix Plan -- Execution Summary

**Date:** 2026-06-07
**Status:** Complete (Python fixes applied; IaC + dbt config already in place)

---

## What Was Done

### Bug 1: Materialization Mismatch (9 errors from `dbt_project_evaluator`)

**Root cause confirmed:** `CompilationErrorClassifier._classify_compilation_error()` had no
case for "Model must use the X materialization" messages. They fell through to
`_diagnose_generic()` which produced misleading "Jinja compilation failed" / "Review the
Jinja syntax" output.

**Fix applied:**
- Added `_MATERIALIZATION_RE` regex to `classifiers/compilation_error.py`
- Added Case 3 in `_classify_compilation_error()` before the generic fallback
- Added `_diagnose_materialization_mismatch()` method producing correct summary + fix
- Added fixture entry to `fixtures/compilation_errors.json`
- Added `TestMaterializationMismatch` class with 4 test cases to `tests/test_compilation_error.py`

**Files changed:**
- `dbt_diagnostics/classifiers/compilation_error.py` (+40 lines)
- `dbt_diagnostics/fixtures/compilation_errors.json` (+7 lines)
- `dbt_diagnostics/tests/test_compilation_error.py` (+69 lines)

**dbt config fix (already present):** `dbt_project.yml` line 45 already sets
`dbt_project_evaluator: +materialized: table`, which prevents this error from recurring.

---

### Bug 2: Schema "does not exist" (12 errors from `dbt_snowflake_monitoring`)

**Root cause confirmed:** `_OBJECT_NAME_RE` only matched `Object '...'` format but
Snowflake uses `Schema '...'`, `Table '...'`, `View '...'`, `Database '...'` for error
code 002003. Result: `object_name = "UNKNOWN"` cascaded through the entire diagnostic.

**Fix (pre-existing in codebase):**
- `_OBJECT_NAME_RE` already broadened to `(Object|Schema|Table|View|Database) '([^']+)'`
- `_diagnose_object_not_found()` already uses group(1) for type, group(2) for name
- Type-specific branches for schema (suggests IMPORTED PRIVILEGES) and database already exist
- Tests already in place: `TestSchemaNotFound` (3 test cases)
- Fixture already has Schema variant in `fixtures/runtime_errors.json` result[3]

**No code change needed this session.**

---

### Bug 3: Privilege fix says "GRANT SELECT" when "CREATE VIEW" is needed (2 errors)

**Root cause confirmed:** `_diagnose_permission_denied()` hardcoded `GRANT SELECT` in
the fix suggestion. Snowflake 003001 messages always contain
`"must have {PRIVILEGE} granted on {TYPE} {FQ_NAME}"` -- this was not extracted.

**Fix (pre-existing in codebase):**
- `_REQUIRED_PRIVILEGE_RE` already extracts the specific privilege from the message
- `_diagnose_permission_denied()` already uses it: if extracted, suggests the exact grant;
  falls back to USAGE for legacy messages without "must have"
- Tests already in place: `TestPrivilegeExtraction` (4 test cases)
- Fixture already has "must have CREATE VIEW" variant in `fixtures/runtime_errors.json` result[4]

**No code change needed this session.**

**IaC (already present):** `infrastructure/create_grants.sql` line 55 already contains
`GRANT CREATE VIEW ON SCHEMA ARTWORK_DB.DBT_TEST__AUDIT TO ROLE ARTWORK_TRANSFORMER`.
Requires `make infra` to apply to the account.

---

## Test Results

```
299 passed, 0 failed (11.01s)
```

All existing tests continue to pass. The 4 new materialization tests also pass.

---

## Remaining Actions (owner-side)

1. **Apply IaC to account:** Run `make infra` on the Mac to apply the grants
   (specifically the CREATE VIEW on DBT_TEST__AUDIT) to the live Snowflake account.
   This fixes 2 of the 23 errors at the infrastructure level.

2. **Re-run dbt:** After `make infra`, run `dbt build` to verify:
   - The 9 materialization errors are gone (dbt_project.yml config already correct)
   - The 2 privilege errors are gone (CREATE VIEW grant now applied)
   - The 12 SNOWFLAKE.ACCOUNT_USAGE errors remain (expected -- Option D: correct
     diagnosis, no grant)

3. **Re-run diagnostics:** Run `dbt-diagnostics diagnose` to verify the classifier
   output quality against remaining errors.

---

## Design Decisions Recorded

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Sub-case in CompilationErrorClassifier (not new classifier) | Keeps registry lean; only ~40 lines added |
| 2 | Broadened `_OBJECT_NAME_RE` with type-aware branches | Single handler with if/elif on object type; avoids file sprawl |
| 3 | Extract exact privilege from error message | Snowflake always states the required privilege; echo it verbatim |
| 4 | Option D for SNOWFLAKE database access | Least privilege; correct diagnosis without granting sensitive access |
| 5 | `drop_grants.sql` remains no-op | Grants cascade with parent object drops; explicit REVOKE would be fragile |
