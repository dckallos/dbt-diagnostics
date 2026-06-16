# dbt_diagnostics CHANGELOG

## [Unreleased]

### Removed the pre-execution linter (scope guard, issue #25)

I removed the `dbt_diagnostics/linters/` package and the `lint` subcommand. The
tool's purpose is live, database-grounded root-cause analysis, not static
linting, and the linter checks duplicated enforcement that dbt's own contract
layer (and sqlfluff/dbt_project_evaluator) already provide. Keeping them was a
standing scope-guard violation documented in `AGENTS.md`.

- Deleted the `linters/` package, the `lint` CLI subcommand and its dispatch in
  `main.py`, the `LintFinding` model, `render_lint` in `renderer.py`, the
  `lint_report.j2` template, and `tests/test_linters.py`.
- No change to the diagnose `--json` output shape; `schema_version` is
  unchanged. The lint path had its own separate output and is gone entirely.
- The `type_hazard` TIMESTAMP_LTZ-vs-NTZ regex is deleted cleanly here, not
  migrated. Re-homing it as a post-failure enricher on the contract-violation
  classifier is tracked separately.

### Testing and reliability uplift (testing epic, issue #23)

I raised the testing bar from happy-path fixtures to adversarial, generative,
and reproducible failure testing. The malformed-artifact robustness tier and
the core "degrade, never raise" hardening it surfaced shipped separately under
"Defensive artifact handling" (this release); this entry covers the generative
tiers built on top.

- New test tiers under `dbt_diagnostics/tests/` (`contract/`, `property/`,
  `e2e/`, `chaos/`; `robustness/` shipped with the defensive-handling work),
  each with a pytest marker, documented in `tests/README.md`. The pre-existing
  flat suite stays in place and migrates into tiers one PR at a time.
- Failure-injection engine (`tests/chaos/injectors.py`): a seeded `ChaosEngine`
  that perturbs real captured artifacts and asserts two contracts -- robustness
  (no mutation makes `classify()` raise) and detection (an injected fault
  signature is localized to exactly the owning classifier). Exploration is
  random; every run is replayable from its recorded seed.
- Property tier (`tests/property/`): Hypothesis generators for synthetic-valid
  `run_results`, asserting accounting and total-function invariants over a wide
  input space. Hypothesis profiles (`dev`/`ci`/`nightly`) are selected via
  `HYPOTHESIS_PROFILE`.
- `pyproject.toml`: hypothesis added to `dev` extra; pytest markers registered
  with `--strict-markers` enforced.

### Defensive artifact handling (robustness hardening)

The artifact-loading path and orchestration loop now tolerate malformed,
truncated, or hostile inputs without crashing.

- `load_json()` raises a new `ArtifactLoadError` (not `sys.exit(1)`
  directly), making it testable from non-CLI contexts. The CLI entry
  points catch and exit cleanly with an explained message.
- `_diagnose_all()` validates artifact shape defensively: checks
  `isinstance(run_results, dict)`, verifies `results` is a list, skips
  non-dict entries. Extends the "degrade, never raise" contract to the
  orchestration layer.
- `DagWalker._build_run_status_map()`: same defensive treatment (guards
  against non-dict run_results and non-dict entries in the results list).
- New `tests/robustness/test_malformed_artifacts.py` (11 parametrized
  malformed shapes) locks the degradation contract.
- `conftest.py`: Hypothesis profile registration now emits a warning
  when hypothesis is absent (instead of silently passing).

### Artifact schema version auto-detection

The tool now reads the dbt artifact's own embedded schema version
(metadata.dbt_schema_version) and reports whether it has been validated
against captured golden fixtures. On an unvalidated or unknown version,
a NOTE is emitted to stderr and parsing continues -- the "degrade to
unverified, never crash" contract.

- New `schema_version.py`: `detect_artifact_version()` and
  `check_compatibility()`. Parses the schema URL from metadata, falls
  back to shape-based kind inference when metadata is absent, and returns
  a `CompatibilityReport` with notes for anything unvalidated. Never
  raises on any input shape.
- Terminal: notes emitted to stderr on unvalidated versions (silent on
  the happy path).
- `--json`: new additive `artifact_schema` key; `schema_version` bumped
  1.1 -> 1.2.
- Tests: `test_schema_version.py` (22 tests) locks the detection and
  degradation contract; `test_main.py` gains `TestSchemaVersionDetection`
  asserting the wiring (JSON key present, terminal notes emitted).

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
