# Design: Live Verification Engine

Status: DRAFT (for review; will iterate)
Branch target: donkey-kong-sandbox
Supersedes: the static `lint` subcommand and `linters/` package (see "Removal").

## 1. Thesis

dbt-diagnostics' differentiator is **live, database-grounded root-cause
analysis** -- not static analysis. Static linting is a crowded space
(sqlfluff, dbt_project_evaluator, dbt's own contract enforcement), and it
operates on a fiction: `manifest.json` describes *this machine's last
compile*, not the live database. Another process, machine, or `--full-refresh`
may have changed state since.

Principle: **manifest.json and run_results.json are hypotheses. The database
is the only truth.** Every assertion the tool makes about state is confirmed
with a live query before it is shown to the user. Offline mode degrades
gracefully: findings are labeled `unverified` with the exact query to confirm.

## 2. Removal and migration

Removed:
- `dbt_diagnostics/linters/` (contract_column_count, duplicate_alias,
  missing_contract_column, type_hazard)
- `cmd_lint` and the `lint` subcommand in `main.py`
- `render_lint` in `renderer.py` and the lint templates
- the corresponding tests

Migrated (NOT lost): the UNION-branch type-coercion insight (Issue 1) moves
into the `contract_violation` classifier in `diagnose`. It runs on the
**compiled SQL that actually failed** and live-confirms the resulting column
type via `DESCRIBE`. Relocation rationale: the contract check already reports
"column X is the wrong type"; the differentiated value is *"which UNION branch
caused it"* -- and that only makes sense post-failure, with a live confirm.

## 3. Architecture: the Live Verification Engine

A reusable probe layer in `enrichers/`. Classifiers declare the probes they
need; the engine batches and runs them over one connection, caches results,
and degrades to `unverified` offline.

Probe library (each = one parameterized, read-only query):
- `object_exists(fqn)` -> SHOW / INFORMATION_SCHEMA
- `distinctness(fqn, grain_cols)` -> COUNT(*) vs COUNT(DISTINCT grain)
- `orphan_fk(child_fqn, fk_cols, parent_fqn, pk_cols)` -> anti-join count + sample
- `duplicate_sample(fqn, key_cols, n)` -> top colliding keys + sample rows
- `column_type(fqn, col)` -> DESCRIBE
- `grant_check(fqn, privilege)` -> existing grants enricher

Contract: a classifier returns `VerificationRequest`s; the engine returns
`VerificationResult`s (status: confirmed / refuted / unverified, plus rows).
Reuses the v0.5.0 connection + lineage-trail plumbing.

All finding objects (VerificationResult, lineage-trail steps, root-cause
groups) are dataclasses with a stable `to_json_dict()`. The public `--json`
output advances to `schema_version: "1.1"`, adding three top-level/per-report
keys: `lineage_trail`, `verification_results`, `root_cause_groups`. The
terminal renderer and the JSON serializer consume the SAME finding objects --
neither is allowed to compute findings independently (no drift).

### 3.1 Cost boundary: $0 metadata vs. warehouse-scanning probes

This is the single most important design axis. The v0.5.0 live layer
(`table_exists`, `describe_table`, SHOW GRANTS via `check_write_access`) is
deliberately **cloud-services-layer metadata only**: $0, no running warehouse
required. Probes split into two tiers:

- **Tier A ($0 metadata):** `object_exists`, `column_type`, `grant_check`.
  Safe to run unconditionally.
- **Tier B (warehouse-scanning):** `distinctness`, `orphan_fk`,
  `duplicate_sample`. These scan data and cost credits. They MUST be gated:
  off by default OR behind a row-count ceiling / `SAMPLE`, with a per-run cap
  on how many Tier-B queries fire and how far upstream the walk goes.

A diagnostic that silently runs an expensive scan on a large table is a trust
violation, not a feature. Tier B is opt-in and bounded.

## 4. First epic: Live Lineage and Root-Cause (use cases 2, 5, 7)

Output: terminal AND JSON. Terminal reuses the v0.5.0 `lineage_trace` Jinja
partial (extended to TestFailureClassifier). JSON (schema_version 1.1) emits
`lineage_trail` (ordered upstream steps + per-step live distinctness),
`verification_results` (probe, status, sampled rows), and `root_cause_groups`
(the N-errors -> 1-cause collapse). The two renderers share finding objects.

Recommended build order (see section 8 for the effort/usefulness basis):
1. UC #5 + the incremental stale-state check (Tier A, low effort, high value).
   These also build the test-failure-finding scaffolding UC #2 needs.
2. UC #2 (flagship), only after the cost ceiling (section 9 Q1) and grain
   source (section 9 Q2) are decided. Tier B; conservative and gated.
3. UC #7, then UNION attribution as an independent delighter.

### 4.1 Upstream grain tracing (UC #2)
Trigger: a `unique`/`relationships` test fails.
1. `duplicate_sample` the failed relation -> the colliding key values.
2. Walk the DAG upstream via `dag_walker`.
3. At each upstream model, run `distinctness` on its *declared* grain.
4. Report the FIRST model whose grain is non-unique as the origin, with the
   live-confirmed colliding values.
Target case: fct_artwork_images.image_id dup -> dim_artworks.source_object_id
fan-out -> dim_artists 30x "Unknown artist" key collision.

Risk to manage: grain resolution (step 3) is inferred. If it is wrong, the
tool points confidently at the wrong model -- worse than silence. Plus it is
Tier B (per-hop warehouse cost). This is why UC #2 is built last and gated.

### 4.2 Single-root-cause aggregator (UC #5)
Trigger: N errors share a class + signature (e.g. `002003 object does not
exist`).
1. Collapse into one group.
2. For "object does not exist," `object_exists` each object **now**.
3. Emit one diagnosis, disambiguated by the live probe:
   - none exist -> "tests ran before materialize; run `dbt build`, not `dbt test`"
   - exist now -> "built by another process / transient; re-run"
   - exist but denied -> route to grant_check
This is why the live probe matters: manifest alone cannot tell these apart.

### 4.3 FK coverage -> live orphan detection (UC #7)
Trigger: a `relationships` test fails (or deep-mode proactive scan).
Replaces static JOIN-vs-YAML parsing (untrustworthy + crowded) with
`orphan_fk`: report orphan count, sampled orphan keys, and the upstream model
that should have produced the missing parents. Grain is free here: the
`relationships` test config already names the parent table and key columns.

## 5. Offline behavior and optional CI gating
- Offline: findings render with status `unverified` plus the copy-paste query,
  in both terminal and JSON.
- `--strict` (opt-in): non-zero exit on any `confirmed` finding. CI consumers
  read the JSON `verification_results`/`root_cause_groups` for the why, not
  scraped terminal text. Default remains interactive (no gate).

## 6. Backlog
- Incremental stale-state detector (Issue 2), reframed as a LIVE check: when an
  incremental model merged 0 rows but its test fails, live-compare row counts /
  watermark to confirm pre-fix rows persist -> recommend `--full-refresh`.
  NOTE: section 8 rates this Low-effort / High-value; strong candidate to
  promote into the first epic alongside UC #5.
- Target-aware materialization opinion (table-on-dev) as guidance, not a linter.

## 7. Open questions
- Probe cost ceiling: cap DISTINCT scans by row count or sample above N?
- Grain source: trust declared PK/uniqueness tests, or also infer from
  `generate_surrogate_key` args in compiled SQL (and live-confirm)?
- How far upstream to walk before giving up (depth limit)?
- Connection reuse across diagnose + enrich without holding it open too long.
- schema_version policy: is 1.x additive-only (new keys, never remove/rename),
  and what's the deprecation path if a finding shape must change?
- UNION attribution wants a real SQL parser (sqlglot). Accept a new dependency,
  or keep it regex-only and narrower?

## 8. Effort vs. usefulness (grounded in the v0.5.0 codebase)

Estimates are based on reading `dag_walker.py`, `enrich.py`, and
`connection.py` -- i.e. what is reusable vs. net-new.

| Feature | Net-new effort | Cost tier | Realistic usefulness |
|---|---|---|---|
| UC #5 object-not-exist aggregator | Low | A ($0) | High / frequent |
| Incremental stale-state (backlog) | Low-Med | A (1 count) | High / silent-killer |
| UNION-branch attribution (Issue 1) | Medium | A | Med-High / rare |
| UC #7 orphan-FK | Med-High | B | Medium |
| UC #2 upstream grain tracing | High | B | Highest ceiling / narrow trigger |

Per-feature notes:

- **UC #5 (Low / High).** Reuses `trace_object_lineage`, `table_exists`, and
  `grouping.py` almost entirely. Net-new = signature grouping + the 3-way
  verdict. Best ROI; stays $0.
- **Incremental stale-state (Low-Med / High).** Mostly `run_results` artifact
  analysis (adapter rows-affected) + `node.config.materialized` + one count
  probe. Directly addresses Issue 2, the costliest silent failure. Under-filed
  in the backlog.
- **UNION attribution (Medium / rare).** Reuses the `contract_violation`
  enrichment + reconciliation path. Effort driver is the parser dependency
  (section 9), not the logic. High value per occurrence, low frequency: a
  delighter.
- **UC #7 (Med-High / Medium).** Grain is free (relationship test config), and
  `dag_walker` gives upstream attribution. But `orphan_fk` is the first
  warehouse-scanning (Tier B) probe and needs a cost guardrail. Increment over
  native dbt is "which rows + where from," since the test already names the FK.
- **UC #2 (High / highest ceiling).** Reuses the trail scaffold, but the hard
  80% is net-new: test-failure findings get no trail today (`enrich_reports`
  only branches on contract_violation/runtime_error); a new Tier-B
  `distinctness` probe per hop; grain resolution; a grain-based disconnect
  verdict. Justified, but built last and gated for the reasons in 4.1.
