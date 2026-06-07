# dbt_diagnostics Classifier Bug Fix -- Multi-Session Plan Prompt

## Role & Standards

You are a **Principal Software Engineer** at a FAANG-tier company. You write production-grade Python with rigorous test coverage, clear separation of concerns, and no hacks. You prefer surgical fixes over rewrites. Every change must have a corresponding test case. You never ship untested code.

---

## CRITICAL: Connection Break Resilience Protocol

**Cortex Code sessions break frequently.** After reviewing every **three files**, you MUST make a tool call (e.g., write a todo list, execute a trivial bash command, or write a progress note). This forces a checkpoint. If the connection breaks, the context window's memory is preserved up to the last tool call.

**Pattern to follow:**
1. Read 3 files
2. Make a tool call (update todo list with findings)
3. Read 3 more files
4. Make a tool call (update todo list again)
5. Continue...

Do NOT read 10 files in sequence without a tool call. You WILL lose work.

---

## Context: What Broke

The `dbt-diagnostics` package (v0.5.0) produces inaccurate diagnoses when run against a real Snowflake dbt project. The errors come from two third-party dbt packages (`dbt_project_evaluator`, `dbt_snowflake_monitoring`) running under a limited-privilege role (`ARTWORK_TRANSFORMER`).

## Ground-Truth Evidence

The file `dbt_diagnostics/fixtures/real_diagnostic_output.txt` contains the ACTUAL output from running `dbt-diagnostics diagnose` against a real dbt project with 23 errors. This is the owner's run -- you cannot reproduce it (you lack the role, account, and artifacts).

**Read this file early.** It is the definitive evidence of what the classifiers currently produce. Your job is to understand WHY the output is wrong by reading the code, not to re-run the tool.

Additionally, `dbt_diagnostics/fixtures/real_run_results_staging_errors.json` and `dbt_diagnostics/fixtures/real_manifest_staging_errors.json` contain the raw dbt artifacts that produced this output. These let you inspect the exact `message` field format that the classifiers receive -- use them to verify hypotheses about what the code actually sees at runtime.

**Do NOT run `dbt-diagnostics diagnose` yourself to evaluate output quality.** You cannot duplicate the owner's environment. Review the static evidence in `real_diagnostic_output.txt` and trace through the code to understand the classification logic.

You MAY run `dbt-diagnostics` or `pytest` for **package development purposes** (e.g., confirming a test passes, checking that a code change doesn't crash, verifying fixture loading). That is different from evaluating diagnostic accuracy -- accuracy is judged against the owner's static output, not your own runs.

---

### IMPORTANT: Epistemic Caveat

The "root cause" hypotheses below are **preliminary observations from a partial code review**. The prior reviewer read only a subset of the package files (classifiers, registry, parts of tracers) and traced the logic by inspection -- NOT by running a debugger, NOT by stepping through with print statements, NOT by examining the actual `run_results.json` artifact (which was unavailable in the workspace).

**Treat these hypotheses pessimistically.** They may be:
- Correct but incomplete (other code paths may interact)
- Correct about symptoms but wrong about the fix location
- Missing context from files not reviewed (enrichers, renderer, test mocks)
- Based on assumptions about the error message format that need verification against actual `run_results.json` output

**Your job is to VERIFY each hypothesis independently** by reading the code, running the tests, and confirming the control flow. Do not trust these observations -- confirm them. The prior reviewer had no ability to run `pytest`, set breakpoints, or examine runtime state.

---

### Suspected Bug 1: Materialization Mismatch Misclassified as "Jinja Syntax Error"

**Actual dbt error message (verbatim from terminal output -- NOT from run_results.json which was unavailable):**
```
Compilation Error in model base_exposure_relationships (models/staging/graph/base/base_exposure_relationships.sql)
  Model must use the table materialization. Please check any model overrides.
  > in macro check_model_is_table (macros/check_model_is_table.sql)
  > called by model base_exposure_relationships (models/staging/graph/base/base_exposure_relationships.sql)
```

**Hypothesis (UNVERIFIED):**
- `CompilationErrorClassifier.matches()` triggers on `"Compilation Error" in message` (line 44 of `classifiers/compilation_error.py`)
- Falls through `_classify_compilation_error()` cases 1 (undefined) and 2 (ref not found) -- neither regex matches
- Lands in `_diagnose_generic()` which says "Jinja compilation failed" and suggests "Review the Jinja syntax"

**Why the prior reviewer THINKS it's wrong:**
- The error appears to be a materialization config conflict, not a Jinja syntax error
- The fix would be `dbt_project.yml` config, not Jinja syntax

**What needs verification:**
- Does the error message in `run_results.json` have the exact same format as the terminal output? (dbt sometimes reformats)
- Is the `_diagnose_generic()` fallback actually what runs? (Could another case match first?)
- Are there other paths through the compilation classifier that could produce this output?
- Does the `message` field in run_results include the full multi-line text or just a summary?

**Affected models:** 9 (all from `dbt_project_evaluator` package)

---

### Suspected Bug 2: Snowflake Shared-Database "Schema Does Not Exist" Falls Through to "UNKNOWN"

**Actual dbt error message (from terminal output):**
```
Database Error in model stg_metering_daily_history (models/staging/stg_metering_daily_history.sql)
  002003 (02000): SQL compilation error:
  Schema 'SNOWFLAKE.ACCOUNT_USAGE' does not exist or not authorized.
  compiled code at target/run/dbt_snowflake_monitoring/models/staging/stg_metering_daily_history.sql
```

**Hypothesis (UNVERIFIED):**
- `RuntimeErrorClassifier.matches()` triggers on `"Database Error" in message`
- `_OBJECT_NOT_FOUND_RE` matches on the error code `002003`
- `_diagnose_object_not_found()` runs and uses `_OBJECT_NAME_RE` to extract the object name
- `_OBJECT_NAME_RE = re.compile(r"Object '([^']+)' does not exist")` -- looks for literal "Object" but message says "Schema"
- `match` is None, so `object_name = "UNKNOWN"` (line 106)

**Why the prior reviewer THINKS it's wrong:**
- Snowflake uses the SAME error code (002003) for tables, schemas, views, and databases
- The regex appears to only handle the `Object '...'` variant

**What needs verification:**
- Is `_OBJECT_NOT_FOUND_RE` actually the regex that triggers the branch? (It has two alternatives joined with `|` -- confirm which one matches)
- Does the `message` field in run_results.json preserve the exact string format shown above?
- Are there other regex patterns in `runtime_error.py` that might also match this message and short-circuit?
- Could the issue be in how `_diagnose_object_not_found` interacts with `trace_object_lineage` rather than (or in addition to) the regex?
- What does the existing `real_object_not_exist_002003.json` test fixture look like? Does it test for this variant?

**Affected models:** 12 (all from `dbt_snowflake_monitoring`)

---

### Suspected Bug 3: Privilege Error Fix Suggestion Says "GRANT SELECT" When the Issue Is "CREATE VIEW"

**Actual dbt error message (from terminal output):**
```
Database Error in model stg_naming_convention_prefixes (models/staging/variables/stg_naming_convention_prefixes.sql)
  003001 (42501): SQL access control error:
  Insufficient privileges to operate on schema 'DBT_TEST__AUDIT'.
  Your primary role ARTWORK_TRANSFORMER must have CREATE VIEW granted on SCHEMA ARTWORK_DB.DBT_TEST__AUDIT.
  compiled code at target/run/dbt_project_evaluator/models/staging/variables/stg_naming_convention_prefixes.sql
```

**Hypothesis (UNVERIFIED):**
- Correctly identifies as a privilege error via `_PERMISSION_DENIED_RE`
- `_diagnose_permission_denied()` extracts the schema name correctly
- But the fix suggestion is generic: `GRANT SELECT ON SCHEMA ...`
- The error message explicitly contains the required privilege ("must have CREATE VIEW granted")

**Why the prior reviewer THINKS it's wrong:**
- The exact missing privilege is stated in the error message
- The fix should echo this privilege rather than defaulting to SELECT

**What needs verification:**
- Read `_diagnose_permission_denied()` in full -- is the generic fix hardcoded or does it attempt extraction?
- Does the regex `_PRIVILEGE_RE` capture the privilege type? If so, is it used in the fix suggestion?
- The diagnostic also reports the schema "does NOT exist in Snowflake" -- is this from the classifier or the enricher? Trace the source.
- Check `enrichers/grants.py` and `enrichers/schema_inspector.py` -- the enricher may be querying with the wrong role or wrong logic

**Verified database state (from live queries this session -- this IS confirmed):**
- `DBT_TEST__AUDIT` schema EXISTS (confirmed via SHOW SCHEMAS)
- `ARTWORK_TRANSFORMER` has `USAGE` + `CREATE TABLE` on it
- `ARTWORK_TRANSFORMER` is MISSING `CREATE VIEW` on it
- The diagnostic output says the schema "does NOT exist in Snowflake" -- this is factually wrong

**Affected models:** 2 (from `dbt_project_evaluator`)

---

## Files to Review

Before making design decisions, review these files in groups of 3 (with tool calls between groups):

**Group A -- Classifiers (the bugs live here):**
1. `dbt_diagnostics/classifiers/compilation_error.py` (189 lines) -- Bug 1 origin
2. `dbt_diagnostics/classifiers/runtime_error.py` (367 lines) -- Bug 2 and Bug 3 origin
3. `dbt_diagnostics/classifiers/registry.py` (32 lines) -- dispatch order
4. `dbt_diagnostics/classifiers/base.py` (62 lines) -- classifier interface

**Group B -- Data models & tracers (downstream of fixes):**
5. `dbt_diagnostics/models.py` (306 lines) -- DiagnosticReport, DiagnosticFinding, LineageStep
6. `dbt_diagnostics/tracers/dag_walker.py` (317 lines) -- trace_object_lineage (used by Bug 2)
7. `dbt_diagnostics/enrichers/schema_inspector.py` (121 lines) -- live existence check (Bug 3 false negative)
8. `dbt_diagnostics/enrichers/grants.py` -- live grant inspection

**Group C -- Tests (must be extended):**
9. `dbt_diagnostics/tests/test_compilation_error.py`
10. `dbt_diagnostics/tests/test_runtime_error.py`
11. `dbt_diagnostics/tests/test_classify.py`
12. `dbt_diagnostics/fixtures/` -- existing fixture JSON files for reference

**Group D -- Rendering & output:**
13. `dbt_diagnostics/renderer.py` -- how findings become human-readable output
14. `dbt_diagnostics/main.py` (536 lines) -- orchestration

---

## Verified Database Facts (from live queries on JHTJUUT-HW58276)

```
SHOW SCHEMAS LIKE 'DBT_TEST__AUDIT' IN DATABASE ARTWORK_DB;
-- Returns 1 row: exists, owner = ARTWORK_ADMIN

SHOW GRANTS TO ROLE ARTWORK_TRANSFORMER;
-- DBT_TEST__AUDIT: USAGE + CREATE TABLE (no CREATE VIEW)
-- SILVER: USAGE + CREATE TABLE + CREATE VIEW
-- GOLD: USAGE + CREATE TABLE + CREATE VIEW
-- No grants on SNOWFLAKE database at all
```

---

## Snowflake Error Message Patterns (from Snowflake docs)

Error code `002003` uses these message variants:
- `Object 'DB.SCHEMA.TABLE' does not exist or not authorized.`
- `Schema 'DB.SCHEMA' does not exist or not authorized.`
- `Table 'DB.SCHEMA.TABLE' does not exist or not authorized.`
- `View 'DB.SCHEMA.VIEW' does not exist or not authorized.`
- `Database 'DB' does not exist or not authorized.`

Error code `003001` includes the specific missing privilege:
- `Insufficient privileges to operate on schema 'X'. Your primary role Y must have CREATE VIEW granted on SCHEMA Z.`
- `Insufficient privileges to operate on table 'X'. Your primary role Y must have SELECT granted on TABLE Z.`

The exact required privilege is ALWAYS stated in the error message after "must have ... granted on".

---

## Design Questions for the Next Session

After verifying (or refuting) the hypotheses above, ask the owner these design questions before coding. **Do not assume the hypotheses are correct when framing the questions** -- adapt them based on what you actually find in the code.

1. **Bug 1 resolution approach (if hypothesis confirmed):** Should the `CompilationErrorClassifier` gain a new sub-case for materialization mismatches (checked before the generic fallback)? Or should a new `MaterializationErrorClassifier` be added to the registry (checked before `CompilationErrorClassifier`)? The tradeoff: a sub-case keeps the registry lean but makes one file fatter; a new classifier is cleaner separation but adds a file. **Or did you find a different root cause that changes the question entirely?**

2. **Bug 2 resolution approach (if hypothesis confirmed):** Should `_OBJECT_NAME_RE` be broadened to match `(Object|Schema|Table|View|Database) '([^']+)' does not exist`? Or should there be separate sub-handlers per object type (since a missing schema has different fix semantics than a missing table)? **Or is the issue somewhere else (e.g., the enricher, the renderer, or a different regex)?**

3. **Bug 3 resolution approach (if hypothesis confirmed):** The error message may explicitly contain the required privilege (e.g., "must have CREATE VIEW granted"). Should the classifier regex-extract this and use it verbatim in the fix suggestion? Or should it also cross-reference with the live grant enricher to confirm? **First verify: does `_diagnose_permission_denied()` already attempt this extraction and fail, or does it never try?**

4. **Test strategy:** Should new fixtures be captured from the real run_results.json (the owner can provide these from their Mac), or should synthetic fixtures be crafted? Real fixtures guarantee accuracy but are verbose; synthetic fixtures are minimal and readable.

5. **Scope boundary:** The `dbt_snowflake_monitoring` errors are fundamentally a privilege gap (ARTWORK_TRANSFORMER lacks SNOWFLAKE.ACCOUNT_USAGE access). Should the classifier provide actionable guidance like "This requires IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE -- consider running this package under a separate role with higher access"? Or just correctly identify the missing schema?

6. **Discovered issues:** Did your independent review uncover bugs or design problems NOT listed in the hypotheses above? If so, present them to the owner as additional scope and ask whether to include them in this fix batch or defer.

---

## Constraints

- Python 3.11+ (match pyproject.toml `requires-python`)
- No new dependencies (use stdlib `re`, existing `sqlglot`, `pyyaml`, `jinja2`)
- Every fix must have a test case in `tests/`
- Maintain backwards compatibility: existing fixture tests must still pass
- Follow existing code patterns (look at how `ContractViolationClassifier` or `SchemaChangeErrorClassifier` were structured)
- Changes must be reviewable in <500 lines total diff

---

## Session Execution Plan

This work spans multiple context windows. The plan:

### Session 1 (this prompt): Design Decisions
- Review the files listed above (in groups of 3 with checkpoint tool calls)
- Ask the 5 design questions above
- Produce a plan document (similar to LINEAGE_TRAIL_PLAN.md) with:
  - Chosen approach for each bug
  - File-by-file change list
  - Test case inventory
  - Execution order

### Session 2: Implement Bug 1 (Materialization Mismatch)
- Code the classifier change
- Write fixture + test
- Run `pytest dbt_diagnostics/tests/` to confirm no regressions

### Session 3: Implement Bug 2 (Object Name Extraction)
- Broaden or refactor the regex/extraction logic
- Write fixture + test for Schema/Table/View/Database variants
- Run tests

### Session 4: Implement Bug 3 (Privilege Fix Suggestion) + Integration Test
- Extract exact privilege from error message
- Fix the enricher false negative (schema reported as non-existent)
- Write end-to-end test with a real-shaped run_results
- Run full test suite

---

## Starting Instructions

1. Read this prompt fully.
2. Read files in Group A (3 files + tool call checkpoint). **As you read, actively challenge the hypotheses above.** Note where you agree, disagree, or find additional context.
3. Read files in Group B (3 files + tool call checkpoint). **Trace the actual control flow for each bug's error message -- do not rely on the prior reviewer's guesses.**
4. Read existing tests and fixtures in Group C (3 files + tool call checkpoint). **Check whether existing tests already cover (or contradict) the hypothesized behaviors.**
5. Present your findings to the owner: which hypotheses you confirmed, which you refuted, and what else you discovered.
6. Ask the design questions (adapted based on your findings).
7. Based on answers, produce the plan document.
8. Write the plan to `dbt_diagnostics/CLASSIFIER_FIX_PLAN.md`.

**Critical mindset:** The prior reviewer was working from static inspection of ~6 files without runtime feedback. You have the ability to run `pytest`, read all files, and trace full call stacks. Use that advantage. If the hypotheses are wrong, say so clearly and explain what's actually happening.
