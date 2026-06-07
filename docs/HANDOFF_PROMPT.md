# dbt_diagnostics: Lineage Trail Implementation Prompt

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
- Snowflake metadata operations (DESCRIBE TABLE, SHOW GRANTS, cloud services layer)
- Jinja2 templating for CLI output rendering
- BFS/DFS graph traversal for DAG lineage
- Security-conscious coding (injection prevention, input validation, trust boundaries)

Your code standards: no fragile string parsing when structured data is available,
no SQL injection surfaces, no untested business logic, no incorrect tree traversal,
no misleading output. Every feature ships with tests that prove it works against
real dbt artifacts.

---

## Project Overview

**Package:** `dbt_diagnostics/` -- a Python CLI that reads dbt artifacts
(`run_results.json`, `manifest.json`) after a failed build, classifies the error,
traces root cause through the DAG and compiled SQL via sqlglot, and reports
actionable diagnostics with lineage trails showing where things break.

**Install:** `pip install -e "dbt_diagnostics[live,dev]"`
**Entry point:** `dbt-diagnostics` (CLI)
**Test command:** `pytest dbt_diagnostics/tests/ -v`

### What Has Already Been Built (Work Items 1-4)

These are COMPLETE and tested (202 tests passing). Do not redo them:

1. **SchemaChangeError/RuntimeError priority fix** -- RuntimeErrorClassifier is now
   the primary handler for invalid-identifier errors. It delegates to
   SchemaChangeErrorClassifier only when `find_column_origin()` finds drift evidence.
   SchemaChangeError.matches() always returns False (delegate-only pattern).

2. **Column tracer bare-column references** -- `_find_alias_in_select` now has a
   separate `_find_bare_column_in_select` method. Priority: outer aliases -> CTE
   aliases -> CTE bare columns -> outer bare columns.

3. **DAG walker multi-hop BFS** -- `find_column_origin` uses `collections.deque`
   BFS with `max_depth=5` and a `visited` set for cycle detection. Extracted
   `_node_has_column` helper.

4. **Structured enricher fields** -- `DiagnosticFinding` has `target_object` and
   `target_identifier` fields populated by classifiers. Enricher prefers structured
   fields over regex parsing of summary strings.

---

## CRITICAL: Connection Break Resilience Protocol

Your context can be lost at any time due to connection breaks. The ONLY way to
preserve progress is to execute a tool call (bash command, web search, or file
write). **After every logical unit of work, you MUST:**

1. Run `pytest dbt_diagnostics/tests/ -v 2>&1 | tail -20` (creates a checkpoint)
2. Or run a bash command like `wc -l` on the file you just wrote
3. Or write to a progress tracking comment in your code

**Rules:**
- Never write more than one new file without running tests or a bash command.
- After each sub-task passes tests, run the FULL suite to confirm no regressions.
- Periodically run bash commands (`pytest`, `grep`, `wc -l`, `ls`) even while
  reading code -- these create restoration points.
- A context break with no tool call since the last checkpoint means ALL work
  since that checkpoint is LOST.
- If resumed after a break, run `pytest dbt_diagnostics/tests/ -v` first to see
  the current state, then read this file to understand what remains.

---

## CRITICAL: Fork Detection Protocol

Cortex Code can spawn parallel sessions (forks) that both write to the same
workspace. If you discover work that you didn't do:

**Detection signals:**
- Test count is HIGHER than expected (e.g., 215 instead of 202)
- Files exist that you haven't created yet (e.g., `tracers/snippet.py` already has content)
- Templates already include `lineage_trace.j2`
- `models.py` already has `LineageStep` or `CompiledSnippet` dataclasses
- `main.py` already has `--no-live` flag

**What to do when you detect a fork:**
1. Do NOT redo work. Do NOT overwrite the fork's files.
2. Run `pytest dbt_diagnostics/tests/ -v` to confirm the fork's work passes.
3. Read the new files to understand what the fork implemented.
4. Continue from where the fork left off.
5. If the fork's work is incomplete or broken (tests fail), fix it minimally
   rather than rewriting from scratch.

**Session-open verification sequence (ALWAYS run these first):**
```bash
# Step 1: Confirm test baseline
pytest dbt_diagnostics/tests/ -v 2>&1 | tail -5

# Step 2: Check for fork artifacts
ls dbt_diagnostics/tracers/snippet.py 2>&1
grep -l "LineageStep" dbt_diagnostics/models.py 2>&1
grep -l "no-live\|no_live" dbt_diagnostics/main.py 2>&1
ls dbt_diagnostics/templates/findings/lineage_trace.j2 2>&1

# Step 3: Count current tests
pytest dbt_diagnostics/tests/ --co 2>&1 | tail -1
```

If Step 2 shows existing files, a fork has been here. Read them before proceeding.

---

## Source Layout

```
dbt_diagnostics/
  main.py                     # CLI entry point, orchestration
  models.py                   # Dataclass output types (DiagnosticReport, etc.)
  renderer.py                 # Jinja2 template renderer
  colors.py                   # ANSI color utilities
  discover.py                 # dbt project auto-detection
  classifiers/
    base.py                   # BaseClassifier ABC + DiagnosticContext
    registry.py               # CLASSIFIER_REGISTRY, classify() dispatch
    compilation_error.py      # Jinja compilation failures
    contract_violation.py     # Contract mismatch (pipe-delimited table parse)
    data_error.py             # Numeric overflow, string too long, div by zero
    runtime_error.py          # Snowflake runtime (object not found, etc.)
    schema_change_error.py    # Schema drift (delegate from runtime_error)
    timeout_error.py          # Statement timeout, warehouse suspended
  tracers/
    column_tracer.py          # sqlglot AST column tracing + qualify
    dag_walker.py             # Manifest DAG navigation (BFS multi-hop)
    diff_tracer.py            # Manifest-vs-previous diff comparison
    snippet.py                # [TO CREATE] Compiled SQL snippet extraction
  enrichers/
    connection.py             # profiles.yml parsing, Snowflake connection
    enrich.py                 # Orchestrates live enrichment + reconciliation
    params.py                 # SHOW PARAMETERS IN SESSION
    query_history.py          # INFORMATION_SCHEMA.QUERY_HISTORY matching
    schema_inspector.py       # DESCRIBE TABLE, SHOW TABLES
    grants.py                 # [TO CREATE Phase 2] SHOW GRANTS TO ROLE
  linters/                    # Pre-execution lint (not affected by this work)
  templates/
    report.j2                 # Main diagnostic report template
    lint_report.j2            # Lint output template
    findings/                 # Per-error-class sub-templates
      lineage_trace.j2        # [TO CREATE] Lineage trail partial
      runtime_error.j2
      schema_change_error.j2
      data_error.j2
      compilation_error.j2
      timeout_error.j2
      generic.j2
  fixtures/                   # Test data (real_* are authoritative)
  tests/                      # 202 tests passing (baseline)
    test_snippet.py           # [TO CREATE]
    test_lineage_trail.py     # [TO CREATE]
```

---

## Real Fixtures (AUTHORITATIVE -- do NOT invent fake fixtures)

These are REAL dbt artifacts captured from actual failures:

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

## The Plan of Record

**Read `dbt_diagnostics/LINEAGE_TRAIL_PLAN.md` for full details.** It contains:
- Section 3: Output targets for all 12 error types (the "destination" for each)
- Section 5: Architecture (data structures, methods, templates)
- Section 6: Phase breakdown with acceptance criteria
- Section 9: Locked decisions (NOT negotiable) and adjustable decisions

The summary:

### Phase 1: Offline Trail (what you're building NOW)

**Goal:** Every error produces a lineage trail + compiled snippet in offline mode.

Sub-tasks in order:

1. **Models** (`models.py`):
   - Add `CompiledSnippet` dataclass (lines, error_line, position, caret_char)
   - Add `LineageStep` dataclass (node_id, node_type, short_name, file_path, depth,
     manifest_status, manifest_detail, live_status, live_detail, status_emoji property)
   - Add `DisconnectVerdict` dataclass (between_nodes, explanation, fix)
   - Add fields to `DiagnosticFinding`: `compiled_snippet`, `lineage_trail`,
     `disconnect_verdict`

2. **Snippet extractor** (`tracers/snippet.py`):
   - `extract_snippet(compiled_code, line_number, context_before=1, context_after=1)`
   - Returns `CompiledSnippet` with the error line marked
   - Handle edge cases: line at start/end of file, position-based caret

3. **DAG walker extensions** (`tracers/dag_walker.py`):
   - `trace_column_lineage(unique_id, column_name, max_depth=5)` -> `list[dict]`
     Records status at EVERY node visited (not just first match)
   - `trace_object_lineage(unique_id, object_name)` -> `list[dict]`
     For object-not-found: checks manifest sources for matching relation_name

4. **Classifier updates** (each classifier populates trail + snippet):
   - `runtime_error.py`: populate for object-not-found, invalid-identifier, privileges
   - `schema_change_error.py`: populate for drift cases
   - `data_error.py`: populate compiled_snippet + basic trail (test -> model -> source)
   - `compilation_error.py`: populate compiled_snippet only (no DAG trail needed)

5. **Template + renderer**:
   - Create `templates/findings/lineage_trace.j2`
   - Update each error template to include the lineage trace partial
   - Update `renderer.py` to pass emoji helpers and new fields
   - Update `colors.py` with emoji rendering helpers

6. **Integration tests** (`tests/test_lineage_trail.py`, `tests/test_snippet.py`):
   - Every fixture produces a report with populated lineage_trail
   - Snippet tests: various line numbers, edge cases
   - Verify emoji rendering with color enabled/disabled

### Phase 2: Live Enrichment (AFTER Phase 1 is complete)

- DESCRIBE TABLE on each trail node with a relation_name
- Flip --live to default, add --no-live
- SHOW GRANTS TO ROLE for privilege errors
- Cross-reference run_results for cascade detection

### Phase 3: Deep Expression Tracing (AFTER Phase 2)

- sqlglot-powered expression tracing for data errors
- Syntax error caret rendering
- LATERAL FLATTEN alias recognition

---

## Locked Decisions (do NOT change these)

From LINEAGE_TRAIL_PLAN.md section 9:

- Emojis when color enabled, text fallback `[PASS]`/`[FAIL]`/`[WARN]`/`[????]` when not
- Live by default (Phase 2), `--no-live` to opt out
- Trail ALWAYS shown (not gated by `--verbose`)
- Compiled snippet ALWAYS shown
- Disconnect verdict ALWAYS at the bottom of the trail
- DESCRIBE TABLE is the live verification method (not INFORMATION_SCHEMA)
- SHOW GRANTS TO ROLE for privilege checking (not SHOW GRANTS ON TABLE)
- BFS traversal order (closest upstream first)

---

## Adjustable Decisions (implementor's discretion)

- Exact wording of verdict text (keep it concise and actionable)
- Number of context lines in default vs verbose (proposal: 3 vs 7)
- Whether to show the full trail even when it's just 1 hop (yes -- consistency)
- Template formatting details (box-drawing chars vs dots for separators)
- How to handle fixtures 10/11 which are identical to fixture 4

---

## Execution Protocol

For EACH sub-task within a phase:

1. **Run session-open verification** (fork detection + test baseline)
2. **Read the relevant source files** that will be modified
3. **Read LINEAGE_TRAIL_PLAN.md section 3** for the output target of the fixture
   you're implementing
4. **Implement the change** -- minimal, focused. No refactoring unrelated code.
5. **Write tests** using real fixtures where applicable, synthetic where needed.
6. **Run tests** -- `pytest dbt_diagnostics/tests/ -v` (CHECKPOINT)
7. **Confirm zero regressions** in the full suite.
8. **Move to the next sub-task.**

If a change introduces a regression, fix it immediately before moving on.

After completing ALL sub-tasks in a phase, run every fixture through the CLI:
```bash
for f in dbt_diagnostics/fixtures/real_*[^_]*.json; do
  [[ "$f" == *_manifest.json ]] && continue
  manifest="${f%.json}_manifest.json"
  echo "=== $(basename $f .json) ==="
  dbt-diagnostics --project-dir artwork_pipeline \
    --run-results "$f" --manifest "$manifest" \
    --no-fail --no-color 2>&1
  echo
done
```

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
- Emojis are UTF-8 literals in Python source, not escape sequences.
- Templates use Jinja2 filters for color/emoji (registered in renderer.py).

---

## Success Criteria

### Phase 1 (offline trail):
- All 202 existing tests still passing
- Minimum 15 new tests (snippet extraction + trail generation + rendering)
- All 12 fixtures produce a report with `lineage_trail` populated
- CLI output includes compiled snippet + lineage trail + verdict for each error
- `--no-color` renders text markers instead of emojis
- `--verbose` shows more context lines + full column lists per trail node
- Total test runtime < 8 seconds

### Phase 2 (live enrichment):
- Live mode is default; `--no-live` suppresses it
- Each trail node's live_status populated via DESCRIBE TABLE
- Privilege errors show grant check results
- Graceful fallback when connection unavailable (with warning)

### Phase 3 (expression tracing):
- Data error fixtures show the specific cast/division expression
- Syntax error fixture shows caret at exact position
- LATERAL FLATTEN aliases recognized

---

## Key Commands

```bash
# Install
pip install -e "dbt_diagnostics[live,dev]"

# Run all tests
pytest dbt_diagnostics/tests/ -v

# Run single fixture through CLI
dbt-diagnostics --project-dir artwork_pipeline \
  --run-results dbt_diagnostics/fixtures/real_schema_change_missing_column.json \
  --manifest dbt_diagnostics/fixtures/real_schema_change_missing_column_manifest.json \
  --no-fail --verbose

# Run all 12 fixtures
for f in dbt_diagnostics/fixtures/real_*[^_]*.json; do
  [[ "$f" == *_manifest.json ]] && continue
  manifest="${f%.json}_manifest.json"
  echo "=== $(basename $f .json) ==="
  dbt-diagnostics --project-dir artwork_pipeline \
    --run-results "$f" --manifest "$manifest" --no-fail --no-color
  echo
done
```

---

## Account Context (reference only -- no SQL execution needed for Phase 1)

- Account: OBANOYY-MK07348 (locator EP21559, AWS US-EAST-2)
- Admin: PORCHFLAKE / ACCOUNTADMIN
- dbt role: ARTWORK_TRANSFORMER (key-pair auth via ARTWORK_TRANSFORMER_SVC)
- Database: ARTWORK_DB with BRONZE/SILVER/GOLD schemas
- Branch: donkey-kong-sandbox

---

## Before Proposing Your First Action

1. Confirm you read `dbt_diagnostics/LINEAGE_TRAIL_PLAN.md` (section 3 output targets especially)
2. Run the session-open verification sequence (fork detection)
3. Run `pytest dbt_diagnostics/tests/ -v` and confirm passing count
4. State which phase you're implementing
5. State your approach for the first sub-task (models.py changes)
6. Wait for explicit approval before writing any code
