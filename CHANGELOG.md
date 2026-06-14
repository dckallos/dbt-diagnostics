# dbt_diagnostics CHANGELOG

## [Unreleased]

### Added -- single-root-cause aggregator (issue #7, epic #4 Live Verification Engine)

- `root_cause.py`: collapses many same-signature "object does not exist"
  (Snowflake 002003) errors into one `RootCauseGroup`, so N identical failures
  render as a single root-cause line instead of N. For each missing object it
  emits one verdict, disambiguated by a Tier-A ($0 metadata) live probe:
  - none exist now  -> tests ran before materialize; run `dbt build`, not
    `dbt test`.
  - exists now      -> built by another process / transient; re-run.
  - exists, denied  -> routed to a grant check (SHOW GRANTS TO ROLE).
  The "denied" branch is decided by grants, never by a bare `table_exists`
  False -- SHOW TABLES cannot distinguish "absent" from "invisible to this
  role". Offline, or when a probe cannot confirm state, the verdict degrades to
  "unverified" and carries the exact query to run; it never crashes.
- `enrichers/run_identity.py`: recovers the role the dbt run actually used
  rather than inferring it. Fidelity ladder -- Tier 0 recovered (failing
  query_id -> INFORMATION_SCHEMA.QUERY_HISTORY.ROLE_NAME), Tier 2 declared (dbt
  profile/target role), Tier 3 session (CURRENT_ROLE()). An empty query-id
  lookup is classified "not yet" (history lagging) vs "never" (out of window /
  invisible) by a watermark comparison, with one short bounded retry; a drift
  warning is emitted when the recovered role disagrees with the declared one.
  Near-real-time (INFORMATION_SCHEMA, not ACCOUNT_USAGE).
- Terminal output gains a ROOT CAUSE section that reuses the existing
  `findings/lineage_trace.j2` partial.
- `--json`: `schema_version` bumped `1.0` -> `1.1` (additive only) with a new
  top-level `root_cause_groups` array. No existing keys changed.
- Tests: `tests/test_root_cause.py`, `tests/test_run_identity.py`.

---

## v0.5.0 -- 2026-06-07 (workspace only; not yet tested on Mac)

### Lineage Trail Enhancement (Phase 1 + Phase 2)

I shipped the full lineage trail feature: every error diagnosis now shows a
visual breadcrumb trail upstream through the DAG, with compiled SQL context
and a verdict naming the exact disconnect point. Live enrichment is ON by
default (DESCRIBE TABLE populates each trail step).

**Phase 1 -- Template + Renderer Layer (sub-tasks 5-6):**

- Created `templates/findings/lineage_trace.j2` -- reusable Jinja2 partial
  that renders both the compiled SQL snippet and the lineage trail. Included
  by all four error-class templates via `{% include %}`.
- Updated `colors.py` with `status_indicator()` helper (emoji vs text
  fallback depending on `color_enabled`).
- Updated `renderer.py` -- `_build_env()` now sets `color_enabled` and
  `verbose` as Jinja globals so included partials can branch on them.
  Registered `status_indicator` as a Jinja filter.
- Updated all error-class templates (`runtime_error.j2`, `schema_change_error.j2`,
  `data_error.j2`, `compilation_error.j2`) to include the lineage trace partial
  after root-cause and before fix suggestion. Each sets an appropriate
  `trace_target` (column name, FQ object, "data flow", "compilation").
- Fixed `runtime_error.j2` trace_target to fall back to `finding.target_object`
  when `target_identifier` is None (object-not-found errors).
- Created `tests/test_lineage_integration.py` -- 57 integration tests covering
  all 12 real fixtures across color/no-color/verbose modes. Parametrized over
  every fixture to verify no-crash, trail structure, and rendering.

**Phase 2 -- Live Enrichment Wiring (sub-tasks 2a-2d):**

- Flipped `--live` to `--no-live` in `main.py`. Live enrichment is now ON by
  default with graceful fallback (missing connector -> warn + continue offline;
  connection failure -> warn + continue offline; `--no-live` -> silent skip).
- Added `_enrich_lineage_trail()` in `enrichers/enrich.py` -- iterates each
  LineageStep with a `relation_name`, calls `table_exists()` and
  `describe_table()` to populate `live_status` / `live_detail`. For
  column-lineage findings, checks whether the specific target column exists.
- Created `enrichers/grants.py` (new file) with `check_role_grants()` and
  `get_current_role()` -- SHOW GRANTS TO ROLE wrapper for privilege-error
  diagnosis. Exported via `enrichers/__init__.py`.
- Added `_identify_disconnect()` in `enrichers/enrich.py` -- scans the trail
  for the pass-to-fail transition after live enrichment, populates
  `finding.disconnect` (DisconnectVerdict) with between-nodes, explanation,
  and confidence level.

**Acceptance criteria met:**

- 288 tests passing (231 existing + 57 new integration tests).
- Running any fixture through classifier + renderer produces:
  - "COMPILED SQL (line N):" section when snippet exists
  - "LINEAGE TRACE:" section when trail is non-empty
  - Correct emoji/text status per step
- `--no-color` mode produces `[PASS]`/`[FAIL]`/`[????]` instead of emoji.
- `--no-live` suppresses all Snowflake queries.
- Default mode attempts live enrichment with graceful fallback.
- DisconnectVerdict populated with correct between-nodes.
- "VERDICT:" line appears in rendered output.

**Files created:** `templates/findings/lineage_trace.j2`, `enrichers/grants.py`,
`tests/test_lineage_integration.py`.

**Files modified:** `colors.py`, `renderer.py`, `main.py`,
`enrichers/enrich.py`, `enrichers/__init__.py`,
`templates/findings/runtime_error.j2`, `templates/findings/schema_change_error.j2`,
`templates/findings/data_error.j2`, `templates/findings/compilation_error.j2`.

---

## v0.4.0 -- 2026-06-06

### Self-Contained CLI + Major Enhancement Pass

I made the tool fully self-contained: it works zero-config in any dbt project
directory. I also shipped 12 enhancements covering CLI UX, output quality,
bug fixes, and a new classifier.

**CLI is now self-contained (Enhancement #1):**

- Every value that was in `config.yml` is now a CLI flag with auto-detection.
  The tool walks up from cwd to find `dbt_project.yml`, reads the profile name
  from it, finds `profiles.yml` (project-local first, then `~/.dbt/`), and
  reads the default target. Zero files required.
- Added `--project-dir`, `--profile`, `--target`, `--run-results`, `--manifest`
  for explicit overrides.
- Added `--env-file` flag to specify a `.env` path for `env_var()` resolution.
  Previously this relied on auto-detection only.
- Added `--config` as an optional convenience (never required). The tool never
  fails because `config.yml` is missing.
- New `discover.py` module handles all project auto-detection logic.

**Output modes (Enhancement #11):**

- Default mode: shows ROOT CAUSE + FIX only. Clean, fast, actionable.
- `--verbose`: adds ORIGIN, EXPLANATION, all session params, full skipped
  model names, raw query history detail.
- This is a renderer-level switch -- classifiers are unchanged.

**Enrichment improvements (#2, #3, #12):**

- Added `python-dotenv>=1.0.0` to `[live]` dependencies. Previously it
  silently skipped `.env` loading, making `--live` fail for profiles using
  `env_var()`.
- Classifiers now tag which session params are _diagnostic_ (directly explain
  the error, e.g. TIMESTAMP_TYPE_MAPPING) vs _contextual_ (useful background,
  e.g. TIMEZONE). Default mode shows only diagnostic params; `--verbose` shows all.
- Post-enrichment reconciliation pass: if the live TIMESTAMP_TYPE_MAPPING
  matches what the contract expects (both NTZ), I replace the cast suggestion
  with "your build ran under different session settings." If it's LTZ and the
  contract wants NTZ, I prepend "CONFIRMED" to strengthen the fix. This
  eliminates the misleading "Cast to NTZ" when the mapping is already NTZ.

**Skipped model truncation (Enhancement #4):**

- Default mode: shows short model names (e.g., `dim_artworks`) and groups tests
  as "N test(s) skipped (downstream)."
- `--verbose`: shows full `unique_id` strings.

**Model short name in ORIGIN (Enhancement #6):**

- ORIGIN section now says "introduced in THIS model (dim_artists)" instead of
  just "introduced in THIS model."

**CTE attribution fix (Enhancement #5):**

- Fixed `_find_alias_in_select` which used `find_all(exp.Alias)` -- this
  recursed into CTE definitions from the outer SELECT, making `cte_name`
  always None. Now uses `select_node.expressions` (direct projection list)
  for the outer SELECT, and explicitly walks each CTE with `cte_name` set.
  `cte_name` is now correctly populated in trace results.

**Smart "did you mean?" (Enhancement #8):**

- Replaced the naive substring/prefix match with `difflib.get_close_matches()`
  (stdlib). Shows the closest column name with Levenshtein edit distance inline.

**Query history in output (Enhancement #9):**

- `RAW ERROR (from Snowflake)` section with `error_code` and `error_message`
  now shows in DEFAULT mode (not just verbose) when `--live` finds a match.
  This is critical for ambiguous 002003 errors.

**Cascading error detection (Enhancement #7):**

- After classification, I check if any errored model is a parent of another
  errored model via the DAG. Downstream errors get a CASCADE annotation:
  "This failure is likely caused by the error in upstream model(s): stg_foo.
  Fix that first."

**Compilation Error classifier (Enhancement #10):**

- New `classifiers/compilation_error.py` handles "Compilation Error" messages.
- Three sub-patterns: undefined name (typo in a macro), ref target not found
  (model doesn't exist), and generic Jinja syntax errors.
- For ref-not-found: uses `difflib.get_close_matches()` against all model
  names in the manifest to suggest typo corrections.
- Extracts line number from dbt's Jinja traceback when available.
- Includes fixture JSON + 6 tests.

**Test count:** 62 -> 104 (all passing).

---

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
