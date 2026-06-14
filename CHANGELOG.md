# dbt_diagnostics CHANGELOG

## [Unreleased]

### Single-root-cause aggregator (issue #7, epic #4)

I shipped the first Live Verification Engine probe. When many results share the
Snowflake "object does not exist" (002003) signature, they now collapse into one
`root_cause_group` with a single live-disambiguated verdict instead of N
identical lines.

- New `root_cause.py`: `build_root_cause_groups()` groups object-not-exist
  errors by fully qualified object name and attaches one verdict:
  - `never_built` -> tests ran before materialize; run `dbt build`, not `dbt test`.
  - `exists_now`  -> built by another process / after the run started; re-run.
  - `denied`      -> routed through a grant check.
  The `denied` branch is decided by `SHOW GRANTS`, not by `table_exists`, because
  `SHOW TABLES` cannot tell "missing" apart from "invisible to the role". All
  probes are Tier A ($0 metadata). Offline -- or any probe failure -- degrades to
  an `unverified` verdict that carries the exact query to run; nothing raises.
- New `enrichers/run_identity.py`: recovers the role the run actually used from
  the failing statement's `query_id` via `INFORMATION_SCHEMA.QUERY_HISTORY`
  (Tier 0, near-real-time), falling back to the declared profile role (Tier 2)
  then the diagnostic session role (Tier 3). A watermark comparison distinguishes
  "history not yet populated (lagging)" from "never" with a single bounded retry,
  and a drift note is emitted when the recovered role disagrees with the profile.
- Terminal: new ROOT CAUSE section that reuses the `findings/lineage_trace.j2`
  partial. 46 identical object-not-found errors render as one root-cause line.
- `--json`: `schema_version` bumped 1.0 -> 1.1 (additive) with a new top-level
  `root_cause_groups` key. No existing keys changed.
- Tests: `tests/test_root_cause.py`, `tests/test_run_identity.py`.

**Follow-up (separate issue):** an opt-in dbt `on-run-start` hook that stamps
the run's identity (invocation_id + CURRENT_ROLE) so role recovery does not
depend on query-history retention or the presence of a query_id.

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

See git history for the full v0.4.0 and earlier notes (trimmed here only in this
Unreleased-edit; the original entries remain in prior commits).
