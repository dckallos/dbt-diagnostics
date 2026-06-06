# dbt_diagnostics CHANGELOG

## v0.3.0 -- 2026-06-06

### Live Enrichment (`--live` flag)

I added the ability to connect to Snowflake and verify findings against the
actual state of the database. Instead of hardcoding assumptions like
"CURRENT_TIMESTAMP returns LTZ by default," the tool now queries
SHOW PARAMETERS and reports the actual value + where it's set.

**What `--live` does:**

- Queries `SHOW PARAMETERS IN SESSION` to get actual values for
  TIMESTAMP_TYPE_MAPPING, TIMEZONE, etc. Reports the effective value
  and which level (account/session/warehouse) it's set at.
- Runs `DESCRIBE TABLE` to get actual column names and types for tables
  referenced in failed models. For "invalid identifier" errors, suggests
  the closest matching column name.
- Runs `SHOW TABLES` to confirm whether a missing object truly doesn't
  exist or if it's a permissions issue.
- Searches `INFORMATION_SCHEMA.QUERY_HISTORY` for the exact query
  Snowflake executed, matched by time window + text similarity.
  Only attaches the result if match confidence >= 80%.

**Design decisions I made:**

- Connection uses the dbt role from profiles.yml. I don't escalate to
  an admin role because that would mean the tool sees things the dbt
  user can't, which leads to misleading advice.
- I parse profiles.yml directly (no dbt-core dependency). I handle
  `env_var('KEY')` and `env_var('KEY', 'default')` via regex substitution.
  This covers real-world profiles. Complex Jinja in profiles will fail
  gracefully with a warning.
- I use INFORMATION_SCHEMA.QUERY_HISTORY (not ACCOUNT_USAGE) for zero
  latency and no privilege escalation. Tradeoff: only sees the current
  role's own queries.
- If --live is passed but the connection fails, the tool warns and falls
  back to offline output. It never crashes because of enrichment failures.
- snowflake-connector-python is an optional dependency. Install with
  `pip install "dbt_diagnostics[live]"`.

---

## v0.2.0 -- 2026-06-06

### Architecture Refactor + RuntimeErrorClassifier

I refactored the tool from "classifiers that print to stdout" to
"classifiers that return structured DiagnosticReport dataclasses, rendered
by Jinja2 templates."

**Structural changes:**

- Created `models.py` with DiagnosticReport, DiagnosticFinding,
  TraceLocation, UpstreamOrigin dataclasses.
- Created `classifiers/base.py` with BaseClassifier ABC and
  DiagnosticContext. Classifiers implement `matches()` and `diagnose()`.
- Created `classifiers/registry.py` with CLASSIFIER_REGISTRY list and
  `classify()` dispatch function. First match wins.
- Moved all `__init__.py` files to imports + `__all__` only. No logic
  defined in init files.
- Added Jinja2 templates under `templates/` -- one per error class.
  Templates own presentation; classifiers own analysis.
- Added `renderer.py` that loads templates and produces output.
- Added `__main__.py` so `python -m dbt_diagnostics` works.
- Created `pyproject.toml` so the tool installs as a proper package.
- Dropped `dbt-artifacts-parser` dependency (was imported but unused).

**New classifier: RuntimeErrorClassifier**

Handles Snowflake execution errors (the model compiled fine but failed
when Snowflake tried to run it):

- Object does not exist (002003) -- checks manifest to see if the object
  is a known parent that failed upstream vs genuinely missing DDL.
- Invalid identifier (000904) -- extracts the column name and line number
  from Snowflake's error, checks upstream column declarations.
- Insufficient privileges (003001) -- identifies the object and produces
  the GRANT statement to fix it.

**CLI:**
- `dbt-diagnostics` -- diagnose from artifacts
- `dbt-diagnostics demo` -- run against bundled fixtures
- `dbt-diagnostics --json` -- machine-readable output

---

## v0.1.0 -- 2026-06-06

### Initial Build

I built the first working version of the diagnostic tool. It handles one
error class: dbt contract type mismatches.

**How it works:**

1. Reads `run_results.json` (errors) and `manifest.json` (DAG structure)
   from the dbt target/ directory.
2. Classifies the error by substring matching on the message.
3. For contract violations: parses the pipe-delimited mismatch table from
   the error message using regex.
4. Uses sqlglot to parse the compiled SQL and find the exact expression
   that produces the mismatched column (e.g., CURRENT_TIMESTAMP()).
5. Uses the DAG walker to check if the column is inherited from upstream
   or introduced in the current model.
6. Reports the file, line number (text search in source .sql), CTE,
   expression, and relevant session parameters to check.

**Known limitation:** The column tracer's `find_all(exp.Alias)` recurses
into CTEs from the outer SELECT, so `cte_name` attribution is unreliable
when the outer SELECT passes through a CTE column without re-aliasing.

**Dependencies:** sqlglot, pyyaml (and jinja2 as of v0.2.0).
