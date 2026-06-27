# dbt_diagnostics CHANGELOG

## [Unreleased]

### Add repo policy adapter boundary for governance tooling

- I added a typed `scripts/triage/policy.toml` loader for repository identity,
  issue-contract identity, path roots, protected Codex/governance surfaces,
  hook wiring, quality receipt paths, product checks, compatibility schema
  checks, official-docs policy, and worker-packet verification commands.
- I moved the governance, Codex doctor, quality, hook, context, package, compat,
  and shell wrapper surfaces to consume the checked-in policy values while
  preserving current `dbt-diagnostics` behavior.
- I added a synthetic `example/widgets-service` policy fixture that proves the
  reusable governance paths do not require `dbt_diagnostics`,
  `dbt-diagnostics`, `donkey-kong-sandbox`, package checks, or dbt schema
  caches.
- I added fail-fast policy validation that rejects mutation-shaped keys,
  request payloads, forbidden tracker operation IDs, PR merge instructions, and
  unsupported official-docs live retrieval, browser automation, or freshness
  flags.
- I tightened the adapter boundary so Stop hook policy-load failures block
  finalization, worker-packet verification commands reject GitHub mutation
  command shapes, PR-1-only seams for hook venv and official-doc section title
  are rejected explicitly, and no-suffix package policies still inspect any
  built artifacts for forbidden members.

### Require official documentation evidence for external contracts

- I added a conditional `Official documentation evidence` issue-contract
  section for issues that rely on external platform behavior, product docs,
  API or CLI contracts, schema guarantees, hosted service rules,
  package-manager behavior, CI-service behavior, or similar official source
  material outside this repository, including unknown providers.
- I made the contract and standardize paths validate official documentation
  evidence offline with deterministic known-provider and generic external
  triggers plus independent provider-field and URL-host checks, without
  fetching docs, caching pages, running browser automation, or adding a GitHub
  write path.
- I added the unknown-provider workflow: maintainer-verified unknown sources
  and unknown URL hosts must preserve verification context, while critical
  unverified unknown sources must also appear in
  `Maintainer decisions and blockers`.
- I updated issue-governance docs and skill instructions so standardized issues
  record the provider, official URL, supported claim, version context,
  retrieval date, and residual uncertainty when the section is required.

### Add Codex mutation-blocking hooks

- I added repo-local Codex hooks for `PreToolUse`, `PermissionRequest`, and
  `Stop` so direct GitHub metadata mutation commands and known unsafe command
  shapes are blocked before execution or escalation.
- I made the Stop hook require a fresh digest-valid
  `output/codex/quality-receipt.json` after protected Codex or governance
  files change, and tightened that check so every changed protected path must
  be present in the receipt's deterministic
  `freshness_bound_protected_paths` field.
- I expanded deterministic GitHub mutation blocking to include GraphQL
  mutations, PR comments/reviews, repository edits, workflow dispatch/toggle
  commands, and secret/variable writes while keeping read-only `gh` commands
  allowed.
- I added a JSON-safe hook launcher and root-resolving hook configuration that
  fail closed when the git root, repo `.venv`, or hook script cannot be
  resolved.
- I wired hook JSON/script validation into the Codex check and doctor gates and
  documented hook trust and local `.venv` execution in `.codex/README.md`.

### Add Codex quality and harden governance artifacts

- I added `bash .codex/bin/action.sh codex-quality` as a local semantic quality
  gate for repository instruction surfaces and wrote a digest-bound local
  receipt under `output/codex/`.
- I kept `issue-work` read-only for nonconformant issue bodies and added a PR
  publication guard so implementation PRs use `Closes #<issue>` instead of
  `Refs #<issue>` as the only issue link.
- I tightened the Codex governance-boundary gate so it scans the issue contract,
  rejects forbidden operation IDs and verb-first tracker mutation instructions,
  and no longer treats generic read-only wording as enough to allow a mutation
  sentence.
- I clarified the direct maintainer-delegated GitHub operator-action boundary
  and the one-entry-per-PR progress-log convention in the repository agent
  instructions.
- I hardened `project-plan`, `backlog-synthesis`, and
  `synthesis-review-packet` validation so partial audits, stale packets,
  under-reported byte sizes, nested comments/snapshots, and mutation-shaped
  metadata payloads are rejected before advisory artifacts are emitted or
  consumed.
- I fixed governance issue normalization to preserve existing decision criteria,
  include conditional required sections, and treat `governance:` as authoritative
  even when legacy type labels are still present.

### Define the synthesis review packet contract

- I added the v1 `synthesis-review-packet` schema docs and machine schema for
  bounded LLM backlog review evidence.
- I added `validate_synthesis_review_packet()` so malformed, stale,
  over-budget, or mutation-shaped packets are rejected before any downstream
  LLM review consumes them.
- The packet contract remains read-only and advisory: no CLI command, builder,
  retrieval path, verdict schema, comments collection, or GitHub write path is
  added.

### Expose the read-only Project planner wrapper

- I added `bash .codex/bin/action.sh project-plan` as the stable Codex wrapper
  for the existing advisory Project planner.
- The wrapper delegates through `.codex/bin/triage-project-plan.sh`, forwards
  arguments to `python scripts/triage/triage.py project-plan`, and does not add
  any GitHub write path.
- I documented the wrapper alongside the existing read-only audit and frontier
  actions.

### Add read-only backlog synthesis signals

- I added a `backlog-synthesis` governance command that emits deterministic
  candidate signals for likely duplicates, explicit overlap, split candidates,
  semantic disposition hypotheses, and dependency-order inversions.
- I kept the existing readiness `recommended_disposition` map mechanical while
  surfacing semantic disposition hypotheses as additive audit fields and as a
  local synthesis override.
- I added the `backlog-synthesis` skill so cross-issue verdicts are proposed
  from the bounded signal artifact for maintainer review, with no tracker
  mutation path.
- I documented and validated the backlog-synthesis signal contract in
  `docs/BACKLOG_SYNTHESIS_SIGNALS_SCHEMA_V1.md` and
  `docs/backlog-synthesis-signals-schema-v1.json`.

### Add governance issue-kind classification

- I added a dedicated `governance` issue kind for process and tracker-contract
  decisions so they no longer have to masquerade as product test-verification
  work.
- I added the `governance:` title prefix to triage policy and kept genuine
  `test:` issues classified as `test_verification`.
- Governance issues require the reduced decision section set and do not require
  product-test sections by kind.

### Add read-only GitHub Project desired-state planning

- I added a `project-plan` governance command that emits a deterministic
  desired GitHub Project layout from an existing snapshot and readiness audit.
  It assigns audit-state columns, issue placement, and ordering without reading
  GitHub.
- I added dependency-inversion warnings when the planned order puts an issue
  before one of its direct dependencies.
- The emitted Project plan is not an approval bundle and contains no metadata
  operations, issue bodies, or state changes. Project and metadata writes remain
  unsupported by this planner.
- I added `validate_project_plan()` and a CLI self-check so malformed, stale,
  or mutation-shaped Project plans are rejected before they are emitted.
- I documented the Project plan contract in `docs/PROJECT_PLAN_SCHEMA_V1.md`
  and added the matching machine schema at `docs/project-plan-schema-v1.json`.

### Add issue contract, readiness audit, and read-only relay coordination

- I added the versioned issue contract and separate governance/readiness states.
- I exposed the documented command surface: `snapshot`, `audit`, `plan`,
  `project-plan`, `apply`, `contract`, `review-packet`, `standardize`, and
  `frontier`.
- I made audit output directly consumable by deterministic audit and
  implementation frontier selection, including explicit empty selection and
  bounded coordinator/worker-packet validation.
- I kept contract review, review packets, and body standardization local-only.
  Issue-body mutation remains forbidden and the metadata mutation allowlist is
  unchanged.
- I added focused governance tests, Codex relay documentation, stable read-only
  wrappers, and minimal repository skills.

### Fix governance triage readiness/contract correctness and relay stdout

Follow-up correctness fixes to the issue-governance toolchain under
`scripts/triage/`. All remain read-only and offline.

- I made tracker resolution pull-request-aware. Direct dependencies and
  unchecked checklist references that name a pull request are now resolved
  against the pull-request map instead of only the issue map, so a dependency on
  a merged/closed PR is satisfied (or correctly stale) rather than reported as a
  missing reference that blocks the issue.
- I made `Blocks: #N` an enforced inbound relationship. An open issue that
  declares it blocks another issue now blocks that issue's readiness, rather
  than being treated as an informational `related` reference.
- I corrected issue-kind inference. A scoped Conventional Commit prefix such as
  `fix(cli):` now strips the scope before matching, and the repository's
  configured `docs` type label is recognized, so neither is misclassified as a
  feature enhancement (with the wrong required sections and branch prefix).
- I stopped negated prose from manufacturing required work. "No open decisions"
  or "No external evidence required" no longer set the decision/external gates;
  a term counts only when it is not immediately negated.
- I made missing-path detection section-aware. A path named only in the
  Scope/deliverable section is an intended new file and no longer blocks the
  issue as a stale missing reference.
- I made unresolved placeholders block acceptance. A proposed body that still
  contains the generated "maintainer review is required" placeholder is reported
  as `needs_contract_revision`, so `standardize` does not return success for an
  unresolved contract.
- I gated frontier selection on audit coverage. The frontier now requires the
  readiness audit to cover every issue it will rank, so a partial
  (issue-filtered) `--audit-file` can no longer silently mis-rank or empty the
  frontier; the audit also records its `audit_scope`.
- I routed relay wrapper status to stderr. `codex_header` and the `codex_run`
  command trace now write to stderr, so `bash .codex/bin/action.sh frontier ...
  --json` (and `audit --json`) emit valid JSON on stdout for schema/digest
  consumers.

### Make issue file references verifiable by content anchor

Bare `path:line` citations in issue bodies are not reproducible -- line numbers
drift as code changes, and an in-range line is no proof of freshness. The
governance audit now reasons about citation content instead of position.

- I added a shared anchor-aware citation parser (`parse_file_references` in
  `scripts/triage/common.py`) that records line numbers, line ranges, symbol
  anchors (`path:symbol`), and quoted-snippet anchors (`path "snippet"`). The
  legacy `referenced_paths` helper is unchanged.
- The readiness audit emits three advisory findings: `unanchored-file-citation`
  (warning) recommends a stable anchor for a bare `path:line` or
  `path:line-range`; `unresolved-file-anchor` (warning) fires when a cited
  symbol or snippet no longer resolves in the current file; and
  `line-citation-past-eof` (info) is a one-directional "definitely stale" signal
  when a cited line exceeds the file's length. An in-range line is never
  certified as fresh.
- All three are advisory and never change `implementation_state`. A nonexistent
  path stays reported once as `missing-repo-path` and is skipped by the anchor
  check, so the same defect is not double-reported. The Scope/deliverable
  section exemption from missing-path detection also exempts the citation smell.
- I routed the `audit` command's path scan (`audit_snapshot` in
  `scripts/triage/triage.py`) through the same shared parser so both audit
  surfaces stay consistent, and added `check_unanchored_citations` and
  `check_file_anchors` toggles to `[audit]` in `scripts/triage/policy.toml`
  (default on).
- I documented the verifiable-reference guidance in the issue contract and added
  focused readiness tests for the smell, symbol and snippet resolution and
  staleness, past-EOF detection, the deliverable exemption, and the
  no-double-report behavior.

### Add AI-assisted drafting of missing contract sections (skill assist layer)

`review-packet` writes `proposed-body.md` with a placeholder for each section it
cannot establish, and the contract audit rejects a body that still contains the
placeholder. Filling those sections by hand is the slow step; the deterministic
tool cannot draft them without inventing facts.

- I extended the `issue-governance` skill with a bounded drafting subroutine: it
  reads `contract.json` (missing sections) and `review-packet.json` (repository
  context), drafts only the placeholder sections from cited source files, runs
  `standardize` to confirm the contract passes, and presents the
  placeholder-to-draft diff for maintainer review.
- I kept the deterministic tool unchanged. It still emits placeholders and gates;
  the drafting is an assistive, non-authoritative layer outside it.
- I required drafts to cite verifiable anchors (`path:symbol` or `path "snippet"`,
  never a bare `path:line`), to keep proven and inferred separate with
  hypothesis labels and an open-questions list, to mark each drafted section with
  a machine-authored provenance note, and to stop before any GitHub mutation.
- I documented the assist flow and its guardrails in `docs/ISSUE_GOVERNANCE.md`.
  No deterministic code, command surface, or mutation allowlist changed.

### Fix frontier merged-PR dependencies and scoped-audit cycle leakage

Two scope/dependency-resolution correctness fixes in the issue-governance
toolchain. Both remain read-only and offline.

The readiness audit was made pull-request-aware, but the implementation
frontier's own dependency-closure re-check still consulted only the issue map.
An otherwise-ready issue whose direct dependency was a merged pull request was
rejected as "direct dependencies are not closed" (the PR number is absent from
the issue map), even though `dependency_merge_evidence` was true -- a false
negative that kept implementable work out of the frontier.

- I made `implementation_frontier_candidates` in `scripts/triage/frontier.py`
  pull-request-aware via a shared `_dependency_is_closed` helper: a dependency
  is satisfied when it resolves to a closed issue or a closed pull request. The
  companion `dependency_merge_evidence` guard is unchanged, so a closed-unmerged
  PR dependency is still rejected.
- I fixed `build_worker_packet` to resolve a pull-request dependency from the
  pulls map, so the packet reports its real state instead of `unknown`.
- I added frontier tests: a merged-PR dependency is implementable, an open-PR
  dependency is rejected, and the worker packet reports the PR's closed state.
- I scoped the metadata audit to the requested issues. A scoped
  `audit --issues N` previously ran `audit_snapshot` over the whole snapshot and
  only post-filtered findings carrying an `issue` field, so a global finding such
  as a dependency cycle among unrelated issues (which has no `issue`) survived
  and could make the single-issue audit exit with errors. `make_readiness_audit`
  now passes the same `issue_filter` into `audit_snapshot`, which already drops
  out-of-scope issue-keyed findings and suppresses cycles that do not touch the
  filter; the redundant post-filter is removed.
- I added scoped-audit tests: an unrelated dependency cycle is excluded from a
  single-issue audit, while a cycle that includes the requested issue is kept.


<!-- BEGIN #39 -->
### Detect mixed-version manifest/run_results pairs (feat, issue #39)

A single diagnosis can consume a `manifest.json` and `run_results.json` that
came from different dbt versions -- a real case under `dbt build --defer
--state path/` and multi-invocation workflows, where the deferred manifest can
predate the live run_results. Correlating fields across such a pair (e.g.
mapping a result to a node) can silently misalign. The compatibility check now
compares the two artifacts and surfaces a note when they diverge.

- `CompatibilityReport` gained a computed `skew` (a `VersionSkew`) that compares
  the pair's dbt line. It prefers `metadata.dbt_version` (the fine-grained
  signal: patch differences like 1.11.0 vs 1.11.11 do not count as skew) and
  falls back to a coarse, historical schema-major -> dbt-minor-range table only
  when `dbt_version` is absent. The fallback uses ranges, not points, so
  co-occurring versions never flag; unknown majors yield no note (no false
  positive).
- On divergence the report emits an additive note (e.g. "manifest from dbt 1.7
  but run_results from dbt 1.11 -- likely a --defer/state run; cross-artifact
  correlation may be approximate"). A matching pair emits none. The note rides
  the existing `CompatibilityReport.notes` plumbing, so it prints with no change
  to `main.py`.
- `--json` `artifact_schema` gains an additive `skew` block
  (`diverged`/`source`/`run_results_signal`/`manifest_signal`/`note`); existing
  keys and the meaning of `supported`/`all_supported` are unchanged.
- Detection is best-effort and never raises on missing or garbled
  `dbt_version` (degrades to the majors fallback, then to silence).
- Added `unit` tests for divergence/match/patch-insensitivity, the majors
  fallback (divergence and overlap), unknown majors, never-raise on garbled
  input, and the additive `--json` shape.
<!-- END #39 -->

<!-- BEGIN #42 -->
### Consume catalog.json for schema-drift diagnosis (feat, issue #42)

`target/catalog.json` (from `dbt docs generate`) carries dbt's last-known column
types. The schema-drift classifier now uses them as a hint, strictly
best-effort: present -> enrich; absent or stale -> degrade silently and let the
live `INFORMATION_SCHEMA` recovery remain authoritative.

- `discover.resolve_project_paths` now resolves `target/catalog.json` (optional,
  non-fatal). `cmd_diagnose` loads it best-effort -- an absent or unparseable
  catalog yields `None` (reusing the never-raise `load_json` from #38) and
  threads through `_diagnose_all` into `DiagnosticContext.catalog`.
- `consumed_paths.REGISTRY` gains catalog entries (`nodes[].columns[].type`,
  `nodes[].columns[].name`, `sources[].columns[].type`), each with a
  `live_recovery` pointing at `INFORMATION_SCHEMA.COLUMNS`, so the catalog's
  consumed paths share the same declarative contract as manifest/run-results.
- New never-raising `compat.safe` catalog accessors (`catalog_node`,
  `catalog_column_type`) return `None`/degrade on any missing or garbled input.
- `schema_change_error` surfaces the last-known cataloged type for the drifted
  column as an additive hint in its explanation when a catalog is present; with
  no catalog (or a stale one missing the node) the output is unchanged and the
  diagnosis falls back to the live warehouse. `--json` is additive only.
- Tests follow the project's real-artifact policy (no synthetic fixture files):
  the pure `compat.safe` catalog accessors are unit-tested with inline dict
  inputs, degradation is `robustness`-tested against real artifacts plus an
  absent/empty catalog, and the end-to-end "consumes real cataloged types"
  guarantee is a `contract` test against a real catalog captured from
  dckallos/artwork-db (scenario 12), skipped until that fixture is committed.
  The capture procedure is documented in `docs/FIXTURE_CAPTURE.md`.
  `contract_violation` is intentionally untouched this session (potential follow-up).

  Note: gating the catalog's consumed paths in `schema_diff`/CI (catalog v1) is
  handled in #40, which owns the schema cache and CI matrix.
<!-- END #42 -->

<!-- BEGIN #40 -->
### Run the schema-diff gate in CI against a first-party schema cache (chore/ci, issue #40)

`scripts/compat/schema_diff.py` now actually runs in CI, so a future dbt schema
that drops a field we consume (with no declared fallback) fails the build loudly
instead of silently breaking the offline read path.

- `.github/workflows/ci.yml` gains a cache-aware `compat-schema-gate` job: it
  diffs consumed paths across adjacent manifest majors (v4->v12) and run-results
  majors (v4->v6), plus a catalog v1 / sources v3 presence check. Until the
  committed cache exists it skips, so it cannot block before the cache lands.
- Proved the gate offline with `tests/test_compat_schema_gate.py` (`-m contract`):
  a synthetic schema that drops `relation_name` with no fallback makes
  `schema_diff` exit nonzero; a stable schema exits 0.
- `schema_diff.py --artifact` now also accepts `catalog` and `sources`, matching
  the artifacts now present in `consumed_paths.REGISTRY`.
- `pyproject.toml` package-data now ships `fixtures/schemas/**/*.json` so the
  committed cache travels with the package.
- The first-party schema cache itself (`fixtures/schemas/**` + `PROVENANCE.json`)
  is NOT committed here: the build sandbox has no network, so `fetch_schemas.py`
  (the only networked component) cannot run. The five first-party confirmation
  tasks (relation_name v1-v12, compiled_sql->compiled_code at v7, run-results
  majors 1.3-1.6, catalog v1 / sources v3, dbt-common/dbt-adapters split tags)
  remain PROVISIONAL with the exact maintainer commands recorded in
  `docs/RESEARCH_VERSION_COMPAT_FINDINGS.md` rather than being promoted falsely.
<!-- END #40 -->

### Harden the artifact read path against interrupted-run corruption (fix, issue #38)

An interrupted `dbt build` can leave a half-written, empty, or non-UTF8
`run_results.json`/`manifest.json` behind. The read boundary now treats that as
a diagnosable condition rather than a crash or an opaque error.

- `load_json` reads bytes and classifies failures: a missing file raises
  `ArtifactLoadError(kind="not_found")` (run `dbt build` first), while an empty,
  truncated, or non-UTF8 artifact raises `ArtifactLoadError(kind="corrupt")`
  carrying a single user-facing note: "<artifact> appears truncated or corrupted
  (interrupted run?); re-run `dbt build` to regenerate it". `cmd_diagnose`
  surfaces the corrupt case as a clean `NOTE:` instead of a stack trace.
- Fixed a real escape: non-UTF8 bytes previously raised `UnicodeDecodeError` (a
  `ValueError`, not an `OSError`), which slipped past `load_json`'s handlers and
  surfaced as a traceback. It now degrades like any other corrupt artifact.
- `compat.schema_model.SchemaDoc` tolerates a non-dict schema root so
  `path_resolver.resolve` returns an empty result instead of raising on a
  malformed schema document.
- Added `robustness`-marked tests for every threat case (truncated, empty,
  whitespace-only, non-UTF8, wrong-shape JSON, missing `nodes`/`results`,
  metadata without a valid schema URL, null entries) asserting no exception
  escapes and a degraded result/note is produced; added `unit`-marked tests
  proving `compat.safe.*` return `None` and `path_resolver.resolve` returns an
  empty list on non-dict / missing-key inputs.
- No change to the `diagnose --json` output shape; `artifact_schema` is
  additive and unchanged.

### Safe artifact access wiring for classifiers and enrichers (feat, issue #37)

I wired classifier and enricher artifact reads for compiled/raw SQL, relation
names, and Snowflake adapter response fields through `dbt_diagnostics.compat.safe`,
so old manifest keys (`compiled_sql`/`raw_sql`) and current keys
(`compiled_code`/`raw_code`) resolve the same way without changing current-version
output.

- Direct reads of `compiled_code`/`compiled_sql`, `raw_code`/`raw_sql`,
  `relation_name`, and Snowflake `adapter_response.query_id`/`rows_affected` now
  go through never-raising safe accessors. Missing or malformed artifact input
  returns `None`, so callers omit optional snippets/enrichment or fall through to
  live recovery instead of inventing defaults.
- Added safe accessor coverage for old-style and new-style manifest nodes,
  non-dict/missing inputs, and adapter response access.
- Extended the same safe-accessor wiring to the `tracers/` package (`dag_walker`,
  `diff_tracer`, `column_tracer`), which still read `compiled_code`/`relation_name`
  directly (some without the `compiled_sql` fallback), so lineage and diff tracing
  are version-correct on pre-1.3 manifests too.
- Added a guard test that scans `classifiers/`, `enrichers/`, and `tracers/` for
  reintroduced direct raw artifact reads (subscript check restricted to reads, so
  dict writes are not flagged).
- No change to the diagnose `--json` output shape or existing golden outputs.

### Robust naive/aware timestamp comparison in run-history lag check (fix, issue #50)

- `run_identity._is_lagging` now coerces both the run timestamp and the
  query-history watermark to timezone-aware UTC (via a new `_to_aware_utc` helper)
  before comparing. This fixes a corner case where a naive run timestamp paired with
  an aware watermark raised `TypeError`, which a blanket `except` silently swallowed
  (reporting "not lagging" and suppressing the retry). Parse failures now narrow to a
  `None` result instead of a broad `except Exception`, and the `datetime` import was
  moved to module scope.
- Added unit tests for `_to_aware_utc` and `_is_lagging` across aware/aware,
  naive/naive, mixed naive/aware, unparseable, and empty-history cases.

### Cross-version compatibility layer for consumed artifact fields (feat, issue #35)

I added `dbt_diagnostics/compat/`, a small offline layer that hardens the ~12
artifact dict paths the classifiers/enrichers read, so the tool parses and
diagnoses artifacts across dbt-core versions without crashing and without a
third-party parser dependency.

- New package: `consumed_paths.py` (declarative registry of consumed paths with
  version fallbacks and a Tier-A `live_recovery` per field), `schema_model.py`
  (stdlib JSON Schema resolver: `$ref`, `$defs`/`definitions`, `allOf`,
  `anyOf`/`oneOf`), `path_resolver.py` (resolve a path across node-type unions to
  per-definition presence), `safe.py` (never-raising accessors with the dbt 1.3
  `compiled_code`/`raw_code` <- `compiled_sql`/`raw_sql` fallbacks), and
  `DESIGN.md`.
- New tooling: `scripts/compat/schema_diff.py` (CI gate; diffs two first-party
  schemas by consumed path, nonzero exit only on an unguarded break) and
  `scripts/compat/fetch_schemas.py` (the only networked code; caches first-party
  schemas + `PROVENANCE.json` for the offline diff).
- Tests: `dbt_diagnostics/tests/test_compat_schema_diff.py` (marker `unit`).
- First-party is the source of truth (schemas.getdbt.com / dbt-core + real
  artifacts); `dbt-artifacts-parser` is not a dependency or oracle. Runtime stays
  offline. No change to the diagnose `--json` `schema_version` shape (additive).

### Version-controlled branch-protection policy (governance, issue #32)

I codified the branch-protection policy for `donkey-kong-sandbox` and `main` as
in-repo scripts under `scripts/governance/`, so the policy is reviewable,
diffable, and roll-back-able like any other change. The maintainer applies it
from a local `gh` session; nothing runs in CI or from an agent.

- Added `policy.donkey-kong-sandbox.json` and `policy.main.json` (classic
  protection bodies), plus `apply-`, `export-`, and `rollback-` shell scripts
  and a README.
- Policy: require a PR before merging, require the `test` status check (strict),
  require linear history and conversation resolution, block force-push and
  deletion, `enforce_admins: false` (owner break-glass). Both branches are
  identical by design under solo maintainership; the files are split so `main`
  can diverge later.
- No tool behavior or `--json` `schema_version` change.

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

### Optimize per-issue governance: loop guidance, snapshot fallback, and audit-noise fixes

Improvements to the issue-governance toolchain surfaced by dogfooding issue #74.
All changes remain read-only and offline; no GitHub mutation path is added.

- I gave the `issue-governance` skill an explicit working loop instead of a flat
  recipe: a single-issue disposition hypothesis (keep / duplicate / split /
  wont-do) that escalates rather than standardizing an issue whose existence is
  in question; a draft -> self-verify-anchors -> standardize -> bounded-repair
  cycle (max three passes); and explicit stop/escalation conditions. Cross-issue
  judgment is declared out of scope for a per-issue run.
- I moved the non-negotiable governance rules (read-only, one issue at a time,
  content anchors) into `AGENTS.md` so they hold even when no skill is loaded.
- I stopped prose path shorthand from blocking readiness. A citation that joins
  existing top-level directory names into one token (for example
  `.agents/.codex`) is now a non-blocking `prose-path-shorthand` warning,
  segregated from `missing_repository_paths` via the additive
  `prose_path_references` field; a genuine stale path still blocks.
- I suppressed a redundant recommended-section warning. When acceptance/test
  text already demonstrates negative, degradation, and regression coverage, the
  contract no longer also asks for a separately headed
  "Negative, degradation, and regression coverage" section.
- I relaxed the `.codex` task-context gate. `context <issue>` now falls back to a
  `--snapshot` read when `gh` is missing or unauthenticated, so a public
  read-only issue is reachable offline instead of failing hard.
- I corrected the Codex getting-started note that implied `docs/` counts toward
  `project_doc_max_bytes`; only the AGENTS.md hierarchy does.
- I added focused tests for the snapshot fallback, the coverage-suppression
  rule, and the prose-path warning. The governance suite passes (135).

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
