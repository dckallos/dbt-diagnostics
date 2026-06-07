# HANDOFF PROMPT 2: Template Layer + Live Enrichment

> **Role:** You are a Principal Engineer implementing the template/rendering
> layer and live enrichment wiring for `dbt_diagnostics`. Code standards are
> rigorous: every template is testable, every branch is covered, every string
> literal matches the acceptance targets in `LINEAGE_TRAIL_PLAN.md` section 3.
> You write production-quality Python with type annotations, docstrings on public
> functions, and no dead code.
>
> **Context:** The Lineage Trail feature (Phase 1 sub-tasks 1-4) is COMPLETE.
> All 4 classifiers now populate `compiled_snippet` and `lineage_trail` on their
> DiagnosticFinding objects. 231 tests pass. What remains is rendering the trail
> to terminal output (Phase 1 sub-tasks 5-6), then wiring live Snowflake
> enrichment (Phase 2).
>
> **Branch:** `donkey-kong-sandbox`
> **Package:** `dbt_diagnostics/`
> **Plan of record:** `dbt_diagnostics/LINEAGE_TRAIL_PLAN.md` (read sections 3, 5.6, 5.7, 6 for full spec)
> **Test baseline:** 231 tests passing (`pytest dbt_diagnostics/tests/ -v`)

---

## VERIFICATION STEP (do this first)

```bash
pytest dbt_diagnostics/tests/ --co -q 2>&1 | tail -3
# Expected: 231 tests collected

grep -c "compiled_snippet" dbt_diagnostics/classifiers/runtime_error.py
# Expected: >= 2

grep -c "lineage_trail" dbt_diagnostics/classifiers/schema_change_error.py
# Expected: >= 2

grep -c "_build_basic_trail" dbt_diagnostics/classifiers/data_error.py
# Expected: >= 2
```

If any check fails, stop and ask. The prior sub-tasks may need recovery.

---

## PHASE 1, SUB-TASK 5: Template + Renderer Layer

### 5a. Create `dbt_diagnostics/templates/findings/lineage_trace.j2`

This is a **reusable Jinja2 partial** included by each error-class template.
It renders the lineage trail as a vertical breadcrumb. Study the output targets
in `LINEAGE_TRAIL_PLAN.md` section 3 -- the template must produce output that
structurally matches those examples.

The template receives these variables in its context:
- `finding.compiled_snippet` -- a `CompiledSnippet` (or None)
- `finding.lineage_trail` -- a `list[LineageStep]` (may be empty)
- `finding.disconnect` -- a `DisconnectVerdict` (or None)
- `verbose` -- bool (controls snippet context width)
- `color_enabled` -- bool (the Jinja filters handle ANSI; emojis are unconditional
  when color enabled, text fallback when not)

**Compiled snippet section structure:**

```
  COMPILED SQL (line {{ snippet.error_line }}):
{% for i in range(snippet.lines | length) %}
  | {{ snippet.line_numbers[i] }}:{% if snippet.line_numbers[i] == snippet.error_line %} >>> {% else %}     {% endif %}{{ snippet.lines[i] }}
{% endfor %}
{% if snippet.error_position %}
  |        {{ " " * (snippet.error_position - 1) }}^
{% endif %}
```

**Lineage trail section structure:**

```
  LINEAGE TRACE: {{ trace_target }}
  ........................................................

{% for step in finding.lineage_trail %}
  {{ step.status_emoji if color_enabled else step.status_text }} {{ step.short_name }}
{% if step.file_path %}
     File: {{ step.file_path }}
{% endif %}
{% if step.manifest_status and step.manifest_status != "not_checked" %}
     Manifest: {{ step.manifest_detail }}
{% endif %}
{% if step.live_status %}
     Live: {{ step.live_detail }}
{% endif %}
{% if step.run_status %}
     Run: {{ step.run_status }}
{% endif %}
{% if step.annotation %}
     ({{ step.annotation }})
{% endif %}

{% endfor %}
  ........................................................
{% if finding.disconnect %}
  VERDICT: {{ finding.disconnect.explanation }}
{% endif %}
```

**Important rendering rules:**

1. Status emoji uses `step.status_emoji` property (already on LineageStep).
   When `color_enabled=False`, use `step.status_text` instead.
2. The `trace_target` is derived from context: for column lineage it's the
   column name; for object lineage it's the FQ object name. Pass it as a
   template variable from the parent template.
3. The dotted line separator is exactly 56 dots.
4. Indentation: 2 spaces for the section, 5 spaces for detail lines under a step.

### 5b. Update `dbt_diagnostics/colors.py`

Add a helper for emoji/text status rendering that templates can call:

```python
def status_indicator(emoji: str, text: str, *, color_enabled: bool = True) -> str:
    """Return emoji when color enabled, bracketed text when not."""
    return emoji if color_enabled else text
```

Register it as a Jinja filter in `renderer.py`.

### 5c. Update `dbt_diagnostics/renderer.py`

1. Import `status_indicator` from colors.
2. Register new Jinja filters:
   - `status_indicator` filter
   - A `color_enabled` global so templates can branch on it
3. Pass `finding.compiled_snippet`, `finding.lineage_trail`, and
   `finding.disconnect` to the template context. Currently `render_text()`
   passes reports as-is to the template -- verify that the template has access
   to these new dataclass fields via the report's findings list.

**Critical detail:** The report template iterates `report.findings` and includes
the per-error-class template for each finding. Each per-error-class template then
`{% include "findings/lineage_trace.j2" %}` to render the trail. You need to
ensure `color_enabled` is available as a template global (not just a filter
argument).

### 5d. Update each error-class template to include the lineage trace

Files to modify:
- `dbt_diagnostics/templates/findings/runtime_error.j2`
- `dbt_diagnostics/templates/findings/schema_change_error.j2`
- `dbt_diagnostics/templates/findings/data_error.j2`
- `dbt_diagnostics/templates/findings/compilation_error.j2`

Each template should include the trace partial AFTER the root-cause block and
BEFORE the fix suggestion. The pattern:

```jinja2
{# ... existing root cause section ... #}

{% if finding.compiled_snippet or finding.lineage_trail %}
{% include "findings/lineage_trace.j2" %}
{% endif %}

{# ... existing fix suggestion section ... #}
```

For `runtime_error.j2`, the trace_target depends on the sub-class:
- `invalid_identifier`: the column name (from `finding.target_identifier`)
- `object_not_found`: the FQ object name (from `finding.target_identifier`)
- `privilege_error`: the FQ object name (from `finding.target_identifier`)
- `syntax_error`: "SQL syntax" (static string)

For `schema_change_error.j2`: trace_target = column name (`finding.target_identifier`)
For `data_error.j2`: trace_target = "data flow" (these trace values, not columns)
For `compilation_error.j2`: no trail (snippet only, if available)

### 5e. Update `dbt_diagnostics/templates/report.j2`

Ensure the report template passes `color_enabled` and `verbose` down to the
included finding templates. Check if it already does -- if so, no change needed.
If not, add:

```jinja2
{% set color_enabled = color_enabled | default(false) %}
```

---

## PHASE 1, SUB-TASK 6: Integration Tests

### Create `dbt_diagnostics/tests/test_lineage_integration.py`

This file tests end-to-end: fixture in -> rendered output out. Structure:

```python
"""
Integration tests: verify that each real fixture produces a report
with correctly populated lineage trail and rendered output matching
the structural targets in LINEAGE_TRAIL_PLAN.md section 3.
"""
import json
from pathlib import Path

import pytest

from dbt_diagnostics.classifiers.base import DiagnosticContext
from dbt_diagnostics.classifiers import classify_error
from dbt_diagnostics.tracers.dag_walker import DagWalker
from dbt_diagnostics.tracers.column_tracer import ColumnTracer
from dbt_diagnostics.renderer import render_text
from dbt_diagnostics.models import DiagnosticReport

FIXTURES = Path(__file__).parent.parent / "fixtures"
```

**Tests to include (one per fixture that has a trail):**

1. `test_object_not_exist_trail_structure` -- fixture `real_object_not_exist_002003`
   - Assert: trail length == 2 (failing model + missing object)
   - Assert: trail[1].manifest_status == "missing"
   - Assert: rendered output contains "LINEAGE TRACE:"
   - Assert: rendered output contains "COMPILED SQL (line"

2. `test_invalid_identifier_trail_structure` -- fixture `real_invalid_identifier_000904`
   - Assert: trail length >= 2
   - Assert: finding.compiled_snippet is not None
   - Assert: finding.compiled_snippet.error_line == 38
   - Assert: rendered output contains "NONEXISTENT_TOP_LEVEL_COLUMN"

3. `test_schema_drift_trail_structure` -- uses SchemaChangeErrorClassifier delegation
   - Assert: trail[1].manifest_status == "declared"
   - Assert: rendered output contains "VERDICT:" or disconnect is populated

4. `test_division_by_zero_basic_trail` -- fixture `real_division_by_zero_100035`
   - Assert: trail has failing model + at least 1 source
   - Assert: finding.compiled_snippet is None (no error line in test failures)

5. `test_no_color_uses_text_status` -- render with `color_enabled=False`
   - Assert: output contains "[PASS]" or "[FAIL]" or "[????]"
   - Assert: output does NOT contain Unicode emoji chars

6. `test_color_uses_emoji_status` -- render with `color_enabled=True`
   - Assert: output contains one of: \u2705, \u274c, \u2753

7. `test_all_fixtures_no_crash` -- parameterize over every real fixture pair
   - For each: classify -> render -> assert no exception
   - Assert: every report has at least 1 finding

8. `test_verbose_shows_more_context` -- render same fixture twice (verbose vs not)
   - Assert: verbose output length > non-verbose output length

**Test helpers:**

```python
def _make_context(manifest: dict, run_results: dict = None) -> DiagnosticContext:
    walker = DagWalker(manifest)
    tracer = ColumnTracer(models_dir=Path("."), compiled_dir=Path("."))
    return DiagnosticContext(
        dag_walker=walker,
        column_tracer=tracer,
        models_dir=Path("."),
        compiled_dir=Path("."),
        manifest=manifest,
        run_results=run_results,
    )

def _load_fixture(name: str) -> tuple[dict, dict]:
    """Load run_results + manifest for a named fixture."""
    rr = json.loads((FIXTURES / f"{name}.json").read_text())
    manifest = json.loads((FIXTURES / f"{name}_manifest.json").read_text())
    return rr, manifest
```

---

## PHASE 2: Live Enrichment (if time permits after Phase 1 sub-tasks 5+6)

### 2a. Add `--no-live` flag to `main.py`

Current state: `main.py` has a `--live` flag that opts INTO live enrichment.
Change:
- Remove `--live` flag
- Add `--no-live` flag (default: live enrichment is ON)
- Graceful fallback: if `snowflake-connector-python` is not installed or
  connection fails, print a warning and continue in offline mode

```python
parser.add_argument(
    "--no-live",
    action="store_true",
    help="Skip live Snowflake queries (manifest-only diagnosis)",
)
```

Update the `run()` function logic:
```python
# Old: if args.live: do_enrichment()
# New: if not args.no_live: try_enrichment_or_fallback()
```

### 2b. Update `dbt_diagnostics/enrichers/enrich.py`

Add a new function that iterates `finding.lineage_trail` and enriches each step:

```python
def enrich_lineage_trail(finding: DiagnosticFinding, conn) -> None:
    """
    For each LineageStep that has a relation_name, run DESCRIBE TABLE
    to populate live_status and live_detail.
    """
    for step in finding.lineage_trail:
        if not step.relation_name:
            continue
        exists = table_exists(conn, step.relation_name)
        step.live_status = "exists" if exists else "missing"
        if exists and finding.target_identifier:
            # For column-lineage: check if the specific column exists
            cols = describe_table(conn, step.relation_name)
            col_names = [c.name.upper() for c in cols]
            if finding.target_identifier.upper() in col_names:
                step.live_detail = f"column '{finding.target_identifier}' found"
            else:
                step.live_detail = f"column '{finding.target_identifier}' NOT found"
        elif exists:
            step.live_detail = "table exists"
        else:
            step.live_detail = "table does NOT exist in Snowflake"
```

Call this from the existing enrichment orchestration in `enrich_report()`.

### 2c. Create `dbt_diagnostics/enrichers/grants.py`

For privilege errors only. Structure:

```python
"""
dbt_diagnostics/enrichers/grants.py

SHOW GRANTS TO ROLE wrapper for privilege-error diagnosis.
"""
from typing import Optional


def check_role_grants(conn, role_name: str, target_object: str) -> dict:
    """
    Check if the given role has SELECT/USAGE on the target object.

    Uses: SHOW GRANTS TO ROLE <role_name>
    This always succeeds for the current session role (no special privileges needed).

    Returns:
        {
            "has_access": bool,
            "grants_found": list[str],  # e.g. ["SELECT on TABLE DB.SCHEMA.TBL"]
            "role_checked": str,
        }
    """
    ...
```

### 2d. Wire `DisconnectVerdict` population

After live enrichment populates `live_status` on trail steps, scan the trail
to find the disconnect point and set `finding.disconnect`:

```python
def identify_disconnect(finding: DiagnosticFinding) -> None:
    """
    Scan the lineage trail for the point where status flips from
    'exists' to 'missing' (or 'declared' to 'not_found'). Set the
    DisconnectVerdict accordingly.
    """
    trail = finding.lineage_trail
    if len(trail) < 2:
        return

    for i in range(len(trail) - 1):
        current = trail[i]
        next_step = trail[i + 1]
        # The disconnect is between a passing node and a failing one
        if _is_passing(current) and _is_failing(next_step):
            finding.disconnect = DisconnectVerdict(
                between_node_a=current.node_id,
                between_node_b=next_step.node_id,
                explanation=_build_verdict_text(current, next_step, finding),
                confidence="high" if next_step.live_status else "medium",
            )
            return

    # If no clear disconnect found but there are failures:
    failing_steps = [s for s in trail if _is_failing(s)]
    if failing_steps:
        last_fail = failing_steps[-1]
        finding.disconnect = DisconnectVerdict(
            between_node_a=trail[0].node_id,
            between_node_b=last_fail.node_id,
            explanation=f"'{last_fail.short_name}' is the furthest upstream failure.",
            confidence="low",
        )
```

---

## ACCEPTANCE CRITERIA

### Phase 1 complete when:
- [ ] `pytest dbt_diagnostics/tests/ -v` shows 250+ tests passing (231 existing + 19+ new integration tests)
- [ ] Running any fixture through the classifier + renderer produces output containing:
  - "COMPILED SQL (line N):" section (when snippet exists)
  - "LINEAGE TRACE:" section (when trail is non-empty)
  - Correct emoji/text status per step
- [ ] `--no-color` mode produces `[PASS]`/`[FAIL]`/`[????]` instead of emoji

### Phase 2 complete when:
- [ ] `--no-live` flag suppresses all Snowflake queries
- [ ] Default mode (no flag) attempts live enrichment
- [ ] Live enrichment populates `live_status` on trail steps
- [ ] DESCRIBE TABLE failures are graceful (warn + continue offline)
- [ ] Privilege errors show grant-check results
- [ ] `DisconnectVerdict` is populated with correct between-nodes
- [ ] "VERDICT:" line appears in rendered output naming the disconnect

---

## CODE STANDARDS (non-negotiable)

1. **Type annotations on all function signatures.** No `Any` unless unavoidable.
2. **Docstrings on all public functions.** One-liner minimum; multi-line for
   anything non-obvious.
3. **No dead code.** If you remove a feature path, remove all traces.
4. **No bare `except`.** Always catch specific exceptions.
5. **Template indentation matters.** The output targets in section 3 of the plan
   define exact indentation. Match them.
6. **Test isolation.** Integration tests must not require a live Snowflake
   connection. Mock or patch any connector calls.
7. **Backward compatibility.** All 231 existing tests must continue passing
   without modification. If a template change alters test fixtures' expected
   output, update the test expectations -- but verify the new output is correct.
8. **Import order:** stdlib, third-party, local. No wildcard imports.
9. **Line length:** 99 chars max (consistent with existing codebase).
10. **Commit granularity:** One logical commit per sub-task (5a, 5b+5c, 5d+5e, 6).

---

## FILE REFERENCE (current state as of handoff)

| File | Lines | State |
|---|---|---|
| `models.py` | ~305 | DONE: CompiledSnippet, LineageStep, DisconnectVerdict, new fields on DiagnosticFinding |
| `tracers/snippet.py` | 63 | DONE: extract_snippet() |
| `tracers/dag_walker.py` | ~230 | DONE: trace_column_lineage(), trace_object_lineage() |
| `classifiers/runtime_error.py` | ~250 | DONE: populates compiled_snippet + lineage_trail |
| `classifiers/schema_change_error.py` | 155 | DONE: populates compiled_snippet + lineage_trail |
| `classifiers/data_error.py` | 201 | DONE: populates compiled_snippet + basic trail |
| `classifiers/compilation_error.py` | 189 | DONE: populates compiled_snippet (no trail for Jinja errors) |
| `renderer.py` | 114 | NEEDS UPDATE: pass new fields + color_enabled global |
| `colors.py` | 88 | NEEDS UPDATE: add status_indicator helper |
| `main.py` | 535 | NEEDS UPDATE: --no-live flag (Phase 2) |
| `enrichers/enrich.py` | ~120 | NEEDS UPDATE: iterate lineage_trail for live enrichment (Phase 2) |
| `enrichers/grants.py` | -- | NEEDS CREATION (Phase 2) |
| `templates/findings/lineage_trace.j2` | -- | NEEDS CREATION |
| `templates/findings/runtime_error.j2` | ~60 | NEEDS UPDATE: include lineage_trace partial |
| `templates/findings/schema_change_error.j2` | exists | NEEDS UPDATE: include lineage_trace partial |
| `templates/findings/data_error.j2` | exists | NEEDS UPDATE: include lineage_trace partial |
| `templates/findings/compilation_error.j2` | exists | NEEDS UPDATE: include lineage_trace partial |
| `tests/test_lineage_trail.py` | 470 | DONE (19 tests for trace methods) |
| `tests/test_snippet.py` | ~100 | DONE (10 tests for snippet extraction) |
| `tests/test_lineage_integration.py` | -- | NEEDS CREATION |

---

## EXECUTION ORDER

1. Read `LINEAGE_TRAIL_PLAN.md` section 3 (output targets) -- this is your acceptance spec
2. Run `pytest dbt_diagnostics/tests/ -v` to confirm 231 pass
3. Implement sub-task 5a (create `lineage_trace.j2`)
4. Implement sub-task 5b+5c (colors.py + renderer.py updates)
5. Implement sub-task 5d+5e (update all error templates + report.j2)
6. Run `pytest` -- expect 231 still passing (templates are additive)
7. Implement sub-task 6 (integration tests) -- target 250+ tests
8. Run full suite, fix any failures
9. If all green: proceed to Phase 2 (2a -> 2b -> 2c -> 2d)
10. After Phase 2: run full suite again, target 260+ tests

---

## KEY DATACLASS SHAPES (for template reference)

```python
@dataclass
class CompiledSnippet:
    lines: list[str]           # The actual SQL lines in the window
    line_numbers: list[int]    # 1-based line numbers for each line
    error_line: int            # The 1-based line number with the error
    error_position: Optional[int] = None  # 1-based column position

@dataclass
class LineageStep:
    node_id: str               # e.g. "model.artwork_pipeline.stg_met__artworks"
    node_type: str             # "model", "source", "test", "seed"
    short_name: str            # e.g. "stg_met__artworks"
    file_path: Optional[str] = None
    relation_name: Optional[str] = None  # e.g. "ARTWORK_DB.BRONZE.RAW_MET_OBJECTS"
    depth: int = 0
    manifest_status: Optional[str] = None  # "declared", "not_found", "missing", "not_checked"
    manifest_detail: Optional[str] = None
    live_status: Optional[str] = None      # "exists", "missing" (populated by Phase 2)
    live_detail: Optional[str] = None
    run_status: Optional[str] = None       # "pass", "error", "skipped"
    annotation: Optional[str] = None

    @property
    def status_emoji(self) -> str: ...     # Returns Unicode emoji based on status
    @property
    def status_text(self) -> str: ...      # Returns "[PASS]", "[FAIL]", "[SKIP]", "[????]"

@dataclass
class DisconnectVerdict:
    between_node_a: str        # The last "good" node
    between_node_b: str        # The first "bad" node
    explanation: str           # Plain-English verdict
    confidence: str            # "high", "medium", "low"
```
