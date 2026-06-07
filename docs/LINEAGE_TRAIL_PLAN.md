# Lineage Trail Enhancement Plan

> **Status:** APPROVED (owner sign-off 2026-06-06)
> **Branch:** `donkey-kong-sandbox`
> **Package:** `dbt_diagnostics/`
> **Predecessor:** Work Items 1-4 (all complete, 202 tests passing)

---

## 1. Problem Statement

After a dbt build failure, the user currently gets a single-hop diagnosis: "column
X is missing" or "object Y doesn't exist." To understand WHY, they still need to:

1. Open the compiled SQL file and find the offending line
2. Manually trace upstream through the DAG (which model produces this column?)
3. Run DESCRIBE TABLE to see what actually exists at runtime
4. Compare manifest declarations against live schema
5. Check grants if it's a permissions issue

This is exactly the trivial-but-tedious work the tool should automate. The user
wants to see a **visual breadcrumb trail** -- a linear progression from the failing
model upstream through every DAG node -- showing at each step whether the
column/object is present or absent, until the disconnect is found.

---

## 2. Design Principles

1. **Show the journey, not just the destination.** The trail reveals the full
   path so the user can follow the logic without opening files.
2. **Live by default.** DESCRIBE TABLE is free (cloud services layer, no warehouse
   needed). Default to live enrichment; `--no-live` opts out.
3. **Emojis when color is enabled.** Use Unicode status indicators (red X, green
   check, yellow circle, question mark) in color mode; fall back to `[FAIL]`,
   `[PASS]`, `[WARN]`, `[????]` in `--no-color` mode.
4. **Always show compiled SQL context.** The snippet around the error line is
   included by default (3 lines in default mode, 7 in verbose).
5. **Verdict line.** Every trail ends with a plain-English conclusion naming
   the exact disconnect point.
6. **Adapt per error class.** The trail traces different things depending on the
   error type (column existence, object existence, value lineage, grant chain).

---

## 3. Output Targets (the destinations we're building toward)

Each target below is the EXACT terminal output the tool should produce for that
fixture. These are the acceptance criteria -- the implementation is correct when
running the fixture produces output matching this structure.

### 3.1 Object Not Found (002003) -- `real_object_not_exist_002003`

```
======================================================================
  [X] ERROR: stg_met__artworks
  Class: runtime_error (object_not_found)
======================================================================

  COMPILED SQL (line 21):
  | 20:         object_id, raw_payload, _extracted_at,
  | 21: >>>     FROM ARTWORK_DB.BRONZE.DOES_NOT_EXIST_TABLE
  | 22:

  LINEAGE TRACE: ARTWORK_DB.BRONZE.DOES_NOT_EXIST_TABLE
  ........................................................

  [X] ARTWORK_DB.BRONZE.DOES_NOT_EXIST_TABLE
     Manifest: not declared as source or ref
     Live: does NOT exist

  [Y] Nearest source in manifest:
     ARTWORK_DB.BRONZE.RAW_MET_OBJECTS
     Live: EXISTS [check]

  ........................................................
  VERDICT: SQL references a nonexistent table. This is not in
  the manifest -- likely a typo or the DDL was never applied.

  FIX:
    Did you mean ARTWORK_DB.BRONZE.RAW_MET_OBJECTS?
    Or: apply DDL to create DOES_NOT_EXIST_TABLE.
```

NOTE: `[X]` = red X emoji, `[Y]` = yellow circle emoji, `[check]` = green
checkmark emoji. Actual output uses Unicode: U+274C, U+1F7E1, U+2705.

### 3.2 Invalid Identifier / No Drift (000904) -- `real_invalid_identifier_000904`

```
======================================================================
  [X] ERROR: stg_met__artworks
  Class: runtime_error (invalid_identifier)
======================================================================

  COMPILED SQL (line 38):
  | 37:         raw_payload:department::STRING AS department,
  | 38: >>>     NONEXISTENT_TOP_LEVEL_COLUMN,
  | 39:         raw_payload:objectDate::STRING AS object_date,

  LINEAGE TRACE: NONEXISTENT_TOP_LEVEL_COLUMN
  ........................................................

  [X] stg_met__artworks (this model, line 38)
     References NONEXISTENT_TOP_LEVEL_COLUMN as bare column
     Not an alias, not from RAW_PAYLOAD path expression

  [X] raw_met_objects (source)
     ARTWORK_DB.BRONZE.RAW_MET_OBJECTS
     Manifest columns: OBJECT_ID, RAW_PAYLOAD, _EXTRACTED_AT, ...
     Column NOT in manifest or live table

  ........................................................
  VERDICT: This column does not exist anywhere in the lineage.
  Likely a typo or leftover from a removed column.

  FIX:
    Remove or correct NONEXISTENT_TOP_LEVEL_COLUMN in your SQL.
    Available columns in source: OBJECT_ID, RAW_PAYLOAD,
    _EXTRACTED_AT, _SOURCE_SYSTEM, _BATCH_ID
```

### 3.3 Invalid Identifier / Lateral Flatten (000904) -- `real_invalid_identifier_lateral_000904`

```
======================================================================
  [X] ERROR: stg_met__artists
  Class: runtime_error (invalid_identifier)
======================================================================

  COMPILED SQL (line 70):
  | 69:
  | 70: >>>     SN.NONEXISTENT_FIELD,
  | 71:         SN.value:artistULAN_URL::STRING AS artist_ulan_url,

  LINEAGE TRACE: SN.NONEXISTENT_FIELD
  ........................................................

  [X] stg_met__artists (this model, line 70)
     References SN.NONEXISTENT_FIELD
     SN is a LATERAL FLATTEN alias -- not a table reference

  [X] raw_met_objects (source)
     The FLATTEN input is raw_payload (VARIANT)
     Field NONEXISTENT_FIELD not in known VARIANT paths

  ........................................................
  VERDICT: SN is a LATERAL FLATTEN alias. The field
  NONEXISTENT_FIELD does not exist in the flattened VARIANT.

  FIX:
    Check the JSON structure of raw_payload to find the
    correct field name. Compare with other SN.value: paths
    in this model (e.g., SN.value:artistULAN_URL).
```

### 3.4 Schema Drift (000904 with manifest evidence) -- `real_schema_change_missing_column`

```
======================================================================
  [X] ERROR: stg_met__artworks
  Class: schema_change_error
======================================================================

  COMPILED SQL (line 35):
  | 34:         -- Primary key (from top-level column, not VARIANT)
  | 35: >>>     object_id,
  | 36:         raw_payload:title::STRING AS title,

  LINEAGE TRACE: OBJECT_ID
  ........................................................

  [X] stg_met__artworks (this model, line 35)
     SELECT object_id -- bare column from CTE "source"
     Runtime: MISSING (Snowflake 000904)

  [check] raw_met_objects (source)
     ARTWORK_DB.BRONZE.RAW_MET_OBJECTS
     Manifest: OBJECT_ID declared (columns dict)
     Live: OBJECT_ID present (NUMBER(38,0))

  ........................................................
  DISCONNECT: Between raw_met_objects [check] and stg_met__artworks [X]
  The source has OBJECT_ID but CTE "source" doesn't pass it through.

  FIX:
    1. Check CTE "source" -- does it SELECT object_id?
    2. If the column was removed from source, run dbt parse
    3. If renamed, update this model's SQL
```

### 3.5 Privileges / Object Not Authorized (002003) -- `real_privileges_003001`

```
======================================================================
  [X] ERROR: stg_met__enrichment_status
  Class: runtime_error (object_not_found_or_unauthorized)
======================================================================

  COMPILED SQL (line 29):
  | 28:     SELECT
  | 29: >>>     FROM ARTWORK_DB.GOLD.MET_ENRICHMENT_CONTROL
  | 30:

  LINEAGE TRACE: ARTWORK_DB.GOLD.MET_ENRICHMENT_CONTROL
  ........................................................

  [?] ARTWORK_DB.GOLD.MET_ENRICHMENT_CONTROL
     Manifest: not declared as source or ref
     Live (table_exists): NO
     Live (SHOW GRANTS TO ROLE ARTWORK_TRANSFORMER):
       No SELECT grant on ARTWORK_DB.GOLD.* found

  ........................................................
  VERDICT: Table does not exist OR role lacks access (Snowflake
  conflates these in error 002003). The table is NOT in the
  manifest, and the executing role has no grants on GOLD schema.

  FIX:
    1. If the table should exist: apply DDL or correct the schema
       (did you mean ARTWORK_DB.BRONZE.MET_ENRICHMENT_CONTROL?)
    2. If it exists but role lacks access:
       GRANT SELECT ON TABLE ... TO ROLE ARTWORK_TRANSFORMER;
```

### 3.6 Division By Zero (100051) -- `real_division_by_zero_100035`

```
======================================================================
  [X] ERROR: not_null_stg_met__images_ordinal_position (test)
  Class: data_error (division_by_zero)
======================================================================

  TEST SQL:
  | select ordinal_position
  | from ARTWORK_DB.SILVER.stg_met__images
  | where ordinal_position is null

  NOTE: The division occurs inside the VIEW, not in the test SQL.

  LINEAGE TRACE: division expression
  ........................................................

  [X] stg_met__images (view, evaluated by test)
     ARTWORK_DB.SILVER.stg_met__images
     View SQL contains division operation(s)
     Runtime: Division by zero (100051)

  [Y] raw_met_objects (source)
     Supplies data via VARIANT that may contain zeros

  ........................................................
  VERDICT: A division in the stg_met__images view hits zero
  divisor at runtime. The test triggers view evaluation.

  FIX:
    Wrap with NULLIF: numerator / NULLIF(divisor, 0)
    Or: IFF(divisor = 0, NULL, numerator / divisor)
```

### 3.7 Numeric Overflow / Cast Failure (100038) -- `real_numeric_overflow_100132`

```
======================================================================
  [X] ERROR: not_null_stg_met__artworks_object_date (test)
  Class: data_error (numeric_overflow)
======================================================================

  TEST SQL:
  | select object_date
  | from ARTWORK_DB.SILVER.stg_met__artworks
  | where object_date is null

  NOTE: The cast error occurs inside the VIEW, not the test.
  Bad value: 'Putti with a Medallion'

  LINEAGE TRACE: object_date cast
  ........................................................

  [X] stg_met__artworks (view, evaluated by test)
     Expression: raw_payload:objectDate::NUMBER (estimated)
     Runtime: 'Putti with a Medallion' can't cast to NUMBER

  [Y] raw_met_objects (source)
     raw_payload:objectDate contains mixed types
     Some records have strings where numbers expected

  ........................................................
  VERDICT: The VARIANT path raw_payload:objectDate contains
  non-numeric strings. The hard cast (::NUMBER) fails on them.

  FIX:
    Use TRY_CAST: TRY_CAST(raw_payload:objectDate AS NUMBER)
    Or TRY_TO_NUMBER(raw_payload:objectDate::STRING)
```

### 3.8 Internal Error (000603) -- `real_string_too_long_100078`

```
======================================================================
  [X] ERROR: not_null_stg_met__artworks_object_date (test)
  Class: runtime_error (internal_error)
======================================================================

  TEST SQL:
  | select object_date
  | from ARTWORK_DB.SILVER.stg_met__artworks
  | where object_date is null

  [!] This is a Snowflake internal error (000603). Limited
  diagnostics available -- the error is inside Snowflake's engine.

  VERDICT: Snowflake hit an internal processing error evaluating
  this view. This may be transient, or may indicate a query that
  exceeds internal limits.

  FIX:
    1. Retry -- internal errors can be transient
    2. If persistent, simplify the view's SQL or file a support case
    3. Reference incident ID: 4727597
```

### 3.9 Syntax Error (001003) -- `real_syntax_error_001003`

```
======================================================================
  [X] ERROR: stg_met__images
  Class: runtime_error (syntax_error)
======================================================================

  COMPILED SQL (line 66):
  | 65:         LATERAL FLATTEN(input => s.api_images:additional_images  f
  |                                                                      ^
  | 66: >>>     ) AS f

  ........................................................
  VERDICT: Stray character 'f' at end of LATERAL FLATTEN input
  expression. Likely an incomplete edit.

  FIX:
    Remove the trailing 'f' on the LATERAL FLATTEN line:
    LATERAL FLATTEN(input => s.api_images:additional_images) AS f
```

No lineage trail needed -- this is a pure syntax issue in the current model.

### 3.10 & 3.11 Compilation ref/source not found

These fixtures produce the same error shape as case 3.4 (schema drift with
OBJECT_ID). Same output as section 3.4.

### 3.12 Contract Violation / Object Not Found (cascade) -- `real_contract_violation_extra_column`

```
======================================================================
  [X] ERROR: dim_artworks
  Class: runtime_error (object_not_found)
======================================================================

  COMPILED SQL (line 53):
  | 52:     -- Join to get artist dimension key
  | 53: >>>     FROM ARTWORK_DB.GOLD.dim_artists
  | 54:     WHERE artist_alpha_sort IS NOT NULL

  LINEAGE TRACE: ARTWORK_DB.GOLD.DIM_ARTISTS
  ........................................................

  [X] dim_artworks (this model, line 53)
     FROM ARTWORK_DB.GOLD.dim_artists
     Runtime: Object does not exist (002003)

  [?] dim_artists (upstream model)
     ARTWORK_DB.GOLD.DIM_ARTISTS
     Manifest: declared (model.my_project.dim_artists)
     This run: model was NOT executed (not in run_results)
     Live: table does NOT exist

  ........................................................
  VERDICT: dim_artists was never materialized. It is declared
  in the manifest but was not part of this dbt run, and the
  table does not exist in Snowflake.

  FIX:
    Run: dbt run -s dim_artists dim_artworks
    (dim_artists must be built before dim_artworks can reference it)
```

---

## 4. Default vs. Verbose Mode

| Section | Default | Verbose adds |
|---|---|---|
| Compiled SQL snippet | Error line +/- 1 (3 lines) | Error line +/- 3 (7 lines) |
| Lineage trail nodes | Emoji + 2-3 line status | + full column list from manifest, + full DESCRIBE output, + compiled_code excerpts per node |
| Verdict | 2-3 line conclusion | + detailed reasoning chain |
| Fix suggestion | 1-3 actionable steps | + alternative approaches |
| Skipped downstream | Count + summary | Full unique_id list |
| Grants info (privileges) | "No grant found" one-liner | Full SHOW GRANTS TO ROLE relevant rows |
| Run context | Not shown | Role, warehouse, run timestamp, dbt version |

---

## 5. Architecture

### 5.1 New Data Structures (`models.py`)

```python
@dataclass
class CompiledSnippet:
    """A few lines of compiled SQL around the error, with a marker."""
    lines: list[str]           # The actual lines of code
    line_numbers: list[int]    # Corresponding line numbers
    error_line: int            # Which line is the error (1-indexed)
    error_position: Optional[int]  # Column position if available (for caret)


@dataclass
class LineageStep:
    """One node in the column/object lineage trail."""
    node_id: str              # "model.my_project.stg_met__artworks"
    node_type: str            # "model", "source", "seed", "test"
    short_name: str           # "stg_met__artworks"
    file_path: Optional[str]  # "staging/met/stg_met__artworks.sql"
    relation_name: Optional[str]  # "ARTWORK_DB.SILVER.STG_MET__ARTWORKS"
    depth: int                # 0 = failing model, 1 = parent, 2 = grandparent...

    # What the manifest says about the target (column or object) at this node
    manifest_status: str      # "declared", "in_compiled_sql", "not_found", "not_checked"
    manifest_detail: Optional[str]  # "OBJECT_ID (INTEGER)" or "not in columns dict"

    # What Snowflake says (populated by enricher; None when offline)
    live_status: Optional[str]     # "present", "absent", None
    live_detail: Optional[str]     # "NUMBER(38,0)" or "table does not exist"

    # Cross-reference with current run_results
    run_status: Optional[str]      # "success", "error", "skipped", "not_in_run", None

    # Descriptive annotation for rendering
    annotation: Optional[str]      # Free-text context line for the template

    @property
    def status_emoji(self) -> str:
        """Compute the display status icon."""
        if self.live_status == "present":
            return "\u2705"       # green checkmark
        elif self.live_status == "absent":
            return "\u274c"       # red X
        elif self.manifest_status == "declared" or self.manifest_status == "in_compiled_sql":
            return "\U0001f7e1"   # yellow circle (unverified)
        elif self.manifest_status == "not_found":
            return "\u274c"       # red X
        else:
            return "\u2753"       # question mark

    @property
    def status_text(self) -> str:
        """Non-emoji fallback for --no-color mode."""
        if self.live_status == "present":
            return "[PASS]"
        elif self.live_status == "absent":
            return "[FAIL]"
        elif self.manifest_status == "declared" or self.manifest_status == "in_compiled_sql":
            return "[WARN]"
        elif self.manifest_status == "not_found":
            return "[FAIL]"
        else:
            return "[????]"


@dataclass
class DisconnectVerdict:
    """The conclusion at the bottom of a lineage trail."""
    between_node_a: str       # The last green/yellow node (upstream)
    between_node_b: str       # The first red node (downstream)
    explanation: str           # Plain-English conclusion
    confidence: str            # "definitive" (live-verified) or "likely" (manifest-only)
```

### 5.2 New Fields on Existing Models

Add to `DiagnosticFinding`:

```python
    compiled_snippet: Optional[CompiledSnippet] = None
    lineage_trail: list[LineageStep] = field(default_factory=list)
    disconnect: Optional[DisconnectVerdict] = None
```

### 5.3 New Tracer Methods (`dag_walker.py`)

```python
def trace_column_lineage(self, unique_id: str, column_name: str,
                         max_depth: int = 5) -> list[LineageStep]:
    """
    Walk upstream from unique_id via BFS, recording at EVERY node
    whether column_name is declared/found/absent. Unlike find_column_origin()
    which returns the first match and stops, this records the full path.

    Returns a list of LineageStep ordered by depth (shallowest first).
    The first entry (depth=0) is always the failing model itself.
    """

def trace_object_lineage(self, unique_id: str, object_fq_name: str,
                         run_results: Optional[dict] = None) -> list[LineageStep]:
    """
    For object-not-found errors: trace whether the target object is a known
    manifest node, whether it ran successfully in this build, and whether
    it exists live.
    """
```

### 5.4 Compiled Snippet Extractor (new utility)

Location: `dbt_diagnostics/tracers/snippet.py`

```python
def extract_snippet(compiled_code: str, error_line: int,
                    context_lines: int = 1,
                    error_position: Optional[int] = None) -> CompiledSnippet:
    """
    Extract a window of compiled SQL around the error line.

    Args:
        compiled_code: The full compiled SQL from run_results.
        error_line: 1-indexed line number from the error message.
        context_lines: How many lines above/below to include (1=default, 3=verbose).
        error_position: Column position for caret rendering (syntax errors).

    Returns a CompiledSnippet with the lines, numbers, and marker position.
    """
```

### 5.5 Enricher Extensions (`enrichers/enrich.py`)

When live mode is active (the new default), the enricher iterates
`finding.lineage_trail` and for each step that has a `relation_name`:

1. `DESCRIBE TABLE <relation_name>` -- check column existence, get types
2. For privilege errors: `SHOW GRANTS TO ROLE <role>` (role from profiles.yml)
3. Cross-reference `run_results` to set `run_status` on each step

Queries used:
- `DESCRIBE TABLE` -- cloud services layer, no warehouse, effectively free
- `SHOW TABLES LIKE '<name>' IN SCHEMA <db>.<schema>` -- same
- `SHOW GRANTS TO ROLE <role>` -- always permitted for your own role, free

### 5.6 Template Changes

New template: `dbt_diagnostics/templates/findings/lineage_trace.j2`

This is a reusable partial included by every error-class template that has a
lineage trail. It renders:
1. The trail header with the traced target name
2. Each LineageStep with emoji/text status + detail lines
3. The DisconnectVerdict at the bottom

Updated templates: every `findings/<error_class>.j2` includes the compiled
snippet section and the lineage trace partial.

### 5.7 CLI Flag Changes (`main.py`)

- Remove `--live` flag
- Add `--no-live` flag (opt out of live enrichment)
- Live enrichment runs by default; graceful fallback if:
  - `snowflake-connector-python` not installed (warn + continue offline)
  - Connection fails (warn + continue offline)
  - `--no-live` is passed (silent offline)

---

## 6. Implementation Phases

### Phase 1: Core Trail Infrastructure

**Goal:** The lineage trail renders for all 12 fixtures in OFFLINE mode
(manifest-only data). Live enrichment not yet wired.

Files to create:
- `dbt_diagnostics/tracers/snippet.py` -- CompiledSnippet extractor

Files to modify:
- `dbt_diagnostics/models.py` -- add CompiledSnippet, LineageStep, DisconnectVerdict, new fields on DiagnosticFinding
- `dbt_diagnostics/tracers/dag_walker.py` -- add trace_column_lineage(), trace_object_lineage()
- `dbt_diagnostics/classifiers/runtime_error.py` -- populate lineage_trail + compiled_snippet
- `dbt_diagnostics/classifiers/schema_change_error.py` -- populate lineage_trail + compiled_snippet
- `dbt_diagnostics/classifiers/data_error.py` -- populate compiled_snippet + basic trail
- `dbt_diagnostics/classifiers/compilation_error.py` -- populate compiled_snippet
- `dbt_diagnostics/classifiers/timeout_error.py` -- no trail (not applicable)
- `dbt_diagnostics/templates/findings/lineage_trace.j2` -- new template
- `dbt_diagnostics/templates/findings/*.j2` -- all error templates updated
- `dbt_diagnostics/templates/report.j2` -- compiled snippet section
- `dbt_diagnostics/renderer.py` -- pass new fields to template context
- `dbt_diagnostics/tests/` -- new tests against all 12 real fixtures

**Acceptance criteria:**
- `dbt-diagnostics --project-dir <your_project> --run-results <fixture> --manifest <manifest> --no-live`
  produces output structurally matching the targets in section 3.
- All existing 202 tests still pass.
- Minimum 15 new tests covering trail generation + snippet extraction.

### Phase 2: Live Enrichment of Trail

**Goal:** With a live connection, DESCRIBE TABLE populates `live_status` on
each trail step. Grants checking for privilege errors. Cross-reference with
run_results for cascade detection.

Files to modify:
- `dbt_diagnostics/enrichers/enrich.py` -- iterate lineage_trail, DESCRIBE each node
- `dbt_diagnostics/enrichers/schema_inspector.py` -- add describe_column() helper
- `dbt_diagnostics/main.py` -- flip --live to default, add --no-live
- `dbt_diagnostics/classifiers/runtime_error.py` -- pass run_results for cross-ref
- New: `dbt_diagnostics/enrichers/grants.py` -- SHOW GRANTS TO ROLE wrapper
- `dbt_diagnostics/templates/findings/lineage_trace.j2` -- show live_detail when available

**Acceptance criteria:**
- Running against a live Snowflake connection shows green/red status based on
  actual DESCRIBE TABLE results.
- `--no-live` suppresses all live queries.
- Graceful fallback when connection unavailable.
- Grant check works for privilege errors (SHOW GRANTS TO ROLE always succeeds
  for the current role).

### Phase 3: Deep Expression Tracing (follow-on)

**Goal:** For data errors (division, overflow, string-too-long), trace through
the compiled SQL with sqlglot to find the exact expression that causes the error.
For syntax errors, render exact caret position. For LATERAL FLATTEN identifiers,
recognize the alias pattern.

Files to modify:
- `dbt_diagnostics/tracers/column_tracer.py` -- add expression_at_line() method
- `dbt_diagnostics/classifiers/data_error.py` -- use sqlglot to trace value lineage
- `dbt_diagnostics/classifiers/runtime_error.py` -- syntax error caret rendering
- `dbt_diagnostics/tracers/snippet.py` -- add caret support

**Acceptance criteria:**
- Data error fixtures show the specific expression (e.g., `::NUMBER` cast)
- Syntax error fixture shows caret at exact position
- LATERAL FLATTEN aliases recognized and explained

---

## 7. Grants: What's Guaranteed vs. What's Not

| Query | Always works? | Requires |
|---|---|---|
| `SHOW GRANTS TO ROLE <current_role>` | YES | Nothing special |
| `SHOW GRANTS TO ROLE <other_role>` | Only if you can USE that role | Role hierarchy |
| `SHOW GRANTS ON TABLE <table>` | Only if you own it or have MANAGE GRANTS | Ownership/privilege |
| `CURRENT_ROLE()` | YES | Nothing |
| `DESCRIBE TABLE <table>` | Only if SELECT/USAGE granted | Table-level privilege |

**Strategy for privilege errors:**
1. Read role from profiles.yml (offline) -- we know what role dbt uses
2. `SHOW GRANTS TO ROLE <that_role>` -- guaranteed if we connect as that role
3. Check if target object's schema/table appears in the grant list
4. If not: report the gap definitively ("role X has no SELECT on Y")

**Edge case:** If profiles.yml role differs from connection role (e.g., session
default vs. explicit USE ROLE), note the assumption in output.

---

## 8. Cost Analysis

| Operation | Frequency per run | Credit cost |
|---|---|---|
| DESCRIBE TABLE | 1-5 per error (trail nodes) | $0 (cloud services) |
| SHOW TABLES IN SCHEMA | 1 per object-not-found | $0 (cloud services) |
| SHOW GRANTS TO ROLE | 1 per privilege error | $0 (cloud services) |
| Total for typical 3-error run | ~10-15 metadata queries | $0.00 |

All metadata operations execute on the cloud services layer without requiring
a running warehouse or consuming warehouse credits. They only count toward the
10% cloud services adjustment threshold, which diagnostic-scale queries will
never approach.

---

## 9. Execution Protocol for Future Windows

Each phase is independently shippable. A new context window should:

1. Read this file first (it's the plan of record)
2. Check `pytest dbt_diagnostics/tests/ -v` to confirm current state (202 passing)
3. Implement ONE phase at a time (don't mix phases)
4. After each classifier change, run the full test suite
5. After completing a phase, run all 12 fixtures through the CLI and compare
   against the output targets in section 3
6. Add tests that assert the structural properties of the output (trail length,
   emoji presence, verdict text pattern)

**Low-level decisions the implementor may adjust:**
- Exact wording of verdict text (keep it concise and actionable)
- Number of context lines in default vs verbose (current proposal: 3 vs 7)
- Whether to show the full trail even when it's just 1 hop (yes -- consistency)
- Template formatting details (box-drawing chars vs dots for separators)
- How to handle fixtures 10/11 which are identical to fixture 4

**Decisions that are LOCKED (do not change):**
- Emojis when color enabled, text fallback when not
- Live by default, --no-live to opt out
- Trail always shown (not gated by --verbose)
- Compiled snippet always shown
- Verdict always at the bottom of the trail
- DESCRIBE TABLE is the live verification method (not INFORMATION_SCHEMA)
- SHOW GRANTS TO ROLE for privilege checking (not SHOW GRANTS ON TABLE)
- BFS traversal order (closest upstream first)

---

## 10. Testing Strategy

### Unit tests (per phase):
- `test_snippet.py` -- extract_snippet with various line numbers, positions, edge cases
- `test_lineage_trail.py` -- trace_column_lineage with synthetic manifests (1-hop, 3-hop, cycle, no-parents)
- `test_lineage_rendering.py` -- template renders correct emoji/text based on status

### Integration tests (all 12 fixtures):
- Each fixture produces a report with `lineage_trail` populated
- Each trail has the expected number of steps
- Each trail's verdict names the correct disconnect point
- Compiled snippet includes the correct error line

### CLI tests:
- `--no-live` suppresses live queries (mock connection not called)
- `--no-color` renders text fallback instead of emoji
- `--verbose` renders more lines in snippet + full column lists

---

## 11. File Inventory (what gets created/modified)

### New files:
- `dbt_diagnostics/tracers/snippet.py`
- `dbt_diagnostics/enrichers/grants.py`
- `dbt_diagnostics/templates/findings/lineage_trace.j2`
- `dbt_diagnostics/tests/test_snippet.py`
- `dbt_diagnostics/tests/test_lineage_trail.py`

### Modified files:
- `dbt_diagnostics/models.py` (3 new dataclasses + 3 new fields)
- `dbt_diagnostics/tracers/dag_walker.py` (2 new methods)
- `dbt_diagnostics/classifiers/runtime_error.py` (populate trail + snippet)
- `dbt_diagnostics/classifiers/schema_change_error.py` (populate trail + snippet)
- `dbt_diagnostics/classifiers/data_error.py` (populate snippet + basic trail)
- `dbt_diagnostics/classifiers/compilation_error.py` (populate snippet)
- `dbt_diagnostics/enrichers/enrich.py` (iterate trail for live enrichment)
- `dbt_diagnostics/enrichers/schema_inspector.py` (describe_column helper)
- `dbt_diagnostics/main.py` (--no-live flag, remove --live)
- `dbt_diagnostics/renderer.py` (pass new fields to template)
- `dbt_diagnostics/templates/report.j2` (compiled snippet inclusion)
- `dbt_diagnostics/templates/findings/runtime_error.j2`
- `dbt_diagnostics/templates/findings/schema_change_error.j2`
- `dbt_diagnostics/templates/findings/data_error.j2`
- `dbt_diagnostics/templates/findings/compilation_error.j2`
- `dbt_diagnostics/colors.py` (emoji helpers)

### Unchanged:
- `dbt_diagnostics/classifiers/timeout_error.py` (no trail applicable)
- `dbt_diagnostics/classifiers/contract_violation.py` (trail added in Phase 3)
- `dbt_diagnostics/linters/` (not affected)
- All existing test files (must continue passing)
