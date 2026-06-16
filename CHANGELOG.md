# dbt_diagnostics CHANGELOG

## [Unreleased]

### Testing and reliability uplift (testing epic, issue #23)

I raised the testing bar from happy-path fixtures to adversarial, generative,
and reproducible failure testing. The malformed-artifact robustness tier and
the core "degrade, never raise" hardening it surfaced shipped separately under
"Defensive artifact handling" (this release); this entry covers the generative
and tooling tiers built on top.

- New test tiers under `dbt_diagnostics/tests/` (`contract/`, `property/`,
  `e2e/`, `chaos/`; `robustness/` shipped with the defensive-handling work),
  each with a pytest marker, documented in `tests/README.md`. The pre-existing
  flat suite stays in place and migrates one PR at a time.
- Failure-injection engine (`tests/chaos/injectors.py`): a seeded `ChaosEngine`
  that perturbs real captured artifacts and asserts two contracts -- robustness
  (no mutation makes `classify()` raise) and detection (an injected fault
  signature is localized to exactly the owning classifier). Exploration is
  random; every run is replayable from its recorded seed.
- Property tier (`tests/property/`): Hypothesis generators for synthetic-valid
  `run_results`, asserting accounting and total-function invariants over a wide
  input space. Hypothesis profiles (`dev`/`ci`/`nightly`) are selected via
  `HYPOTHESIS_PROFILE`.
- Tooling: `pyproject.toml` gains a full `dev` test extra (pytest-cov,
  hypothesis, freezegun, mutmut, ruff, mypy), a separate `fixtures` extra
  (dbt-core/dbt-snowflake, for the future capture generator), coverage config
  with a ratcheting floor (77%, the measured baseline), ruff/mypy config
  (Python-quality only -- not static SQL linting), and `[tool.mutmut]`.
- CI: a Python 3.11/3.12/3.13 matrix with the offline tiers, a coverage gate,
  and a bounded chaos pass, plus a nightly hardening job (high-volume
  Hypothesis/chaos sweep and mutation testing). The workflow files
  (`ci.yml`, `nightly.yml`) are added separately because they require the
  GitHub `workflows` permission.

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

See git history for the full v0.5.0 and earlier notes.

---

## v0.4.0 -- 2026-06-06

### Self-Contained CLI + Major Enhancement Pass

See git history for the full v0.4.0 and earlier notes (trimmed here only in this
Unreleased-edit; the original entries remain in prior commits).
