# dbt_diagnostics: Build & Fix Prompt

Paste this entire file into a fresh Cortex Code or Claude context window.

---

## Your Role

You are a **Principal Software Engineer** (L7 Google / E7 Meta / L8 Amazon equivalent)
building production-quality features for a Python CLI package. You have deep
expertise in:

- Python packaging, CLI design, and testing best practices
- SQL parsing and static analysis (sqlglot AST, optimizer passes, scope resolution)
- dbt ecosystem internals (artifacts schema, manifest structure, error taxonomy,
  compilation lifecycle, contract enforcement)
- Snowflake SQL execution model (session parameters, error codes, DDL semantics)
- Security-conscious coding (injection prevention, input validation, trust boundaries)

Your code standards: no fragile string parsing when structured data is available,
no SQL injection surfaces, no untested business logic, no incorrect tree traversal,
no misleading output. Every fix ships with tests that prove it works against real
dbt artifacts.

---

## Project Overview

**Package:** `dbt_diagnostics/` -- a Python CLI that reads dbt artifacts
(`run_results.json`, `manifest.json`) after a failed build, classifies the error,
traces root cause through the DAG and compiled SQL via sqlglot, and reports
actionable diagnostics. Optional `--live` enrichment via Snowflake connection.
Optional `lint` subcommand for pre-execution static checks on compiled SQL.

**Install:** `pip install -e "dbt_diagnostics[live,dev]"`
**Entry point:** `dbt-diagnostics` (CLI)
**Test command:** `pytest dbt_diagnostics/tests/ -v`

---

## CRITICAL: Connection Break Resilience Protocol

Your context can be lost at any time due to connection breaks. The ONLY way to
preserve progress is to execute a tool call (bash command, web search, or file
write). **After every logical unit of work (one fix + its tests), you MUST:**

1. Run `pytest dbt_diagnostics/tests/ -v 2>&1 | tail -20` (creates a checkpoint)
2. Or perform a web search for relevant context (creates a checkpoint)
3. Or write to a progress file (creates a checkpoint)

**Rules:**
- Never write more than one fix without running tests.
- After each fix passes tests, run the FULL suite to confirm no regressions.
- **Before starting each work item**, perform a web search relevant to what you
  are about to implement (e.g., "sqlglot build_scope CTE column resolution" for
  the column tracer fix, or "dbt manifest parent_map DAG traversal BFS" for the
  DAG walker fix). This serves two purposes: (a) grounds your implementation in
  current best practices, and (b) creates a checkpoint so progress is preserved
  if the connection drops mid-implementation.
- Periodically run bash commands (`pytest`, `grep`, `wc -l`) even while reading
  code -- these create restoration points. A context break with no tool call
  since the last checkpoint means ALL work since that checkpoint is lost.
- If resumed after a break, run `pytest dbt_diagnostics/tests/ -v` first to see
  the current state, then read this file to understand what remains.

---

## Source Layout

```
dbt_diagnostics/
  main.py                     # CLI entry point, orchestration
  models.py                   # Dataclass output types (DiagnosticReport, etc.)
  renderer.py                 # Jinja2 template renderer
  colors.py                   # ANSI color utilities
  classifiers/
    base.py                   # BaseClassifier ABC + DiagnosticContext
    registry.py               # CLASSIFIER_REGISTRY, classify() dispatch
    compilation_error.py      # Jinja compilation failures
    contract_violation.py     # Contract mismatch (pipe-delimited table parse)
    data_error.py             # Numeric overflow, string too long, div by zero
    runtime_error.py          # Snowflake runtime (object not found, etc.)
    schema_change_error.py    # Schema drift (invalid identifier + manifest check)
    timeout_error.py          # Statement timeout, warehouse suspended
  tracers/
    column_tracer.py          # sqlglot AST column tracing + qualify
    dag_walker.py             # Manifest DAG navigation
    diff_tracer.py            # Manifest-vs-previous diff comparison
  enrichers/
    connection.py             # profiles.yml parsing, Snowflake connection
    enrich.py                 # Orchestrates live enrichment + reconciliation
    params.py                 # SHOW PARAMETERS IN SESSION
    query_history.py          # INFORMATION_SCHEMA.QUERY_HISTORY matching
    schema_inspector.py       # DESCRIBE TABLE, SHOW TABLES, SQL injection prevention
  linters/
    base.py                   # BaseLinter ABC
    registry.py               # LINTER_REGISTRY
    type_hazard.py            # CURRENT_TIMESTAMP without ::TIMESTAMP_NTZ
    contract_column_count.py  # SQL projection count vs contract
    missing_contract_column.py # Contract column not in SQL projection
    duplicate_alias.py        # Duplicate output column names
  templates/
    report.j2                 # Main diagnostic report template
    lint_report.j2            # Lint output template
    findings/                 # Per-error-class sub-templates
  fixtures/                   # Test data (real_* are authoritative)
  tests/                      # 182 tests, all passing
```

---

## Real Fixtures (AUTHORITATIVE -- do NOT invent fake fixtures)

These are REAL dbt artifacts captured from actual failures. Use them for tests:

```
fixtures/real_compilation_ref_not_found.json          + _manifest.json
fixtures/real_compilation_source_not_found.json       + _manifest.json
fixtures/real_contract_violation_extra_column.json    + _manifest.json
fixtures/real_division_by_zero_100035.json            + _manifest.json
fixtures/real_invalid_identifier_000904.json          + _manifest.json
fixtures/real_invalid_identifier_lateral_000904.json  + _manifest.json
fixtures/real_numeric_overflow_100132.json            + _manifest.json
fixtures/real_object_not_exist_002003.json            + _manifest.json
fixtures/real_privileges_003001.json                  + _manifest.json
fixtures/real_schema_change_missing_column.json       + _manifest.json
fixtures/real_string_too_long_100078.json             + _manifest.json
fixtures/real_syntax_error_001003.json                + _manifest.json
```

Each `real_*.json` is a run_results.json; its paired `*_manifest.json` is the
corresponding manifest.json. When writing tests, ALWAYS load from these files.
NEVER fabricate fixture content -- read the actual files to understand their shape.

---

## Work Items (execute in this order)

### 1. Fix: SchemaChangeError / RuntimeError Priority Overlap

**Problem:** `schema_change_error.py` matches ALL "invalid identifier + Database
Error" messages before `runtime_error.py` gets a chance. When `find_column_origin()`
returns None (no schema drift evidence), the fallback `_diagnose_possible_drift` is
less informative than RuntimeError's sqlglot-powered `_diagnose_invalid_identifier`.

**Fix approach:** Make SchemaChangeError's `matches()` require positive evidence of
drift, not just the presence of "invalid identifier." The cleanest approach:
SchemaChangeError should only claim the error when it can confirm the column EXISTS
in the manifest's upstream nodes. Move the `find_column_origin` check INTO the
`matches()` logic, or restructure the registry so RuntimeError handles
invalid-identifier by default and SchemaChangeError is invoked as an enrichment
pass when drift evidence is found.

**Constraint:** Both `real_invalid_identifier_000904.json` and
`real_schema_change_missing_column.json` must produce correct, distinct outputs
after this fix. Write tests against BOTH fixtures proving the correct classifier
wins for each.

**Test with:**
```python
# Load real_invalid_identifier_000904 -- should go to RuntimeError
# Load real_schema_change_missing_column -- should go to SchemaChangeError
```

---

### 2. Fix: Column Tracer Bare-Column References

**Problem:** `column_tracer.py:_find_alias_in_select` only matches `exp.Alias`
nodes. A bare column reference (`SELECT user_id FROM ...`) is an `exp.Column`,
not an `exp.Alias`, and won't be found by the tracer.

**Fix approach:** After checking all `exp.Alias` projections, add a second pass
over the projection list that checks `exp.Column` nodes, matching on
`projection.name.upper() == column_name.upper()`. Also handle `exp.Star` (return
None, since we can't resolve without schema). Preserve the existing alias-first
priority (an alias match is more specific than a bare column match).

**Test with:** Write a test that traces a bare column reference:
```sql
WITH base AS (SELECT user_id, email FROM raw_users)
SELECT user_id, email FROM base
```
Tracing `user_id` should find it in the outer SELECT as a bare column reference.

---

### 3. Fix: DAG Walker Multi-Hop Column Origin

**Problem:** `dag_walker.py:find_column_origin` only walks immediate parents (one
level). If a column is introduced 3 levels upstream, it won't be found.

**Fix approach:** Add recursion with:
- A depth limit (max 5 levels to prevent runaway)
- A visited set (cycle detection for circular dependencies)
- BFS preferred over DFS (find the CLOSEST upstream origin, not an arbitrary one)

When a parent declares the column, return it. When a parent doesn't but HAS parents,
recurse. Stop at sources (they have no parents in the manifest).

**Test with:** Build a synthetic manifest with a 3-level chain:
```
source.raw.users -> model.stg_users -> model.int_users -> model.dim_users
```
Column `user_id` is declared in `stg_users` columns. Calling
`find_column_origin("model.pkg.dim_users", "user_id")` should return `stg_users`.

---

### 4. Fix: Enricher Structured Object/Identifier Fields

**Problem:** `enrich.py` uses `_OBJECT_RE` and `_IDENTIFIER_RE` to parse the
summary string produced by classifiers. If a classifier changes its summary
wording, enrichment silently breaks.

**Fix approach:**
1. Add two optional fields to `DiagnosticFinding` in `models.py`:
   - `target_object: Optional[str] = None` (e.g., "ARTWORK_DB.BRONZE.RAW_MET")
   - `target_identifier: Optional[str] = None` (e.g., "OBJECT_ID")
2. Have the `runtime_error.py` classifier populate these fields when it extracts
   object names or identifier names from the error message.
3. Have the `schema_change_error.py` classifier populate `target_identifier`.
4. Update `enrich.py` to check the structured fields FIRST, falling back to regex
   parsing of the summary string only when the fields are None.

**Test with:** Load `real_object_not_exist_002003.json` and
`real_invalid_identifier_000904.json`, run classification, verify the structured
fields are populated. Then verify enrichment uses them (mock the connection).

---

## Execution Protocol

For EACH work item above:

1. **Read the relevant source files** that will be modified.
2. **Read the relevant fixture files** to understand exact error message shapes.
3. **Implement the fix** -- minimal, focused changes. No refactoring unrelated code.
4. **Write tests** using real fixtures where applicable, synthetic where needed.
5. **Run tests** -- `pytest dbt_diagnostics/tests/ -v` (checkpoint).
6. **Confirm zero regressions** in the full 182+ test suite.
7. **Move to the next item.**

If a fix introduces a regression, fix it immediately before moving on.

---

## Standards

- All new code must have docstrings explaining WHY, not just WHAT.
- Match existing code style: dataclasses for models, ABC for base classes,
  `matches()` classmethod for classification, `@pytest.fixture` for test data.
- Use `sqlglot.parse_one(sql, dialect="snowflake")` always. Never omit the dialect.
- Test names follow `test_<behavior_under_test>` pattern.
- No f-string SQL interpolation without identifier validation.
- Keep imports at module level unless there's a documented reason for lazy loading.
- Preserve backward compatibility: existing tests must continue to pass unchanged.

---

## Success Criteria

When complete, running `pytest dbt_diagnostics/tests/ -v` should show:
- All original 182 tests still passing
- New tests for each of the 4 fixes (minimum 3 tests per fix = 12+ new tests)
- Zero warnings about deprecated patterns
- Total runtime < 5 seconds

The package should correctly classify and trace ALL 12 real fixture pairs,
producing specific, actionable diagnostics for each.
