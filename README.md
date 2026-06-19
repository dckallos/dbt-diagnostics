# dbt-diagnostics

[![CI](https://github.com/dckallos/dbt-diagnostics/actions/workflows/ci.yml/badge.svg?branch=donkey-kong-sandbox&event=push)](https://github.com/dckallos/dbt-diagnostics/actions/workflows/ci.yml)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![Status: pre-release](https://img.shields.io/badge/status-pre--release-orange)

> **Pre-release software:** The package is under active development, is Snowflake-only, and has not completed its first public release. Several correctness and live-verification issues listed below are release blockers. Do not treat the current output as an authoritative incident verdict without checking the underlying dbt artifacts and warehouse evidence.

**You're in the right place if you're already stuck.** The `dbt-diagnostics` package provides you with deterministic workflows that help you once your data pipeline is already broken, similar to American healthcare diagnostics that only help you once you're already sick. I'd recommend that you eat more vegetables so that you're not seeing your doctors so frequently, and I'd recommend dbt packages and tools such as [`dbt-utils`](https://hub.getdbt.com/dbt-labs/dbt_utils/latest/), [`dbt-expectations`](https://hub.getdbt.com/metaplane/dbt_expectations/latest/), [`dbt-project-evaluator`](https://hub.getdbt.com/dbt-labs/dbt_project_evaluator/latest/), [`dbt-audit-helper`](https://hub.getdbt.com/dbt-labs/audit_helper/latest/), [`dbt-checkpoint`](https://github.com/dbt-checkpoint/dbt-checkpoint), [SQLFluff](https://www.sqlfluff.com/), [Elementary](https://docs.elementary-data.com/data-tests/dbt/dbt-package), and the [dbt Fusion engine and VS Code extension](https://docs.getdbt.com/docs/fusion) so that your pipeline doesn't break and you don't need this `dbt-diagnostics` package.

## What this package is for

`dbt-diagnostics` is a post-failure debugging tool. It starts with the artifacts dbt already produced, identifies failed or skipped work, adds source and lineage context, and can optionally query Snowflake metadata to test likely explanations.

The package is intended to answer questions such as:

- Which dbt node actually failed first?
- Is this a compilation error, a warehouse runtime error, a contract mismatch, or a test assertion failure?
- Which compiled SQL line and expression are involved?
- Is the referenced object declared in the manifest?
- Does the relation or column exist now?
- Did the run role appear to lack a required privilege?
- Did the failing model change since a previous manifest?
- Are many downstream errors symptoms of one upstream failure?

It is deliberately not another static SQL linter. Use SQLFluff, dbt's own parser and tests, dbt-checkpoint, dbt-project-evaluator, and your CI system before production. Use this package when those controls did not prevent the failure.

## Prevention tools worth using first

The tools below solve different parts of the prevention problem. They are complements, not interchangeable products.

| Tool | Useful before a failure because it can... |
| --- | --- |
| [`dbt-utils`](https://hub.getdbt.com/dbt-labs/dbt_utils/latest/) | Add widely used generic tests and reusable macros. |
| [`dbt-expectations`](https://hub.getdbt.com/metaplane/dbt_expectations/latest/) | Add Great Expectations-style assertions directly to dbt projects. |
| [`dbt-project-evaluator`](https://hub.getdbt.com/dbt-labs/dbt_project_evaluator/latest/) | Evaluate project structure, modeling conventions, and DAG hygiene. |
| [`dbt-audit-helper`](https://hub.getdbt.com/dbt-labs/audit_helper/latest/) | Compare old and new relations or queries during migrations and refactors. |
| [`dbt-checkpoint`](https://github.com/dbt-checkpoint/dbt-checkpoint) | Run dbt-aware pre-commit checks for documentation, tests, metadata, and project consistency. |
| [SQLFluff](https://www.sqlfluff.com/) | Parse, lint, and often auto-fix SQL, including dbt projects through its dbt templater. |
| [Elementary](https://docs.elementary-data.com/data-tests/dbt/dbt-package) | Add anomaly tests, artifact collection, test-history tracking, and dbt-native observability. |
| [dbt Fusion and the dbt VS Code extension](https://docs.getdbt.com/docs/fusion) | Provide fast parsing, static analysis, live error detection, editor feedback, and lineage during development. |

Check each tool's current dbt version, adapter, and Fusion compatibility before adding it to a project. Those support matrices change independently.

## High-level functionality

### Artifact-aware diagnosis

The CLI reads dbt artifacts rather than asking you to reconstruct a failed run by hand:

- `target/run_results.json` - required; identifies statuses, messages, timing, and adapter responses.
- `target/manifest.json` - required; supplies nodes, sources, dependencies, compiled code, relation names, and column declarations.
- `target/catalog.json` - optional; used as a stale-tolerant hint about last-known relation and column metadata.
- A previous `manifest.json` - optional; enables change comparison for the failing node and its immediate upstream dependencies.

The current compatibility layer detects artifact schema URLs, warns on unknown or unvalidated versions, and reports likely manifest/run-results version skew. The code currently marks manifest schema v12 and run-results schema v6 as the validated majors. Broader and Fusion-generated artifact compatibility still require real-fixture validation.

### Error classification

The current classifier set covers:

| Class | Examples |
| --- | --- |
| `contract_violation` | Model output and enforced contract disagree on a column or type. |
| `compilation_error` | Undefined Jinja names, missing `ref()` targets, syntax failures, or materialization constraints. |
| `runtime_error` | Missing objects, invalid identifiers, insufficient privileges, and other Snowflake database errors. |
| `schema_change_error` | A column declared upstream appears inconsistent with the failing runtime reference. This remains a hypothesis until live evidence confirms it. |
| `timeout_error` | Statement timeout or warehouse suspension messages. |
| `data_error` | Numeric conversion or overflow, oversized strings, and division by zero. |
| `test_failure` | A dbt test query ran but returned failing rows or breached a threshold. |

Unrecognized errors remain visible as `unknown`; the tool should not hide the raw dbt message simply because no classifier owns it.

### Compiled SQL and source context

Where the artifacts contain compiled SQL and the database error contains a line number, the tool can:

- Extract a small compiled SQL window around the failing line.
- Record the reported line and position.
- Use `sqlglot` with the Snowflake dialect to locate an output expression or CTE.
- Search the source model for the corresponding alias definition.
- Compare current and previous compiled SQL when a previous manifest is supplied.

### Lineage context

The manifest DAG is used to show the failing node and relevant upstream nodes. The current code records manifest status, run status, relation names, and optional live status on each lineage step.

The current flat-list disconnect algorithm is a known pre-release weakness on branching DAGs. Before the first release, disconnect inference must use actual graph edges or explicit paths so that sibling nodes are never mistaken for parent-child boundaries.

### Optional live Snowflake evidence

When a Snowflake connection is available, the package can currently attempt metadata-only checks such as:

- `DESCRIBE TABLE` for actual columns and types.
- `SHOW TABLES` for relation visibility.
- `SHOW PARAMETERS` for session settings involved in a diagnosis.
- `SHOW GRANTS` for role-level grant evidence.
- `INFORMATION_SCHEMA.QUERY_HISTORY` for the executed statement, error code, message, role, user, and warehouse.

These probes are meant to refine a diagnosis, not silently convert missing evidence into certainty. The live evidence semantics are one of the main areas being hardened before release.

### Root-cause grouping

The package can collapse repeated object-not-found failures into a root-cause group and annotate downstream failures that have a failed parent. This is useful when one upstream error produces dozens of skipped or repeated downstream results.

The generic report-grouping implementation is still too broad and can group unrelated failures that share a schema. That behavior is a release blocker and will be replaced with normalized root-cause signatures.

### Human and JSON output

The CLI supports:

- Human-readable terminal output rendered with Jinja templates.
- Optional ANSI color, including `NO_COLOR`, `--color`, and `--no-color` behavior.
- `--verbose` output for more evidence and lineage detail.
- `--json` for machine consumption.
- Non-zero exit status when errors or failures are diagnosed.
- `--no-fail` for exploratory use when the command should still exit zero.

The top-level JSON schema is currently version `1.2` and follows an additive-only policy. Full JSON parity with the text renderer is not complete yet: live enrichment, complete live lineage, and manifest diff data must be finalized before release.

## How the current pipeline works

```text
run_results.json + manifest.json (+ optional catalog / previous manifest)
                              |
                              v
                    classify failed results
                              |
                              v
               attach SQL, source, and DAG context
                              |
                              v
          optionally collect live Snowflake metadata evidence
                              |
                              v
                 group related root-cause symptoms
                              |
                              v
                    render terminal text or JSON
```

## Installation

The package is not yet published to PyPI. Install it from the repository while it is under development.

### Artifact-only installation

```bash
git clone https://github.com/dckallos/dbt-diagnostics.git
cd dbt-diagnostics

python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .
```

On Windows PowerShell, activate the virtual environment with:

```powershell
.venv\Scripts\Activate.ps1
```

### Include live Snowflake support

```bash
pip install -e ".[live]"
```

### Development installation

```bash
pip install -e ".[dev,live]"
```

The declared Python requirement is 3.11 or newer.

## Quick start

Run from inside a dbt project, or from one of its subdirectories.

### Diagnose from artifacts only

```bash
dbt-diagnostics --no-live
```

The CLI walks upward until it finds `dbt_project.yml`, then reads the usual files under `target/`.

### Diagnose with live Snowflake metadata

```bash
dbt-diagnostics
```

Live mode is currently the default unless `--no-live` is supplied. That default is under review for the initial release because opening a warehouse connection should be an explicit and unsurprising user decision.

### JSON output

```bash
dbt-diagnostics --no-live --json
```

### Compare against a previous manifest

```bash
dbt-diagnostics \
  --no-live \
  --previous-manifest path/to/previous/manifest.json
```

### Override artifact paths

```bash
dbt-diagnostics \
  --no-live \
  --project-dir path/to/dbt_project \
  --run-results path/to/run_results.json \
  --manifest path/to/manifest.json
```

A current limitation is that explicit artifact paths still require a resolvable dbt project directory. Standalone artifact diagnosis is on the pre-release checklist.

### Run the bundled demonstration

```bash
dbt-diagnostics demo
```

The demo is useful for seeing the renderer. Bundled fixtures that are not named `real_*` are synthetic and should not be treated as proof of real dbt or Snowflake behavior.

## Project and profile discovery

The current CLI resolves configuration in this order:

1. Explicit CLI flags.
2. An optional YAML config file supplied with `--config`.
3. Auto-detection by walking upward for `dbt_project.yml`.

For Snowflake profiles, it searches:

1. `DBT_PROFILES_DIR/profiles.yml`.
2. `<project_dir>/profiles.yml`.
3. `~/.dbt/profiles.yml`.

It can resolve simple `{{ env_var('NAME') }}` and `{{ env_var('NAME', 'default') }}` expressions. It also supports `--env-file` and automatic `.env` discovery.

Because profile and environment discovery can load credentials, use `--no-live` when you only want artifact analysis. Never commit `.env`, `profiles.yml`, private keys, passwords, or generated query text containing secrets.

## Live-mode safety

Until the live evidence model is hardened:

- Use a dedicated, least-privileged diagnostic role.
- Prefer read-only metadata access.
- Do not run the tool with an account-administrator role.
- Review generated `GRANT`, `ALTER`, and `dbt` commands before copying them.
- Treat `unverified`, missing, and permission-related conclusions as hypotheses unless the underlying probe and identity are clear.
- Use `--no-live` in CI unless the job is explicitly designed and credentialed for live integration testing.

The current code is intended to use metadata operations rather than warehouse-scanning data probes. Future data-scanning checks must be opt-in and cost-gated.

## Current project status

- The repository is pre-release. `pyproject.toml` currently carries package version `0.5.0`, but there has not yet been an initial public package release.
- The implemented CLI can discover a dbt project, load required artifacts, classify errors and test failures, render terminal output, and emit JSON.
- Snowflake live enrichment is implemented as an optional dependency and is currently enabled by default at runtime unless `--no-live` is passed.
- Seven diagnosis classes are implemented: contract, compilation, runtime, possible schema change, timeout, data, and test failure.
- Compiled SQL snippets, basic source locations, DAG context, root-cause groups, cascading-failure notes, and previous-manifest diffs are implemented.
- Artifact schema detection, version-skew reporting, version-tolerant field accessors, and an offline first-party schema-diff tool are implemented.
- `catalog.json` is consumed as an optional last-known schema hint; a real captured catalog fixture is still needed to activate the strongest contract test for that path.
- The repository includes pytest markers for unit, contract, property, robustness, end-to-end, chaos, and live testing.
- The current CI workflow has attribution guards, a Python 3.12 pytest job, and a compatibility-schema job. Branch protection currently requires only the `test` status, not every guard.
- Contribution guidance, a pull-request template, a feature issue template, branch-protection policy files, and governance scripts already exist.
- The package remains intentionally Snowflake-only. A general warehouse adapter is not complete and should not be implied by the public API.
- The package has useful foundations and does not need a rewrite. The live-evidence, lineage, grouping, and report-resolution subsystems need targeted refactoring before release.

## Work required before the initial release

The list below is the release gate, not a promise that every future idea must land before shipping.

### Correctness and confidence

- [ ] Fix query-history matching to use Snowflake's real failed execution states rather than `EXECUTION_STATUS = 'FAIL'`.
- [ ] Replace ambiguous `True` / `False` / `None` and empty grant dictionaries with typed probe results that preserve `confirmed`, `not found`, `not visible`, `query failed`, and `unsupported` states.
- [ ] Record which role or connection identity produced every live observation.
- [ ] Stop treating an empty visibility-limited `SHOW TABLES` result as proof that an object physically does not exist.
- [ ] Separate database `USAGE`, schema `USAGE`, object privileges, and `CREATE TABLE` evidence.
- [ ] Make relation checks exact and relation-kind-aware so tables, views, quoted identifiers, wildcard characters, and inaccessible schemas are handled honestly.
- [ ] Close every cursor reliably, including cursor-acquisition and cursor-close failure paths.
- [ ] Add a top-level degradation boundary so one failed live probe does not abort the entire diagnosis.
- [ ] Calibrate schema-change wording so a manifest declaration remains a hypothesis until the live relation is described.

### Lineage and root-cause resolution

- [ ] Replace flat BFS lineage lists as the basis for disconnect inference with an edge-preserving graph or explicit root-to-ancestor paths.
- [ ] Restrict object matches to ancestors that are actually reachable from the failing node.
- [ ] Preserve real path depth and report when a lineage search is truncated.
- [ ] Ensure a dbt execution error outranks the weaker fact that a node is declared in the manifest.
- [ ] Add positive tests that find the correct disconnect on a real edge, not only tests that suppress a previous false result.
- [ ] Group reports by a normalized root-cause signature rather than only `error_class` and schema.
- [ ] Render each report exactly once while preserving member-specific detail in verbose output.

### Structured evidence and output

- [ ] Separate classifier observations, live evidence, final resolutions, confidence, and rendered prose.
- [ ] Replace ordered mutation of `fix_suggestion` strings with structured evidence and one final resolution step.
- [ ] Avoid running a new evidence collector and the legacy enricher against the same finding in the same diagnosis.
- [ ] Serialize live enrichment, complete live lineage, graph edges, and manifest diffs in `--json` output.
- [ ] Define a redaction policy for matched query text, literals, object names, and credential-adjacent data.
- [ ] Add golden terminal and JSON output tests for every diagnosis class.
- [ ] Use the generic Jinja template as an explicit fallback when a new classifier has no dedicated template.

### Artifact, configuration, and compatibility hardening

- [ ] Validate top-level manifest, run-results, catalog, node, source, timing, and profile shapes before downstream code uses them.
- [ ] Centralize repeated run-results lookups in one indexed, version-tolerant view.
- [ ] Make the consumed-path registry cover every artifact field the runtime actually reads.
- [ ] Make the schema gate compare relevant definitions, requiredness, nullability, and types instead of only "present anywhere."
- [ ] Centralize fallback aliases so the runtime accessor layer and compatibility registry cannot drift.
- [ ] Consolidate duplicate profile discovery and `.env` loading without changing documented search behavior.
- [ ] Decide whether explicit `--run-results` and `--manifest` inputs may run without a dbt project and implement the decision clearly.
- [ ] Decide whether live mode remains the default or becomes an explicit `--live` option. Use a mutually exclusive CLI flag group either way.

### Real evidence and test coverage

- [ ] Capture and commit provenance-recorded `real_*` manifest and run-results fixtures for every supported failure family.
- [ ] Capture the missing real healthy `catalog.json` used by the schema-drift contract scenario.
- [ ] Build a cross-version real-artifact matrix for supported dbt and dbt-snowflake versions.
- [ ] Validate real artifacts against first-party dbt schemas and compare the schemas with runtime behavior.
- [ ] Add branching-DAG, quoted-identifier, quoted-role, view, role-hierarchy, visibility, malformed-artifact, and mixed-version regression cases.
- [ ] Add a credential-gated live Snowflake job using a disposable database/schema and least-privileged test roles.
- [ ] Verify query-history retention, role visibility, error-state values, parameter levels, and connector tuple shapes against a real Snowflake account.
- [ ] Run the entire package suite and retain the evidence of a green release candidate.

### CI, packaging, and release engineering

- [ ] Test every supported Python version, not only Python 3.12. The current `>=3.11` declaration should be matched by a CI matrix or narrowed.
- [ ] Add `python -m compileall`, source-distribution and wheel builds, installed-wheel smoke tests, and README rendering checks.
- [ ] Make `guards` and `compat-schema-gate` required branch-protection checks instead of requiring only `test`.
- [ ] Add a `.pre-commit-config.yaml` for fast local checks and the existing attribution guard.
- [ ] Add a root `LICENSE` file and declare the license in project metadata before calling the project open source.
- [ ] Add `readme = "README.md"`, project URLs, maintainers/authors as appropriate, license metadata, and useful classifiers to `pyproject.toml`.
- [ ] Add `SECURITY.md` with supported versions and a private vulnerability-reporting path.
- [ ] Finalize `CHANGELOG.md`, the release version, and the release checklist.
- [ ] Build and publish through PyPI Trusted Publishing from a protected GitHub environment rather than storing a long-lived PyPI token.
- [ ] Test the release workflow on TestPyPI before the first production upload.

## Work that can wait until after the initial release

These are useful directions, but they should not delay a safe, honest Snowflake-only release:

- A complete `WarehouseAdapter` and a second backend such as BigQuery, PostgreSQL, or DuckDB.
- `sources.json` freshness diagnosis.
- Structured dbt event/log ingestion.
- `partial_parse.msgpack` stale-cache analysis.
- Warehouse-scanning distinctness, orphan-key, and duplicate-sample probes, provided they are opt-in and cost-gated.
- A hosted documentation site.
- Advanced automatic compatibility-update proposals.
- Rich terminal UI or interactive lineage visualization.

## Recommended GitHub and package additions

### Badges

Yes, the repository should have a CI badge. The badge at the top of this README points to the `ci.yml` workflow on the active integration branch and reports the result of push-triggered runs.

Keep badges factual and limited:

- Keep: CI status and supported Python versions.
- Add after publication: PyPI version and package link.
- Add after choosing a license: license badge.
- Add only if measured and enforced: coverage badge.
- Avoid vanity badges and download counters that do not help a user decide whether the package is healthy or compatible.

A green badge is not a substitute for requiring every important workflow in branch protection. The badge and the merge rules should describe the same quality gate.

### Community and support files

The repository already has `CONTRIBUTING.md`, issue guidance, and a pull-request template. Useful additions are:

- `SECURITY.md` for private vulnerability reporting.
- `CODE_OF_CONDUCT.md` if outside contributors are expected.
- `SUPPORT.md` if feature questions, bug reports, and security reports need different channels.
- A concise compatibility table covering Python, dbt artifact schemas, dbt versions validated by real fixtures, Snowflake connector versions, and Fusion status.

### Security automation

Consider enabling:

- Dependabot security and version updates for Python and GitHub Actions.
- GitHub secret scanning and push protection.
- CodeQL or another Python static-analysis workflow.
- Dependency review on pull requests.
- Least-privilege GitHub Actions permissions at the job level.

### Release quality

Recommended release mechanics:

- Build once, then publish the exact tested wheel and source distribution.
- Use a protected `pypi` GitHub environment.
- Use PyPI Trusted Publishing with OIDC.
- Keep PyPI attestations enabled.
- Publish from a GitHub Release or an explicitly protected version tag.
- Attach the wheel and source distribution to the GitHub Release.
- Keep semantic versions and the changelog synchronized.

### Documentation polish

High-value additions after behavior stabilizes:

- One real, scrubbed terminal-output example for each major diagnosis class.
- A small architecture diagram showing artifact analysis versus live evidence.
- A troubleshooting section for profile discovery, missing connectors, unknown artifact schemas, and Snowflake visibility.
- A compatibility matrix generated from the real-fixture test suite.
- A short threat model explaining what live mode reads, what it executes, and what it never uploads.

## Development

Create an environment and install the development extras:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev,live]"
```

Run the current test suite:

```bash
pytest -q
```

Useful focused commands include:

```bash
pytest -m unit
pytest -m contract
pytest -m robustness
pytest -m e2e
pytest -m "not live"
python -m compileall dbt_diagnostics
```

A live test should be skipped unless the required Snowflake credentials and disposable test resources are explicitly configured.

## Repository layout

```text
dbt_diagnostics/
  classifiers/   Parse failed dbt results into structured reports.
  tracers/       Inspect compiled SQL, source files, DAG relationships, and diffs.
  enrichers/     Connect to Snowflake and collect live metadata evidence.
  compat/        Handle artifact schema versions and tolerant field access.
  templates/     Render human-readable terminal output.
  tests/         Unit, contract, robustness, property, end-to-end, chaos, and live tests.

scripts/
  compat/        Fetch and compare first-party dbt artifact schemas.
  governance/    Apply, export, and roll back branch-protection policy.
```

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before opening a pull request.

The repository uses one issue per pull request, conventional commit subjects, an additive-only JSON schema policy, and a strong preference for real dbt artifacts over guessed fixtures. Behavior changes should include tests and a changelog entry.

Bug reports should include, after removing secrets:

- The dbt command that failed.
- dbt and adapter versions.
- The artifact schema URLs from `metadata.dbt_schema_version`.
- The relevant result entry from `run_results.json`.
- The matching manifest node or source.
- Whether `--no-live` and live mode differed.
- The exact `dbt-diagnostics` command and output format.

Do not open a public issue containing credentials, private keys, account identifiers, sensitive SQL literals, or production data. Use the security-reporting process once `SECURITY.md` is added.

## License

No public license is declared in the current snapshot. A license must be selected and committed before the first public release. Until then, do not assume permission to redistribute or incorporate the code into another project.
