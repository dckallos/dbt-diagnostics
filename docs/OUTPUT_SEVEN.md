## 1. Executive verdict.

**[PROVEN] Disposition: ACCEPT WITH MAJOR CHANGES.** `OUTPUT_SIX.md` reaches the correct release-level conclusion—Snowflake must be extracted behind a real dependency boundary before release—but it exposes unstable internals too early, makes `WarehouseBackend` a likely service locator, under-specifies operational failure semantics, and omits package-owned logging. 

The package warrants a **substantial subsystem refactor, not a rewrite**. Preserve the compatibility machinery, classifier knowledge, SQL tracing, artifact fixtures, renderer assets, and current CLI contract. Replace the live-enrichment path, physical-relation handling, evidence model, resolver, grouping, and report assembly behind compatibility projections.

The release architecture should be:

* Snowflake remains the only supported warehouse.
* The backend SPI remains private for the first release.
* The public contracts are the CLI and additive canonical JSON document.
* Snowflake is a statically registered built-in implementing the same private factory and runtime ports a future backend would implement.
* Private entry-point discovery is exercised by an installed fake distribution but is not documented as a stable plugin API.
* Package-owned sanitized JSONL logging is enabled by default.
* Existing and replacement collectors never run for the same request.
* Release requires canonical parity, probe-count parity, installed-wheel conformance, and protected live Snowflake evidence.

The recommended first PR is **W0: freeze current Snowflake output and probe-count baselines**. Do not begin by moving live code.

---

## 2. What is wrong or incomplete in `OUTPUT_SIX.md`.

The current source proves that a protocol declaration alone would not isolate Snowflake. `main._try_enrich()` directly invokes `enrich_reports()` and `LiveObjectProbe`; classifiers contain Snowflake codes, types, parameters, SQL, and remedies; `ColumnTracer` hardcodes the Snowflake dialect; `compat.safe` assigns Snowflake meaning to `query_id`; and grouping/rendering reinterpret mutable reports.

| `OUTPUT_SIX` decision                                | Disposition                     | Failure mode and release scope                                                                                                                                                   | Test that falsifies the design                                                                                                                                                   |
| ---------------------------------------------------- | ------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Snowflake extraction before release                  | **ACCEPT**                      | Mandatory release work. Current generic code is physically and semantically Snowflake-specific.                                                                                  | Import/source audit finds no Snowflake implementation or semantics outside the backend.                                                                                          |
| Large target package split                           | **ACCEPT WITH CHANGES**         | The proposed `api/v1`, `domain`, `engine`, `diagnostics`, and adapter hierarchy is larger than necessary for one backend.                                                        | A sparse fake completes an offline diagnosis through a smaller layout without adapter imports.                                                                                   |
| `WarehouseBackend` bundle                            | **REPLACE**                     | Passed through the engine, it becomes a service locator exposing unrelated capabilities.                                                                                         | A diagnostic rule can access a service unrelated to its declared input.                                                                                                          |
| Small protocols                                      | **ACCEPT WITH CHANGES**         | Keep narrow ports, but inject only the port needed by each stage. Do not pass the backend bundle to rules or resolvers.                                                          | Static typing permits a classifier to open a connection or execute evidence.                                                                                                     |
| Public `api/v1`                                      | **DEFER**                       | The Snowflake extraction has not yet proven stable request, evidence, identity, capability, or remedy semantics.                                                                 | A required parity fix forces a breaking Python-interface change during extraction.                                                                                               |
| Public warehouse plugin entry points                 | **DEFER**                       | A public plugin API creates compatibility and supply-chain obligations before one extraction is complete.                                                                        | The fake plugin requires access to private engine/classifier types.                                                                                                              |
| Entry points as a mechanism                          | **ACCEPT WITH CHANGES**         | Use a private test-only group initially. Python supports selectable installed entry points and lazy `.load()`. ([Python documentation][1])                                       | An unselected plugin module appears in `sys.modules`.                                                                                                                            |
| Same registration for built-in and external backends | **REPLACE**                     | Use the same private `BackendFactory` contract but different registration: explicit static mapping for Snowflake; private entry points only for explicit experimental selection. | An installed distribution named `snowflake` shadows the built-in.                                                                                                                |
| Public adapter conformance kit                       | **DEFER**                       | Keep an internal conformance suite. Publish only after the private SPI survives Snowflake extraction and one independent implementation.                                         | A parity fix requires changing a supposedly stable conformance assertion.                                                                                                        |
| Capability dictionary keyed by strings               | **REPLACE**                     | A frozen dataclass containing a mutable dictionary is not deeply immutable or safely hashable; arbitrary capability IDs become string feature flags.                             | Mutation after construction changes behavior or request planning.                                                                                                                |
| Expressive capability descriptors                    | **ACCEPT WITH CHANGES**         | Use a closed core `ProbeKind` enum plus immutable descriptors. Keep execution status separate from support.                                                                      | A descriptor says “supported” while no executor path exists.                                                                                                                     |
| `LIVE_VERIFICATION_REQUIRED` support state           | **REJECT**                      | It mixes implementation support with whether the current run executed a probe.                                                                                                   | Offline supported request cannot be represented without lying about support.                                                                                                     |
| Relation and identifier models                       | **ACCEPT WITH CHANGES**         | Remove generic namespace-role guesses. Preserve ordered quoted segments and an opaque backend-generated key.                                                                     | `"My.DB"."My.Schema"."Table.1"` fails parse/render round trip. Snowflake permits quoted identifiers containing periods and preserves quoted case. ([Snowflake Documentation][2]) |
| Adapter-response decoder                             | **ACCEPT**                      | Required. dbt documents `adapter_response` as adapter-dependent; fields such as rows affected vary by adapter. ([dbt Developer Hub][3])                                          | Generic artifact code reads `query_id`, `rows_affected`, or bytes processed directly.                                                                                            |
| Error normalizer                                     | **ACCEPT WITH CHANGES**         | Preserve vendor code, SQLSTATE, safe vendor facts, relation, identifier, and location. Raw messages remain internal and redacted.                                                | A normalized error cannot reproduce a useful Snowflake code or subtype.                                                                                                          |
| Evidence status model                                | **ACCEPT WITH CHANGES**         | Add `UNEXECUTED`; record authority independently. `NOT_FOUND` is prohibited for visibility-limited metadata.                                                                     | Offline supported probe serializes as `UNKNOWN` instead of `UNEXECUTED`.                                                                                                         |
| Arbitrary adapter extension evidence payload         | **REJECT** for stable contracts | It recreates `Any` behind a JSON dictionary. Use typed vendor facts or keep opaque data private and excluded from the normative document.                                        | Consumer must inspect arbitrary keys to interpret evidence.                                                                                                                      |
| Execution identity                                   | **ACCEPT WITH CHANGES**         | Use typed provenance and tokenized/redacted identifiers. Distinguish run identity from diagnostic-session identity.                                                              | Privilege evidence gathered under one role confirms a verdict about another role.                                                                                                |
| Semantic probe requests                              | **ACCEPT WITH CHANGES**         | Good direction. Stable request keys, cost declarations, deadlines, cancellation, and authority requirements are missing.                                                         | Equivalent requests execute twice or produce different keys.                                                                                                                     |
| Tuple of `EvidenceProvider`s with `supports()`       | **REPLACE**                     | Runtime scanning by capability string is weak, order-dependent dispatch. Use one backend `EvidenceExecutor` with exhaustive typed dispatch.                                      | Two providers claim the same request and selection depends on tuple order.                                                                                                       |
| Adapter evidence planner                             | **REPLACE**                     | Core owns semantic evidence planning. The backend maps semantic requests to Snowflake operations. An adapter planner consuming classifier internals creates cycle pressure.      | Backend imports classifier or engine modules.                                                                                                                                    |
| Opaque session                                       | **ACCEPT WITH CHANGES**         | Add context-managed ownership, deadlines, cancellation, single-thread rule, and cleanup outcomes.                                                                                | Cursor/connection close failure replaces the primary probe result.                                                                                                               |
| Remedy provider                                      | **ACCEPT WITH CHANGES**         | Backend contributes candidates and commands; core verifies required evidence and alone decides inclusion and final confidence.                                                   | Backend returns a “confirmed” remedy despite failed evidence.                                                                                                                    |
| Active runtime pipeline                              | **ACCEPT WITH CHANGES**         | The proposed order is sound, but pure backend interpretation must occur before rules, and no backend bundle is handed to rules.                                                  | A generic classifier imports or calls Snowflake code.                                                                                                                            |
| Public exporter extension point                      | **DEFER**                       | JSON and terminal are enough. Exporter compatibility would prematurely freeze the canonical model.                                                                               | Adding a field requires a breaking exporter callback change.                                                                                                                     |
| Redaction policy object                              | **ACCEPT WITH CHANGES**         | Redaction is mandatory, not merely boolean inclusion flags. Query text, identifiers, principals, accounts, paths, and exceptions need typed handling.                            | Debug mode can disable redaction.                                                                                                                                                |
| Proposed migration order                             | **REPLACE**                     | It patches legacy live code before establishing parity and the active backend seam. That creates throwaway work and duplicate-probe risk.                                        | A PR lands a new provider while the old runtime call remains active.                                                                                                             |
| W0 characterization baseline                         | **ACCEPT**                      | This must be first. Known bugs are annotated rather than silently blessed.                                                                                                       | Reverting a later extraction PR cannot restore a known public baseline.                                                                                                          |
| Exact parity claim                                   | **ACCEPT WITH CHANGES**         | Compare a compatibility projection, excluding approved correctness fixes and additive provenance/run/log fields.                                                                 | Text matches while evidence states or probe counts differ.                                                                                                                       |
| Databricks/BigQuery comparison                       | **DEFER** from release design   | Useful as pressure-testing, but it should not drive public abstractions or imply support.                                                                                        | Initial API contains unused fields justified only by hypothetical backends.                                                                                                      |
| Operational logging omission                         | **REJECT**                      | Package-owned operational logging is a release requirement and distinct from dbt-log ingestion.                                                                                  | No sanitized log is created or correlated with canonical output.                                                                                                                 |

---

## 3. Corrected release invariants.

1. **[PROVEN] Product support:** The release supports Snowflake only. No documentation, metadata, command, or adapter listing implies Databricks, BigQuery, or other support.

2. **Private backend boundary:** The initial backend SPI, entry-point group, conformance helpers, rule seams, and log-consumer seams are private.

3. **Active composition:** The CLI selects one `BackendFactory`; its pure interpreter services and optional live executor are passed into the active pipeline.

4. **No service location:** Diagnostic rules never receive a `BackendServices` bundle, session factory, registry, or connector.

5. **Physical isolation:** Generic modules import no `backends.snowflake`, `snowflake.connector`, Snowflake probe, tuple decoder, or remedy implementation.

6. **Semantic isolation:** Generic modules contain no Snowflake codes, SQL, tuple positions, profile fields, role semantics, identifier rules, types, parameter names, functions, or generated commands.

7. **Artifact neutrality:** Generic artifact views preserve raw adapter-response fields without assigning adapter meaning.

8. **Relation identity:** Core never splits physical names on `"."`, strips quotes, or uppercases names. Equality uses a versioned opaque canonical key.

9. **Evidence ontology:** `CONFIRMED`, `NOT_FOUND`, `NOT_VISIBLE`, `FAILED`, `UNSUPPORTED`, `UNKNOWN`, and `UNEXECUTED` are distinct.

10. **Authority:** `NOT_FOUND` is emitted only when the observer has recorded authoritative visibility. A normal identity-scoped `SHOW` result cannot prove physical absence.

11. **Identity consistency:** Evidence records the identity that observed it. Evidence from different identities cannot jointly confirm a verdict unless the resolver explicitly models the relationship.

12. **Execution correlation:** Exact statement ID is attempted first. Every fallback records its correlation quality.

13. **Stable identities:** Run, report, observation, request, evidence, probe execution, relation, and group IDs have documented deterministic or random-generation rules.

14. **Probe uniqueness:** One stable request key maps to at most one execution per diagnosis. Reused evidence does not generate a second probe.

15. **No dual migration path:** A new provider and its legacy collector never execute for the same finding.

16. **Lifecycle:** One live session is owned by one diagnostic invocation and one thread. Deadlines, cancellation, cursor closure, connection closure, and cleanup failures are explicit.

17. **Cost boundary:** Tier A means metadata-only, not free. Tier B remains opt-in, bounded, budgeted, and rejected before executor invocation.

18. **Offline purity:** Offline mode imports no connector, parses no profile, loads no dotenv file, performs no credential discovery, and issues no warehouse call.

19. **Canonical output:** One immutable, versioned, JSON-compatible document is normative. Existing schema-major-1 keys remain additive-only.

20. **Terminal projection:** Terminal rendering performs formatting and detail omission only. It does not classify, group, resolve, select remedies, or probe.

21. **Operational logs:** One sanitized JSONL file is produced by default per invocation, correlated by run ID, without contaminating stdout.

22. **Redaction:** Credentials, keys, tokens, raw SQL, literals, query text, object names, principals, roles, accounts, and absolute paths are excluded or tokenized by default.

23. **Release proof:** Golden canonical parity, deterministic ordering, probe counts, private backend conformance, installed-wheel tests, and protected live Snowflake verification all pass.

24. **Fixture integrity:** Real artifacts and connector rows are provenance-recorded. No fabricated artifact or recorded connector-row fixture is accepted.

25. **Scope guard:** No general static SQL linting is added. The grain-declaration consistency check remains the sole proactive static exception.

26. **Process:** One issue maps to one PR; docs follow merged code; all repository-authored material remains ASCII-only.

---

## 4. Current implementation constraints and baseline checks actually run.

### Execution environment

| Check                                     | Result                                                             |
| ----------------------------------------- | ------------------------------------------------------------------ |
| Writable files under `/mnt/data`          | Only `OUTPUT_ONE.md` through `OUTPUT_SIX.md` and `format_files.sh` |
| Search for `.git` checkout                | None found                                                         |
| Search for `dbt_diagnostics/` source tree | None found                                                         |
| Python runtime                            | Python 3.13.5                                                      |
| Package compile/import/test/build         | **Not run**—there is no executable checkout                        |
| Snowflake live checks                     | Not run; no credentials assumed                                    |
| GitHub writes                             | None                                                               |
| Open PRs                                  | None returned by the tracker query                                 |
| Generated contract sketch                 | `py_compile` passed                                                |
| Generated CI YAML                         | Parsed successfully with PyYAML                                    |

**[PROVEN]** I did not run `pytest`, `compileall` against the package, `python -m build`, wheel installation, or CLI smoke tests. The Markdown snapshot is authoritative source material but not an executable repository.

The default GitHub branch is `donkey-kong-sandbox`. The current live epic and most release blockers are assigned to milestone 1; #58 and #33 are not, despite being release dependencies.

### Python support claim

`requires-python = ">=3.11"` currently claims every future Python 3 release. Python 3.11 through 3.14 are supported releases in June 2026, while 3.15 remains prerelease. Narrow the first release to:

```toml
requires-python = ">=3.11,<3.15"
```

and test 3.11, 3.12, 3.13, and 3.14. Reopen the upper bound only when a new version is added to CI. ([Python Developer's Guide][4])

### Commands that must pass once a checkout is mounted

```bash
python -m compileall -q dbt_diagnostics
pytest -q -m unit
pytest -q -m "contract or robustness"
pytest -q -m property
pytest -q -m e2e
pytest -q -m "not live and not chaos"
coverage run --branch -m pytest -q -m "not live and not chaos"
coverage report --fail-under=85
python -m build
twine check dist/*
python scripts/ci/check_dist_contents.py dist
```

Minimum additional material needed: the actual checkout, omitted `real_*` fixtures, schema cache and provenance, all tests/templates/scripts, and any provenance-recorded scrubbed Snowflake rows already held by the project.

---

## 5. Target package layout.

This is intentionally smaller than `OUTPUT_SIX`:

```text
dbt_diagnostics/
  __init__.py
  __main__.py
  main.py

  core/
    json_values.py
    ids.py
    capabilities.py
    relations.py
    errors.py
    observations.py
    requests.py
    evidence.py
    resolution.py
    remedies.py
    report.py
    ports.py

  artifacts/
    context.py
    manifest_view.py
    run_results_view.py
    catalog_view.py
    indexes.py

  engine/
    pipeline.py
    planner.py
    collector.py
    resolver.py
    assembler.py

  classifiers/
    base.py
    registry.py
    compilation_error.py
    contract_violation.py
    runtime_error.py
    timeout_error.py
    data_error.py
    schema_change_error.py
    test_failure.py

  tracers/
    dag_walker.py
    column_tracer.py
    diff_tracer.py
    snippet.py

  backends/
    registry.py
    snowflake/
      factory.py
      capabilities.py
      identifiers.py
      artifact_response.py
      errors.py
      profile.py
      connection.py
      evidence.py
      query_history.py
      identity.py
      privileges.py
      session_context.py
      remedies.py

  compat/
    consumed_paths.py
    safe.py
    schema_model.py
    path_resolver.py

  opslog/
    config.py
    events.py
    redaction.py
    writer.py
    setup.py

  renderer.py
  templates/
```

Key choices:

* Retain `classifiers/`, `tracers/`, and `compat/`; migrate their inputs rather than renaming everything.
* Do not create a public `api/v1`.
* Put stable internal values in `core/`.
* Put orchestration in `engine/`.
* Keep all Snowflake implementation in one subtree.
* Keep operational logging independent of adapters and rendering.
* Keep `main.py` as the compatibility entry point and composition root until a later CLI-only refactor proves valuable.

---

## 6. Import graph and cycle proof.

### Allowed direction

```text
core
  imports: standard library only

compat
  imports: standard library only

artifacts
  imports: core + compat

tracers
  imports: core + artifacts

classifiers
  imports: core + artifacts + tracers

engine
  imports: core + artifacts + classifiers + tracers
  never imports a concrete backend

backends.snowflake
  imports: core
  may import optional connector only in connection/session implementation
  never imports engine, classifiers, renderer, or opslog

opslog
  imports: standard library + core.ids + core.json_values
  never imports a backend

renderer
  imports: core.report only

backends.registry
  imports: core.ports + importlib.metadata
  never imports backends.snowflake

main
  imports: registry + explicit built-in factory + artifacts + engine
           + opslog + renderer
```

### Composition root

`main` builds the static built-in mapping:

```python
builtins = {"snowflake": SnowflakeBackendFactory()}
factory = registry.select(...)
services = factory.create()
ports = ports_from_backend(services)
```

It then passes:

* pure decoder/normalizer/codec/dialect ports to artifact interpretation;
* an optional session and evidence executor to the collector;
* a remedy-candidate port to the resolver.

No classifier receives `BackendServices`.

### Cycle proof

Assign each module a dependency rank:

| Rank | Modules                                     |
| ---: | ------------------------------------------- |
|    0 | `core`, `compat`                            |
|    1 | `artifacts`, `opslog`                       |
|    2 | `tracers`, concrete backend implementations |
|    3 | `classifiers`                               |
|    4 | `engine`                                    |
|    5 | `renderer`, `backends.registry`             |
|    6 | `main`                                      |

Every static edge points from a higher rank to a lower rank, except concrete backends and classifiers are intentionally siblings with **no edge in either direction**. The composition root is the only module allowed to know both.

Automated checks must reject:

```text
core                -> artifacts, classifiers, engine, backends, renderer
artifacts           -> classifiers, engine, concrete backends
classifiers         -> concrete backends, engine
engine              -> backends.snowflake
backends.snowflake  -> engine, classifiers, renderer, opslog
renderer            -> classifiers, engine, backends
opslog              -> artifacts, classifiers, engine, backends, renderer
```

The most likely cycle otherwise would be:

```text
classifier -> backend planner -> classifier observation
```

That is why adapter-specific planning is rejected. Core creates semantic requests; the backend executor translates them to Snowflake operations.

---

## 7. Public/private API decision.

| Surface                                            | Initial release                                             |
| -------------------------------------------------- | ----------------------------------------------------------- |
| CLI commands and flags                             | **PUBLIC**                                                  |
| Canonical JSON schema major 1                      | **PUBLIC, additive-only**                                   |
| Terminal wording/layout                            | Presentation contract, not semantic API                     |
| Existing documented root-package imports           | Preserve where practical; explicitly provisional before 1.0 |
| Backend factory, ports, requests, evidence classes | **PRIVATE**                                                 |
| Backend entry-point group                          | **PRIVATE / experimental test seam**                        |
| Adapter conformance kit                            | **PRIVATE**                                                 |
| Diagnostic-rule plugin system                      | Not exposed                                                 |
| Evidence-source plugin system                      | Not exposed                                                 |
| Exporter plugin system                             | Not exposed                                                 |
| Operational-log consumer SPI                       | Not exposed                                                 |
| JSONL operational event schema                     | Versioned but not yet a public consumer API                 |

### Registration and selection

Built-in Snowflake is registered statically. External candidates use a private entry-point group such as:

```text
dbt_diagnostics._warehouse_backends_v0
```

The standard library can enumerate entry points by group and name without loading their modules, then explicitly call `.load()` only for the selected item. ([Python documentation][1])

Rules:

1. `--warehouse snowflake` or the offline default selects the built-in directly.
2. The name `snowflake` is reserved and cannot be shadowed.
3. External discovery is disabled unless an explicit private experimental switch is set.
4. Unselected entry points are never imported.
5. Duplicate external names fail selection before import.
6. The selected plugin’s load failure, dependency failure, or API mismatch is a configuration failure.
7. There is no fallback to Snowflake after an explicit external selection fails.
8. Backend names use lowercase ASCII and a strict length/character rule.
9. `adapters list` reads metadata without importing plugin code.
10. Distribution name and version are recorded in the run document and sanitized operational log.

This preserves the real dependency boundary while avoiding premature public compatibility.

### Compatibility and deprecation

* Canonical JSON remains additive within major version 1.
* New canonical fields include `run_id`, backend metadata, typed evidence, final resolution, graph edges, redaction metadata, and operational-log summary.
* Existing top-level and per-report fields remain as a compatibility projection.
* `--no-live` remains accepted for at least two minor releases after offline becomes the default.
* No compatibility promise is made for `dbt_diagnostics.core`, `backends`, or the private entry-point group.
* A public backend API requires a future ADR, two independent implementations, and explicit semantic-version policy.

---

## 8. Complete backend and evidence contracts.

The full standard-library-only target sketch compiles under the available Python runtime:

[Private backend contract sketch](sandbox:/mnt/data/backend_contracts.py)

### Core evidence states

```python
class EvidenceStatus(StrEnum):
    CONFIRMED = "confirmed"
    NOT_FOUND = "not_found"
    NOT_VISIBLE = "not_visible"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"
    UNEXECUTED = "unexecuted"
```

`NOT_FOUND` additionally requires `EvidenceAuthority.AUTHORITATIVE`. An identity-scoped metadata result may return `NOT_VISIBLE` or `UNKNOWN`, never authoritative absence.

### Immutable capabilities

```python
@dataclass(frozen=True, slots=True)
class CapabilityDescriptor:
    kind: ProbeKind
    support: CapabilitySupport
    tier: ProbeTier
    compute: ComputeRequirement
    billing: BillingSemantics
    authority: EvidenceAuthority
    notes: tuple[str, ...] = ()
```

`CapabilitySet` stores a tuple, not a dictionary. Duplicate or missing core capability descriptors are invariant violations.

### Relation and identifier model

```python
@dataclass(frozen=True, slots=True)
class IdentifierPart:
    value: str
    quoted: bool
    original: str

@dataclass(frozen=True, slots=True)
class RelationRef:
    backend_name: str
    codec_version: int
    parts: tuple[IdentifierPart, ...]
    raw: str
    canonical_key: str
```

The canonical key is not a Python hash and never depends on process hash randomization. The Snowflake codec incorporates:

* codec version;
* part count;
* quoted flag;
* UTF-8 byte length;
* exact value.

It therefore distinguishes:

```text
FOO
"FOO"
"Foo"
"My.DB"."Schema"."Table.1"
```

### Adapter-response decoding

Generic `RunResultView` exposes:

```python
RawAdapterResponse(fields=JsonObject(...))
```

Snowflake code returns:

```python
AdapterExecutionMetadata(
    statement_id="01b...",
    rows_affected=0,
    bytes_processed=None,
    raw_fields=raw.fields,
)
```

No generic accessor is named `result_query_id`.

### Stable execution identity

```python
@dataclass(frozen=True, slots=True)
class ExecutionIdentity:
    principal_kind: str | None
    principal_token: str | None
    user_token: str | None
    role_token: str | None
    group_tokens: tuple[str, ...]
    compute_token: str | None
    provenance: IdentityProvenance
    status: EvidenceStatus
    vendor_facts: tuple[VendorFact, ...] = ()
```

Raw names may be held transiently inside Snowflake provider code but are converted to per-run tokens before canonical or operational output.

### Stable keys

* `run_id`: UUID4, injectable in tests.
* `report_id`: deterministic from artifact kind, unique ID, and occurrence number.
* Duplicate artifact IDs are preserved as separate occurrence keys; no silent last-write-wins.
* `request_key`: `rq1:` plus SHA-256 of canonical typed request JSON.
* `evidence_id`: `ev1:<request digest>:<execution attempt>`.
* `probe_execution_id`: random per actual executor call.
* Reused cached evidence retains its original evidence ID and does not create another probe ID.
* `group_id`: deterministic digest of sorted member report IDs and structured signature.

### Probe requests

```python
ProbeRequest = (
    InspectRelationRequest
    | InspectColumnsRequest
    | QueryHistoryRequest
    | RecoverExecutionIdentityRequest
    | InspectPrivilegesRequest
    | InspectSessionContextRequest
)
```

Session settings are semantic:

```python
SemanticSetting.STATEMENT_TIMEOUT
SemanticSetting.TIMEZONE
SemanticSetting.TIMESTAMP_TYPE_BEHAVIOR
```

Only Snowflake maps these to parameter names.

### Request de-duplication and cost gating

```python
def collect_requests(
    requests: tuple[ProbeRequest, ...],
    *,
    capabilities: CapabilitySet,
    executor: EvidenceExecutor | None,
    session: WarehouseSession | None,
    context: ProbeExecutionContext,
) -> tuple[EvidenceRecord, ...]:
    cache: dict[str, EvidenceRecord] = {}
    ordered: list[EvidenceRecord] = []
    budget_state = BudgetState()

    for request in requests:
        key = stable_request_key(request)

        existing = cache.get(key.value)
        if existing is not None:
            ordered.append(existing)
            continue

        capability = capabilities.for_kind(probe_kind(request))
        authorization = authorize_probe(
            capability,
            context.budget,
            budget_state,
        )

        if authorization.status is AuthorizationStatus.UNSUPPORTED:
            record = unexecuted_record(
                request=request,
                status=EvidenceStatus.UNSUPPORTED,
                reason=authorization.reason,
                context=context,
                capability=capability,
            )
        elif authorization.status is AuthorizationStatus.REJECTED_BY_POLICY:
            record = unexecuted_record(
                request=request,
                status=EvidenceStatus.UNEXECUTED,
                reason=authorization.reason,
                context=context,
                capability=capability,
            )
        elif executor is None or session is None:
            record = unexecuted_record(
                request=request,
                status=EvidenceStatus.UNEXECUTED,
                reason="no live session",
                context=context,
                capability=capability,
            )
        else:
            record = executor.collect(request, session, context)

        cache[key.value] = record
        ordered.append(record)

    return tuple(ordered)
```

The real implementation must catch only documented backend/connector failures. Programming invariant failures are not converted into warehouse facts.

### Backend services and ports

```python
@dataclass(frozen=True, slots=True)
class BackendServices:
    descriptor: BackendDescriptor
    capabilities: CapabilitySet
    relation_codec: RelationCodec
    adapter_response_decoder: AdapterResponseDecoder
    error_normalizer: ErrorNormalizer
    sqlglot_dialect: str
    session_factory: SessionFactory | None
    evidence_executor: EvidenceExecutor | None
    remedy_provider: RemedyCandidateProvider
```

This container exists only at composition. It is destructured into narrow `PipelinePorts`.

### Session and cancellation

* The generic session has no `execute(sql)`.
* `EvidenceExecutor.collect()` owns backend APIs, SQL construction, row decoding, timeout behavior, and cursor cleanup.
* `SessionFactory.open()` returns a context manager.
* Each request receives a deadline and probe execution ID.
* Snowflake uses connector login/network/socket timeouts and per-call timeout where supported.
* Cancellation uses the request’s probe execution ID or Snowflake query ID.
* Cleanup failure is logged and attached as secondary evidence; it does not replace the primary result.
* Sessions are single-thread-owned in the initial release. No parallel probe execution is allowed.

The Snowflake connector exposes DB-API behavior, timeouts, cursor/connection close operations, and query cancellation, but these remain implementation details behind the backend. ([Snowflake Documentation][5])

### Query-history correlation

Order:

1. exact adapter statement ID;
2. future attested marker;
3. query tag;
4. bounded fingerprint/time window;
5. no correlation.

Every result includes `CorrelationQuality`. Snowflake failure states must use documented values such as `FAILED_WITH_ERROR` and `FAILED_WITH_INCIDENT`, not the current `FAIL` filter. ([Snowflake Documentation][6])

### Privilege inspection

`PrivilegeEvidence` distinguishes:

* database usage;
* schema usage;
* object read privilege;
* schema create privilege;
* direct grants;
* inherited role paths;
* query failure;
* visibility authority.

Snowflake `SHOW GRANTS` exposes explicitly granted privileges and role relationships, but the provider must establish and record the role hierarchy it actually inspected. ([Snowflake Documentation][7])

### Session context

A current diagnostic session parameter does not prove the failed run’s historical parameter value. Each `SessionSettingValue` therefore records its observer identity and source level. The resolver may use it as current context, not as confirmed historical cause, unless correlated evidence establishes the failing session.

### Remedy ownership

Backend candidates include structured steps and a **maximum confidence**, never final confidence. Core accepts a candidate only when all required evidence IDs exist with sufficient status and authority.

### SQLGlot dialect injection

`ColumnTracer` is constructed with:

```python
ColumnTracer(
    models_dir=models_dir,
    compiled_dir=compiled_dir,
    dialect=ports.sqlglot_dialect,
)
```

No generic function contains `dialect="snowflake"`.

### Failure taxonomy

| Failure                                            | Representation                                | Continue?       |
| -------------------------------------------------- | --------------------------------------------- | --------------- |
| Bad CLI/config                                     | `configuration_failed` run outcome; exit 2    | No diagnosis    |
| Backend name collision/API mismatch/import failure | Structured backend-load failure; exit 2       | No fallback     |
| Missing/corrupt required artifact                  | Artifact failure; exit 2                      | No              |
| Optional artifact malformed                        | Artifact evidence `FAILED`/`UNKNOWN`          | Yes             |
| Unsupported capability                             | Evidence `UNSUPPORTED`                        | Yes             |
| Offline supported request                          | Evidence `UNEXECUTED`                         | Yes             |
| Probe timeout/cancellation                         | Evidence `FAILED` with reason                 | Yes             |
| Visibility-limited negative                        | Evidence `NOT_VISIBLE` or `UNKNOWN`           | Yes             |
| Cursor/connection cleanup failure                  | Secondary cleanup event/fact                  | Yes where safe  |
| Report invariant violation                         | Internal failure, sanitized stderr/log        | No false report |
| Operational-log failure                            | Logging status `degraded`; one stderr warning | Yes             |

---

## 9. Six end-to-end execution walkthroughs.

### 1. Snowflake object unavailable or not authorized

1. `RunResultView` preserves the raw adapter response.
2. Snowflake decoder extracts statement ID.
3. Snowflake normalizer produces `ObjectUnavailableObservation` with a parsed `RelationRef`; code `002003` stays in vendor facts.
4. Core plans relation inspection, exact query history, execution identity, and read-privilege requests.
5. Offline mode emits `UNEXECUTED` records.
6. Live Snowflake provider inspects relation kind and visibility under a recorded identity.
7. An empty identity-scoped result becomes `NOT_VISIBLE`, not `NOT_FOUND`.
8. `NOT_FOUND` is possible only in a live-tested owned namespace with authoritative visibility.
9. Privilege evidence is not combined with relation evidence from another identity.
10. Resolver selects one of: confirmed present-now, authoritative absent, not visible, failed, or unverified.
11. Snowflake remedy candidates supply properly quoted grant/manual commands.
12. Core caps confidence and assembles one canonical group.
13. Terminal and JSON project the same resolution.

### 2. Snowflake invalid identifier

1. Normalizer extracts the quoted identifier and location.
2. Artifact graph identifies only reachable candidate relations.
3. Column-name presence in an ancestor is a hypothesis, not proven provenance.
4. Core plans column inspection for the specific reachable relations.
5. Snowflake returns exact column descriptors or explicit failed/not-visible states.
6. Resolver distinguishes typo, quoted-case mismatch, possible drift, confirmed missing column, and unverified state.
7. Similar-column suggestions are computed from confirmed columns only.
8. No global manifest relation or sibling path can become the origin.
9. Canonical output includes graph edges, evidence IDs, and confidence.

### 3. Snowflake timeout or session-setting diagnosis

1. Normalizer creates `TimeoutObservation` without mentioning Snowflake parameters.
2. Core plans exact query history, execution identity, and `STATEMENT_TIMEOUT` semantic context.
3. Snowflake maps that semantic request to relevant Snowflake settings and levels.
4. Query-history evidence describes the failed statement.
5. Current diagnostic-session settings are explicitly identified as current context.
6. Unless the failed session’s setting is recovered, the resolver does not claim it caused the historical timeout.
7. Snowflake remedy candidates may suggest a dbt change, optimization, or warehouse command.
8. Core includes only candidates supported by evidence and never increases confidence based solely on current settings.

### 4. Offline artifact-only diagnosis

1. CLI defaults to backend name `snowflake` for pure interpretation.
2. It loads no dotenv module, profile, connector, or credentials.
3. Artifact views are built once.
4. Snowflake pure decoder/normalizer/codec modules load without connector imports.
5. Classifiers produce observations and core plans semantic requests.
6. Every supported live request becomes `UNEXECUTED`; unsupported remains `UNSUPPORTED`.
7. Resolver emits unverified hypotheses and sanitized manual confirmation steps.
8. Canonical document and operational log share a run ID.
9. JSON stdout contains only the document.

### 5. Unsupported capability on a fake future backend

1. Test composition selects the sparse fake.
2. It normalizes artifacts but declares `SESSION_CONTEXT` unsupported.
3. Core plans a session-context request for a timeout observation.
4. Cost/capability gating creates `UNSUPPORTED` evidence without calling the fake executor.
5. Resolver retains the timeout observation but does not generate setting-specific confidence or remedies.
6. Conformance asserts zero executor calls for that request.
7. The canonical document remains valid and deterministic.

### 6. Failed adapter/plugin loading

1. User explicitly selects an experimental private backend name.
2. Registry enumerates only matching entry-point metadata.
3. Duplicate names fail before import.
4. The selected entry point alone is loaded.
5. Import error, dependency conflict, non-factory object, or private API mismatch becomes a structured configuration failure.
6. The registry does not fall back to Snowflake.
7. In `--json`, stdout contains a minimal canonical run document with `configuration_failed`; stderr remains concise.
8. The operational log records only distribution metadata, safe exception class/category, and run ID.
9. No artifact diagnosis or warehouse call occurs.

---

## 10. Operational logging ADR.

### ADR: sanitized package-owned operational logs

**Status:** Accepted for the target release architecture.

### Goals

* Record how dbt-diagnostics itself loaded artifacts, selected a backend, planned evidence, ran probes, degraded, resolved findings, and assembled output.
* Correlate all operational events, canonical reports, and live probes.
* Preserve valid JSON stdout.
* Make support logs useful without collecting sensitive warehouse or project data.
* Continue diagnosis if logging fails.

### Non-goals

* Consuming dbt’s own event/log protocol.
* Capturing connector log streams.
* Recording raw SQL, query text, profile values, or warehouse identifiers.
* Providing a public log-consumer plugin API.

Issue #45 is specifically the separate dbt structured-event ingestion spike and remains independent.

### Threat model

The log facility assumes:

* profile values can contain passwords, private-key paths, OAuth tokens, account identifiers, users, roles, databases, schemas, and warehouses;
* SQL can contain literals and sensitive business data;
* object/principal names can themselves be sensitive;
* exception strings and tracebacks may echo connector arguments or query text;
* absolute paths reveal usernames and project structure;
* multiple concurrent processes can corrupt a shared rotating file.

Python’s logging cookbook explicitly warns that separate processes writing the same file can garble output and break rotation; standard logging does not serialize a shared file across processes. The design therefore gives every process/run a unique file. ([Python documentation][8])

### Default behavior

| Decision              | Value                                                    |
| --------------------- | -------------------------------------------------------- |
| File log by default   | **Yes**                                                  |
| Format                | JSON Lines only                                          |
| Default level         | INFO                                                     |
| File count            | One unique base file per invocation                      |
| Default size rotation | 5 MiB, two backups                                       |
| Retention             | 14 days and maximum 100 run groups, best effort          |
| Project-local default | No                                                       |
| Standalone behavior   | Same user-state location                                 |
| Failure behavior      | One sanitized stderr warning; continue with no-op writer |

The standard library provides size-based rotating handlers and no-op handlers; no third-party logging dependency is justified. ([Python documentation][9])

### Default locations

These are package decisions:

```text
Linux:
  $XDG_STATE_HOME/dbt-diagnostics/logs
  fallback ~/.local/state/dbt-diagnostics/logs

macOS:
  ~/Library/Logs/dbt-diagnostics

Windows:
  %LOCALAPPDATA%\\dbt-diagnostics\\Logs
```

`DBT_DIAGNOSTICS_STATE_DIR` overrides the base. Explicit `--log-dir` or `--log-file` may select a project-local destination.

### File naming and concurrency

```text
20260620T194512.123456Z_18421_7d37c34e.jsonl
```

The name contains UTC time, PID, and a short run-ID component. Processes never share a base file. Cleanup races tolerate `FileNotFoundError` and never touch the current run’s files.

### CLI controls

```text
--log-level {DEBUG,INFO,WARNING,ERROR}
--log-dir PATH
--log-file PATH
--no-file-log
```

`--log-dir` and `--log-file` are mutually exclusive.

Precedence:

```text
CLI > explicit config > environment > defaults
```

Malformed explicit configuration is an error rather than a silent fallback.

### stdout, stderr, and file separation

* stdout: terminal report or canonical JSON only;
* stderr: concise actionable CLI warnings/errors only;
* operational events: file only;
* connector loggers: not attached to the package file handler.

`--json` stdout must remain parseable even when logging setup, backend loading, or a probe fails.

### Correlation IDs

Every invocation creates one UUID4 `run_id`. The canonical document and every event include it. Events may also include:

* `report_id`
* `observation_id`
* `request_key`
* `evidence_id`
* `probe_execution_id`
* `group_id`

### Event schema

```json
{
  "schema_version": "1.0",
  "timestamp": "2026-06-20T19:45:12.123456Z",
  "sequence": 17,
  "level": "INFO",
  "event": "probe.completed",
  "component": "engine.collector",
  "phase": "collect",
  "run_id": "7d37c34e-37aa-45e0-b85a-5f8ceefb868d",
  "report_id": "rp1:...",
  "request_key": "rq1:...",
  "probe_execution_id": "pe1:...",
  "status": "not_visible",
  "duration_ms": 84,
  "fields": {
    "backend": "snowflake",
    "probe_kind": "relation",
    "relation_token": "obj_a91d4f2c",
    "authority": "identity_scoped"
  }
}
```

The event schema is additive within `1.x`; consumers ignore unknown fields and events. It is versioned separately from canonical report JSON and is not yet a public plugin contract.

### Redaction

Never log:

* passwords, tokens, private keys, passphrases, profile values;
* raw SQL, query text, SQL literals, compiled SQL;
* raw account, object, principal, user, role, warehouse, database, or schema names;
* absolute paths;
* raw connector exception strings or tracebacks.

Correlation-sensitive values use an in-memory per-run HMAC key:

```text
object -> obj_<digest>
principal -> principal_<digest>
account -> account_<digest>
SQL fingerprint -> sql_<digest>
```

Because the key is discarded after the run, tokens cannot be correlated across runs.

Debug level never disables redaction.

### Connector and adapter exceptions

Represent exceptions as:

```text
exception_class
normalized_category
vendor_code
sqlstate
retryable
phase
safe_message_code
```

Do not call `logger.exception()` with an untrusted connector exception. Do not copy `str(exc)` into operational or canonical output.

### Permissions

* Create default directories with mode `0700` on POSIX.
* Create new files with mode `0600`.
* Do not follow symlinks where the platform exposes a safe `O_NOFOLLOW` path.
* Use exclusive creation for generated default filenames.
* Apply best-effort platform ACL behavior on Windows and test only what the runner can prove.

### Failure degradation

At startup or mid-run write failure:

1. disable the file handler;
2. emit one sanitized stderr warning;
3. replace it with a no-op writer;
4. set canonical `operational_log.status = "degraded"`;
5. continue diagnosis;
6. never change evidence or resolution confidence.

### Canonical report relationship

Additive fields:

```json
{
  "run_id": "...",
  "operational_log": {
    "enabled": true,
    "status": "active",
    "reference": "user-state://dbt-diagnostics/logs/20260620...jsonl"
  }
}
```

Only a basename-style reference appears; no absolute path.

### Test plan

* default creation;
* explicit directory and file;
* disabled logging;
* level/config precedence;
* JSON stdout purity;
* credential, key, token, SQL literal, query text, object, principal, account, path, and exception redaction;
* POSIX permissions;
* unique files from concurrent processes;
* rotation and retention;
* startup and mid-run write failure;
* connector exception sanitization;
* run/report/request/probe correlation;
* event-schema serialization;
* no connector logger capture.

### Implementation sequence

1. Run-ID type and injection.
2. Redaction primitives and adversarial tests.
3. Event model and JSONL encoder.
4. Secure unique-file writer, rotation, and retention.
5. Configuration and CLI controls.
6. Composition-root and pipeline instrumentation.
7. Canonical report summary/reference.
8. Concurrency, failure, and e2e tests.
9. ADR and README.

The complete tracker draft is included in the issue packet:

[Tracker issue packet](sandbox:/mnt/data/tracker_issue_packet.md)

---

## 11. Growth-extension decisions.

| Axis                              | Initial-release disposition | Reason                                                                               |
| --------------------------------- | --------------------------- | ------------------------------------------------------------------------------------ |
| Warehouse backends                | **INTERNAL SEAM ONLY**      | Mandatory architecture seam, but public compatibility is premature.                  |
| Diagnostic rules                  | **INTERNAL SEAM ONLY**      | Observation and conflict semantics have not stabilized.                              |
| Evidence sources                  | **INTERNAL SEAM ONLY**      | Needed internally for artifacts/live evidence; no third-party discovery.             |
| Artifact sources                  | **INTERNAL SEAM ONLY**      | `LocalArtifactSource` only; archives/cloud retrieval deferred.                       |
| Execution-correlation strategies  | **INTERNAL SEAM ONLY**      | Exact/fallback fidelity semantics are still being proven.                            |
| Cost policies                     | **INTERNAL SEAM ONLY**      | One built-in policy; public policy plugins would create safety obligations.          |
| Remedy providers                  | **INTERNAL SEAM ONLY**      | Snowflake extraction needs the seam, but core confidence rules must stabilize first. |
| Output exporters                  | **DEFER**                   | JSON plus terminal are sufficient.                                                   |
| Redaction policies                | **INTERNAL SEAM ONLY**      | Redaction is a security invariant, not an arbitrary third-party hook.                |
| Adapter conformance kit           | **INTERNAL SEAM ONLY**      | Run against Snowflake and fake distribution, publish later.                          |
| Package operational-log consumers | **DEFER**                   | JSONL is readable, but no stable consumer API or event subscription system.          |
| dbt structured-log ingestion      | **DEFER pending #45 spike** | Independent evidence-source research.                                                |
| General static SQL lint rules     | **REJECT**                  | Violates project thesis.                                                             |
| Ungated Tier-B probes             | **REJECT**                  | Violates cost/trust boundary.                                                        |

A public extension point should require all of:

1. two independent implementations;
2. stable typed contracts;
3. collision/version/failure semantics;
4. conformance tests;
5. security and compatibility policy;
6. explicit deprecation rules.

No current axis meets that threshold.

---

## 12. Test architecture and coverage matrix.

### Core tests

| Test                                            | Defect it catches                                         |
| ----------------------------------------------- | --------------------------------------------------------- |
| Error-normalizer decision tables                | Wrong vendor code/category or dropped vendor evidence     |
| Observation construction                        | Classifier embeds a conclusion rather than an observation |
| Evidence-state precedence                       | Failed/unknown/not-visible promoted to confirmed absence  |
| Authority/identity decision tables              | Evidence from different identities improperly combined    |
| Resolver truth tables                           | Confidence or remedy selected without required evidence   |
| Cost authorization                              | Tier-B executor called without explicit budget            |
| Stable request-key tests                        | Equivalent requests execute twice                         |
| Evidence-ID/cache tests                         | Reused evidence appears as a second probe                 |
| Lineage graph linear/branch/diamond/cycle tests | Sibling adjacency or invented edges                       |
| Canonical assembler uniqueness                  | Report appears twice or disappears from grouping          |
| Deterministic ordering                          | Golden JSON changes with dictionary/set iteration         |
| Redaction properties                            | Sensitive nested values survive output                    |
| Operational event construction                  | Event lacks correlation or includes forbidden values      |

### Artifact contract tests

| Test                                        | Defect it catches                                         |
| ------------------------------------------- | --------------------------------------------------------- |
| Every committed `real_*` artifact           | Parser behavior diverges from real dbt output             |
| Malformed/unknown versions                  | Crash or false support claim                              |
| Mixed-version pairs                         | Approximate cross-artifact correlation presented as exact |
| Raw adapter-response round trip             | Vendor fields lost before backend decoding                |
| Duplicate result/node IDs                   | Silent last-write-wins                                    |
| Consumed-path registry completeness         | Runtime reads fields absent from the compatibility gate   |
| Field type/nullability/requiredness changes | Presence-only schema gate misses semantic break           |
| One context/index construction              | Repeated O(n) scans and inconsistent views                |

Duplicate policy:

```text
artifact result key = (unique_id, occurrence_index)
```

A lookup requiring uniqueness returns an explicit ambiguous result rather than selecting the last entry.

### Backend conformance suite

Each backend implementation must prove:

* descriptor name, distribution, private API version;
* lazy selection and discovery;
* no connector import offline;
* relation parse/render/key round trips;
* quoted dots, case, wildcards, and variable depth;
* normalized error preservation;
* adapter-response raw-field preservation;
* capability consistency;
* supported/unsupported/unexecuted behavior;
* typed serialization;
* confirmed/not-found/not-visible/failed/unknown distinction;
* identity provenance and authority;
* connection/cursor/cancel/close cleanup;
* cost declarations;
* remedy serialization and confidence ceiling;
* no Tier-B execution without approval.

The suite must test outcomes, not merely that methods were called.

### Snowflake tests

Use provenance-recorded scrubbed real rows and exception shapes for:

* tables, views, materialized views, external/dynamic/vendor kinds;
* quoted and mixed-case identifiers;
* names containing dots, underscores, and percent characters;
* visible, hidden, and authoritatively absent cases;
* direct and inherited roles;
* database/schema/object/create privileges;
* exact failed query-ID correlation;
* documented failed execution states;
* role/user/warehouse identity provenance;
* session parameter values and levels;
* supported authentication/profile variants;
* cancellation and cleanup failures;
* generated command quoting and execution against disposable objects.

No fabricated recorded connector-row file is accepted.

### Fake external test distribution

Build a separate minimal wheel that registers the private group. Installed-wheel tests prove:

* explicit discovery;
* unselected module not imported;
* selection;
* built-in name collision rejection;
* duplicate external names;
* private API-version rejection;
* failed import/dependency error;
* offline operation without connector dependencies;
* unsupported capability behavior.

### Golden parity

Golden canonical documents must cover:

* every diagnosis class;
* offline and mocked-live states;
* pre/post Snowflake extraction compatibility projection;
* terminal projection from the same document;
* verbose/non-verbose semantic equivalence;
* one report assembly;
* one probe per request key;
* deterministic IDs and ordering;
* approved correctness deltas linked to issues.

### Logging tests

Tests cover every ADR property, including subprocess concurrency and JSON stdout purity. A redaction test succeeds only when the sensitive value is absent from:

* log lines;
* JSON stdout;
* stderr;
* terminal output;
* uploaded test artifacts.

### Higher-level tests

* CLI e2e from project and standalone directories.
* Property tests over malformed artifact structures, relations, request ordering, and redaction values.
* Chaos/failure injection at artifact, backend, session, cursor, writer, and renderer boundaries.
* Wheel and sdist install smoke.
* Import-boundary and Snowflake-token source guards.
* Performance assertions based on construction/probe counts rather than flaky wall-clock thresholds.
* Targeted mutation testing after resolver and redaction stabilize, limited to resolver state tables, cost gating, de-duplication, and redaction. It is not a release gate yet.

### Coverage

Adopt branch coverage with an initial total threshold of 85%. Critical new modules—resolver, request authorization, redaction, backend selection, and evidence-state conversion—should have explicit decision-table tests rather than relying only on an aggregate percentage. Coverage.py supports branch measurement and a `fail-under` gate. ([Coverage][10])

---

## 13. Complete CI job graph and proposed workflow.

The complete YAML is here:

[Proposed CI workflow](sandbox:/mnt/data/proposed_ci.yml)

It parsed successfully as YAML.

### Tool decisions

* **Ruff: adopt.** Use an explicit rule set, not `ALL`, plus format checking. Ruff supports linting/formatting and `pyproject.toml` configuration. ([Astral Docs][11])
* **mypy: adopt gradually.** Require strong typing for new `core`, `artifacts`, `backends`, and `opslog`; do not block the release on immediately making every legacy classifier strict. ([mypy Documentation][12])
* **Coverage.py: adopt**, branch mode, 85% initial threshold.
* **Dependency review: adopt on PRs.** It detects vulnerable dependency changes introduced by a PR. ([GitHub][13])
* **CodeQL: adopt** on PR/push/schedule for Python. CodeQL v4 is current and supported. ([GitHub][14])
* **pip-audit: adopt on trusted push/schedule**, not as the sole security control.
* **pre-commit: retain and align** with Ruff, compileall, ASCII, attribution, and fast unit checks.
* **Mutation testing: defer as a required gate** until pure resolver/redaction modules exist.
* **Build:** use `python -m build`; building an sdist and then a wheel from it helps expose incomplete source distributions. ([Build][15])

The proposed workflow uses current major versions of official actions: checkout v6, setup-python v6, upload-artifact v7, download-artifact v8, dependency-review v5, and CodeQL v4. ([GitHub][16])

For final merge, pin non-GitHub-owned actions to reviewed immutable SHAs and configure Dependabot to keep pins current.

### Job graph

| Job                     |  PR | Push |  Schedule/manual | Credentials                |
| ----------------------- | --: | ---: | ---------------: | -------------------------- |
| `guards`                | Yes |  Yes |              Yes | None                       |
| `lint-type`             | Yes |  Yes |              Yes | None                       |
| `compile-import`        | Yes |  Yes |              Yes | None                       |
| `unit (3.11-3.14)`      | Yes |  Yes |              Yes | None                       |
| `contract-robustness`   | Yes |  Yes |              Yes | None                       |
| `property`              | Yes |  Yes |              Yes | None                       |
| `e2e (3.11, 3.14)`      | Yes |  Yes |              Yes | None                       |
| `backend-conformance`   | Yes |  Yes |              Yes | None                       |
| `canonical-logging`     | Yes |  Yes |              Yes | None                       |
| `compat-schema-gate`    | Yes |  Yes |              Yes | None                       |
| `coverage`              | Yes |  Yes |              Yes | None                       |
| `dependency-review`     | Yes |   No |               No | GitHub token only          |
| `build`                 | Yes |  Yes |              Yes | None                       |
| `wheel-smoke`           | Yes |  Yes |              Yes | None                       |
| `external-plugin-wheel` | Yes |  Yes |              Yes | None                       |
| `codeql`                | Yes |  Yes |              Yes | GitHub security permission |
| `pip-audit`             |  No |  Yes |        Scheduled | None                       |
| `chaos`                 |  No |   No | Scheduled/manual | None                       |
| `live-snowflake`        |  No |   No | Protected manual | Snowflake secrets          |

GitHub workflow artifacts support cross-job persistence; the build job uploads one distribution set reused by wheel smoke and plugin tests. ([GitHub Docs][17])

### Fork safety

* `pull_request`, not `pull_request_target`.
* No Snowflake secrets on PR jobs.
* No live extra installed in offline jobs.
* Live job requires manual input, exact repository check, protected environment, and trusted branch.
* Operational logs are not uploaded except deliberately sanitized test outputs.
* Dependency review and CodeQL use minimal GitHub permissions.

### Caching and artifact retention

* `setup-python` pip cache.
* Coverage XML: 14 days.
* Wheel/sdist: 30 days.
* Sanitized live verification: 30 days.
* No credentials, raw SQL, or package operational logs in CI artifacts.

### Required branch-protection checks

```text
guards
lint-type
compile-import
unit (3.11)
unit (3.12)
unit (3.13)
unit (3.14)
contract-robustness
property
e2e (3.11)
e2e (3.14)
backend-conformance
canonical-logging
compat-schema-gate
coverage
dependency-review
build
wheel-smoke (3.11)
wheel-smoke (3.14)
external-plugin-wheel
codeql
```

`pip-audit`, `chaos`, and `live-snowflake` are not ordinary PR-required checks. Release policy separately requires a current successful live-verification record.

A green offline suite is necessary but not sufficient for release.

---

## 14. Snowflake live-verification matrix.

| Case                           | Setup                                     | Required evidence                              | Defect caught                                          |
| ------------------------------ | ----------------------------------------- | ---------------------------------------------- | ------------------------------------------------------ |
| Exact failed query ID          | Intentionally fail a disposable statement | Exact ID, failed state, code/message, identity | Current `FAIL` status bug; approximate mis-correlation |
| Missing statement ID           | Remove ID from diagnostic input           | Explicit fallback quality or unexecuted        | Silent downgrade to fuzzy match                        |
| Different diagnostic/run roles | Execute and diagnose under distinct roles | Both identities and provenance                 | Cross-identity evidence confirmation                   |
| Visible table                  | Owned disposable table                    | `CONFIRMED`, table kind                        | False negative relation probe                          |
| Visible view/materialized view | Disposable relations                      | Correct normalized and vendor kinds            | `SHOW TABLES`-only implementation                      |
| Hidden existing relation       | Revoke visibility from diagnostic role    | `NOT_VISIBLE`, never `NOT_FOUND`               | Absence/invisibility conflation                        |
| Authoritative absence          | Owned namespace with full visibility      | `NOT_FOUND` plus authority                     | Unevidenced physical absence                           |
| Quoted/mixed case              | Quoted parts and case variations          | Parse/render/key stability                     | Uppercasing and quote loss                             |
| Dot in quoted part             | `"DB.X"."S.Y"."T.Z"`                      | Exact round trip                               | `split(".")` parser                                    |
| `_` and `%` names              | Exact objects                             | Exact matching                                 | `LIKE` wildcard false positive                         |
| Direct privilege               | Grant directly                            | Direct path                                    | Grant tuple/intent decoding                            |
| Inherited privilege            | Role hierarchy                            | Inherited path                                 | Direct-only false denial                               |
| DB vs schema usage             | Grant one but not other                   | Separate missing prerequisites                 | Combined `has_usage` defect                            |
| Create privilege               | Disposable schema                         | Correct create intent                          | Read/create conflation                                 |
| Session parameter levels       | Account/user/session/warehouse cases      | Value, level, observer                         | Incorrect level/identity inference                     |
| Table description              | Real DESCRIBE rows                        | Name/type/nullability/order                    | Tuple-layout drift                                     |
| Connector exceptions           | Captured real failures                    | Safe normalized shape                          | Raw secret-bearing exception output                    |
| Cursor/connection cleanup      | Inject close/cancel failures              | Primary result preserved                       | Cleanup replaces original outcome                      |
| Password profile               | Protected test account                    | Validated connection                           | Profile mapping regression                             |
| Key-pair profile               | Protected key-pair identity               | Validated connection                           | Authentication variant regression                      |
| OAuth/external browser         | Only where CI-safe                        | Supported or documented unverified             | Unsupported claim                                      |
| Generated grant/remedy         | Disposable role/schema                    | Correctly quoted executable command            | Malformed or unsafe remedy                             |
| Timeout/cancellation           | Bounded disposable statement              | Failure normalization and cleanup              | Timeout/cancel semantics                               |
| Operational logging            | All cases                                 | No sensitive values; correlated run ID         | Log leakage or missing correlation                     |

Snowflake documents that `SHOW TABLES` uses wildcard matching, returns only objects visible to the current role, and does not require a running warehouse; it therefore cannot by itself establish physical absence or cover every relation kind. ([Snowflake Documentation][18])

The protected environment must use disposable objects and least-privileged credentials, never production data. Any bounded compute used solely to induce timeout/cancellation is test setup with an explicit cost cap, not a product Tier-B probe.

Release parity requires:

1. the full matrix result;
2. scrubbed provenance-recorded rows/exceptions;
3. canonical JSON from the installed wheel;
4. probe-count record;
5. no legacy calls;
6. maintainer sign-off attached to the release candidate.

---

## 15. Migration PR sequence and dependency DAG.

### Strict total order

| Order | Issue/PR | Scope                                                     | Effort |          Risk | Rollback                        |
| ----: | -------- | --------------------------------------------------------- | -----: | ------------: | ------------------------------- |
|     1 | **W0**   | Characterization golden output and probe counts           |      S |           Low | Remove tests                    |
|     2 | **#67**  | Validated artifact views/indexes and raw adapter response |      M |        Medium | Revert views                    |
|     3 | **W1**   | Active private pure backend interpretation seam           |      L |          High | Revert pure seam                |
|     4 | **#61**  | Backend-neutral edge-preserving lineage                   |      L |          High | Revert graph projection         |
|     5 | **#57**  | Generic config/raw-target boundary                        |      M |        Medium | Revert discovery boundary       |
|     6 | **#64**  | Offline default, backend selection, standalone artifacts  |      M |        Medium | Revert CLI contract             |
|     7 | **W2**   | Snowflake profile/session factory                         |      M |          High | Revert session factory          |
|     8 | **#55**  | Snowflake query-history and identity provider             |    M-L |          High | Revert provider                 |
|     9 | **#54**  | Snowflake relation/column visibility provider             |      L |          High | Revert provider                 |
|    10 | **W3**   | Snowflake privilege and session-context providers         |      L |          High | Revert providers                |
|    11 | **#62**  | Observations, evidence, dedupe, cost gate, resolver       |      L |     Very high | Revert class cutover            |
|    12 | **W4**   | Snowflake type semantics and remedies                     |    M-L |          High | Revert semantic provider        |
|    13 | **#56**  | Structured grouping and single assembly                   |      M |          High | Revert grouping                 |
|    14 | **#63**  | Canonical report document and terminal projection         |      L |     Very high | Revert compatibility projection |
|    15 | **LOG**  | Operational JSONL logging                                 |      M | High security | `--no-file-log`; revert issue   |
|    16 | **W5**   | Sole-path cutover, private discovery, legacy removal      |    M-L |          High | Revert entire cutover           |
|    17 | **#58**  | Semantic compatibility gate and hard cache requirement    |      M |        Medium | Revert gate                     |
|    18 | **#59**  | Complete offline CI and release gates                     |      L |        Medium | Revert workflow/helpers         |
|    19 | **#65**  | Legal/package/support metadata                            |    S-M |      Decision | Revert metadata                 |
|    20 | **#66**  | Protected live evidence and recorded rows                 |      M |          High | No production rollback          |
|    21 | **#33**  | TestPyPI/PyPI release                                     |      M |   Operational | Yank/release rollback           |

### Dependency DAG

```text
W0
 |
#67 ---------> #58
 |
W1
 |\
 | +-----> #57 -> #64 -> W2
 |
#61                |
 |                 #55
 |                  |
 +---------------- #54
                    |
                   W3
                    |
                   #62
                    |
                   W4
                    |
                   #56
                    |
                   #63
                    |
                   LOG
                    |
                   W5
                    |
          +---------+---------+
          |                   |
         #59                 #65
          \                   /
           +-------> #66 <---+
                       |
                      #33
```

### Parallel work

* #58 can proceed after #67 without touching runtime backend code.
* #52 real catalog capture can proceed whenever protected Snowflake access is available.
* #65 can proceed once the maintainer chooses a license and support metadata.
* Logging redaction prototypes can be researched earlier, but the production logging PR should follow #63 so it integrates one canonical run document.
* Post-release #43/#44 and research #45/#46/#47 do not block this path.

### Critical path

```text
W0 -> #67 -> W1 -> #64 -> W2 -> #55 -> #54 -> W3
   -> #62 -> W4 -> #56 -> #63 -> LOG -> W5 -> #66 -> #33
```

### Compatibility shims

Permitted:

* import-only re-exports for an existing import path;
* old JSON keys populated from the new final resolution;
* `--no-live` compatibility alias.

Forbidden:

* new collector followed by `enrich_reports()`;
* new provider falling back to old provider after failure;
* old and new request keys for the same probe;
* a runtime feature flag that executes both paths.

W5 removes every runtime shim. Any remaining import shim must have a documented deprecation version and a dedicated removal issue.

---

## 16. Existing tracker dispositions.

The tracker has already incorporated many earlier correctness recommendations. The current live epic explicitly lists #54-#67 as release work, and the compatibility epic lists #41, #52, #58, #67, and #59.

| Issue | Disposition                    | Architecture adjustment                                                       |
| ----: | ------------------------------ | ----------------------------------------------------------------------------- |
|    #4 | **KEEP OPEN — MODIFY**         | Add the warehouse-neutral epic and package logging release dependency.        |
|    #5 | **KEEP OPEN — MODIFY**         | Post-release Tier-B requests must execute through backend providers.          |
|    #6 | **KEEP OPEN — MODIFY**         | Same; no proactive passing-build scan.                                        |
|    #8 | **KEEP OPEN — MODIFY**         | Snowflake semantics/remedies use backend ports.                               |
|    #9 | **KEEP OPEN — MODIFY**         | Adapter response decoded by backend; scans remain out of scope.               |
|   #10 | **KEEP AS-IS**                 | Narrow permitted proactive consistency check.                                 |
|   #12 | **CLOSE — SUPERSEDED/MERGED**  | Already closed not planned; remaining scope belongs to #44.                   |
|   #15 | **KEEP OPEN — MODIFY**         | Future private correlation strategy; not initial release.                     |
|   #28 | **CLOSE — SUPERSEDED**         | Already closed; remaining work belongs to #8.                                 |
|   #33 | **KEEP OPEN — MODIFY**         | Add W5, LOG, and live parity as dependencies; add to initial milestone.       |
|   #41 | **KEEP AS-IS**                 | Compatible with the new architecture.                                         |
|   #43 | **KEEP OPEN — MODIFY**         | Post-release internal artifact evidence source only.                          |
|   #44 | **KEEP OPEN — MODIFY**         | Cross-version real artifact matrix; no fabricated fixtures.                   |
|   #45 | **KEEP AS-IS**                 | dbt log/event ingestion remains a separate spike.                             |
|   #46 | **KEEP AS-IS**                 | Deferred artifact-cache spike.                                                |
|   #47 | **KEEP AS-IS**                 | Deferred compatibility-watch documentation.                                   |
|   #48 | **KEEP OPEN — MODIFY**         | Reference new architecture epic; keep artifact ownership separate.            |
|   #52 | **KEEP AS-IS**                 | Real healthy catalog capture.                                                 |
|   #54 | **SPLIT / KEEP OPEN — MODIFY** | Relation/columns/visibility only; privileges/session move to W3.              |
|   #55 | **KEEP OPEN — MODIFY**         | Implement directly as Snowflake query-history/identity provider.              |
|   #56 | **KEEP OPEN — MODIFY**         | Consume structured final resolutions and relation keys.                       |
|   #57 | **KEEP OPEN — MODIFY**         | Generic raw-target boundary; Snowflake fields move to W2.                     |
|   #58 | **KEEP OPEN — MODIFY**         | Add milestone 1; coordinate with #67.                                         |
|   #59 | **KEEP OPEN — MODIFY**         | Python 3.11-3.14, backend conformance, external test wheel, logging.          |
|   #61 | **KEEP OPEN — MODIFY**         | Use backend-neutral `RelationRef`; depends on W1.                             |
|   #62 | **KEEP OPEN — MODIFY**         | Core owns planning/resolution; no backend planner or duplicate paths.         |
|   #63 | **KEEP OPEN — MODIFY**         | Add backend descriptor, run ID, evidence, redaction, and log summary.         |
|   #64 | **KEEP OPEN — MODIFY**         | Add `--warehouse`; no profile discovery offline.                              |
|   #65 | **KEEP OPEN — MODIFY**         | Snowflake-only statement, private SPI statement, Python upper bound.          |
|   #66 | **KEEP OPEN — MODIFY**         | Add sole-path proof, private conformance, parity, and logging leakage checks. |
|   #67 | **KEEP OPEN — MODIFY**         | Preserve raw adapter response; backend decoder owns meaning.                  |

The current bodies of #54-#67 correctly identify the major source defects but are ordered as legacy fixes. For example, #54 currently targets typed evidence but still frames the work around existing live helpers, and #55 names the entire `enrichers/` subtree. They should be implemented after W1/W2 as backend-provider replacements.

Recently completed foundation remains valid:

* #7 / PR #16: initial aggregator;
* #20 / PR #22: schema-version reporting;
* #23 / PR #27: property/chaos tiers;
* #24 / PR #26: defensive artifact handling;
* #25 / PR #29: static-linter removal;
* #34/#35 / PR #36: compatibility package;
* #37/#50 / PR #49: safe accessors and datetime correction;
* #38 / PR #51: corruption handling;
* #39/#40/#42 / PR #53: skew, catalog, and schema-gate work.

No issue currently owns package-generated operational logs; #45 owns only dbt event/log ingestion.

---

## 17. New or modified epic and issue drafts.

The complete ASCII-only issue packet contains:

* the new architecture epic;
* W0 through W5;
* the package operational logging issue;
* complete replacement bodies for #4, #54, #55, #57, #59, #61, #62, #63, #64, #65, #66, #67, and #33;
* exact template type, labels, parent, dependencies, release target, acceptance criteria, offline/live behavior, cost tier, logging impact, files, tests, and one-PR rationale.

[Complete tracker issue packet](sandbox:/mnt/data/tracker_issue_packet.md)

No issue, label, milestone, PR, or source file was mutated.

New issue titles in total order:

```text
[Epic] Warehouse-neutral core and Snowflake backend release gate
test: freeze Snowflake canonical-output and probe-count baselines before extraction
refactor: make the private backend interpretation seam active
refactor: move Snowflake profile validation and session creation behind the backend
refactor: move Snowflake privilege and session-context evidence behind backend capabilities
refactor: move Snowflake type semantics and remedy candidates out of core
feat: add sanitized package operational JSONL logs with run correlation
refactor: make Snowflake the sole backend path and remove legacy warehouse coupling
```

---

## 18. First PR implementation specification.

### Issue

```text
test: freeze Snowflake canonical-output and probe-count baselines before extraction
```

### Why this is first

* It has no dependency on the target architecture.
* It prevents accidental semantic drift.
* It detects duplicate probes during migration.
* It makes each later capability extraction independently revertible.
* Starting with protocols would otherwise freeze abstractions without proving current behavior.

### Tests first

Add:

```text
dbt_diagnostics/tests/characterization/
  __init__.py
  golden_index.json
  test_offline_public_json.py
  test_terminal_projection.py
  test_probe_counts.py
  test_ordering.py
  test_verbose_semantics.py
  helpers.py

dbt_diagnostics/tests/golden/pre_extraction/
  compilation_error.json
  contract_violation.json
  data_error_division_by_zero.json
  data_error_numeric_overflow.json
  data_error_string_overflow.json
  invalid_identifier.json
  object_unavailable.json
  insufficient_access.json
  schema_change.json
  syntax_error.json
  test_failure.json
  timeout.json
  root_cause_group.json
```

`golden_index.json` records:

* real input fixture paths;
* diagnosis family;
* offline/mocked-live mode;
* known-defect issue IDs;
* expected exit behavior;
* expected probe counts;
* whether real scrubbed connector evidence exists.

Do not fabricate a missing artifact or connector-row fixture. Mark unavailable live characterization as blocked on exact capture evidence.

### Probe-count recorder

Wrap current call sites with test spies for:

```text
table_exists
describe_table
find_matching_query
recover_run_role
check_role_grants
check_write_access
get_parameters
get_parameter_with_level
```

Assertions must be per semantic request, not merely global counts. One relation may legitimately require relation and column probes; it may not run the same relation probe twice.

### File-by-file changes

| File                         | Change                                                                                       |
| ---------------------------- | -------------------------------------------------------------------------------------------- |
| New characterization helpers | Canonicalize nondeterministic test-only values without changing runtime                      |
| New golden index             | Enumerate every diagnosis family and known defect                                            |
| New offline JSON tests       | Exercise current CLI/service output                                                          |
| New terminal tests           | Bind text to the same case                                                                   |
| New probe-count tests        | Fail on duplicate live calls                                                                 |
| Existing test fixtures       | No content changes unless a proven fixture defect is separately tracked                      |
| Production source            | None, except a narrowly justified test injection hook if monkeypatching cannot observe calls |

### Acceptance

* Every committed diagnosis class has a current public JSON baseline.
* Every baseline is generated from a real committed artifact or explicit inline pure-function input.
* Terminal and JSON cases share one test scenario.
* Ordering is deterministic.
* Duplicate probe tests fail if the new and legacy paths both execute.
* Known incorrect behavior is annotated, not silently blessed.
* No user-visible runtime change.
* CHANGELOG need not change.

### Exact commands

```bash
python -m compileall -q dbt_diagnostics
pytest -q dbt_diagnostics/tests/characterization
pytest -q -m "not live and not chaos"
python -m build
python -m venv /tmp/dbt-diagnostics-smoke
/tmp/dbt-diagnostics-smoke/bin/pip install dist/*.whl
/tmp/dbt-diagnostics-smoke/bin/dbt-diagnostics --help
```

### Evidence needed before beginning safely

1. An actual checkout of `donkey-kong-sandbox`.
2. All committed `real_*` artifacts and paired manifests.
3. Existing golden/CLI tests and templates.
4. The committed schema cache and provenance.
5. Any existing scrubbed real Snowflake rows/exceptions.
6. Confirmation of which current behavior is knowingly wrong and linked to #54, #55, #56, #61, or #62.
7. No Snowflake credentials are required for W0.

---

## 19. Risk register and rollback points.

| Risk                                        | Impact                | Mitigation                                                            | Rollback                                     |
| ------------------------------------------- | --------------------- | --------------------------------------------------------------------- | -------------------------------------------- |
| Backend bundle becomes service locator      | High                  | Destructure at composition; rules receive artifacts/observations only | Revert W1                                    |
| Public SPI freezes wrong semantics          | High                  | Keep private; no `api/v1`                                             | No public deprecation needed                 |
| Duplicate probes during migration           | High cost/correctness | Stable request keys and W0 probe counts                               | Revert capability PR                         |
| Visibility interpreted as absence           | Critical              | Authority and identity in evidence; conservative resolver             | Revert #54                                   |
| Query-history wrong match                   | High                  | Exact ID first; explicit correlation quality                          | Revert #55                                   |
| Quoted relation key collision               | High                  | Codec round trips and versioned keys                                  | Revert W1                                    |
| Evidence from different identities combined | Critical              | Resolver identity compatibility rules                                 | Revert W3/#62                                |
| Cleanup failure hides primary result        | Medium                | Secondary cleanup event/fact                                          | Revert W2/provider                           |
| Capability drift                            | High                  | Closed enum and conformance guard                                     | Revert W1/provider                           |
| Backend remedies inflate confidence         | High                  | Core validates evidence and confidence ceiling                        | Revert W4                                    |
| Public JSON break                           | Critical              | Compatibility projection and golden gate                              | Revert #63                                   |
| Renderer recomputes semantics               | High                  | Renderer accepts canonical document only                              | Revert #63                                   |
| Entry-point supply-chain import             | High                  | Private opt-in, exact selection, no import-all, built-in reserved     | Revert W5                                    |
| External plugin dependency conflict         | Medium                | Structured load failure, no fallback                                  | Disable experimental discovery               |
| Default file log leaks secrets              | Critical              | Mandatory redaction, no raw connector logs, adversarial tests         | `--no-file-log`; revert LOG                  |
| Multiple processes corrupt log              | Medium                | Unique file per run/process                                           | Disable file logging                         |
| Unwritable log aborts diagnosis             | Medium                | One warning plus no-op writer                                         | Disable file logging                         |
| Parity suite freezes known bug              | Medium                | Golden annotation with correction issue                               | Update only with issue-linked correctness PR |
| Fake fixtures create false confidence       | High                  | Provenance policy and no fabricated rows                              | Remove invalid fixture                       |
| CI expands beyond package claim             | Medium                | Narrow `<3.15`, four-version matrix                                   | Revert metadata/CI together                  |
| CI required names drift                     | Medium                | Version-controlled branch policy and stable job names                 | Revert #59                                   |
| Live test exposes secrets                   | Critical              | Protected environment, sanitized artifact, no forks                   | Disable environment/workflow                 |
| Migration shim becomes permanent            | Medium                | W5 owns removal; no runtime dual path                                 | Revert or remove shim                        |

---

## 20. Unverified questions with exact required evidence.

1. **[SPECULATIVE] Real adapter-response shapes across all failure classes.**
   Required: unmodified real dbt-snowflake `run_results.json` for success, compilation failure, runtime failure, generic test failure, cancellation, and timeout, with provenance.

2. **[SPECULATIVE] Authoritative Snowflake absence methodology.**
   Required: live proof that the probing role has complete visibility over a disposable owned namespace, followed by exact checks for present, hidden, and absent objects.

3. **[SPECULATIVE] Effective inherited-role privilege decoding.**
   Required: disposable direct and nested role hierarchy, captured `SHOW GRANTS` rows, and successful/failed operations under the target role.

4. **[SPECULATIVE] Historical session-parameter recovery.**
   Required: official Snowflake source or live evidence showing whether the failed statement’s effective parameter values and levels can be recovered after execution. Current diagnostic-session values are insufficient.

5. **[SPECULATIVE] Supported authentication variants.**
   Required: real profile samples and connection tests for password, key pair, OAuth, external browser, and any supported authenticator before claiming compatibility.

6. **[SPECULATIVE] Connector timeout/cancellation exception shapes.**
   Required: bounded live captures from the supported connector range.

7. **[SPECULATIVE] Public Python import usage.**
   Required: README/docs search and, ideally, download/user feedback evidence before removing existing root exports or `enrichers` import paths.

8. **[SPECULATIVE] Complete first-party schema cache in the actual branch.**
   Required: checkout inspection plus `scripts/compat/check_all.py`. The snapshot’s workflow still contains a cache-presence conditional.

9. **[SPECULATIVE] Dependency compatibility on Python 3.14.**
   Required: install and full offline suite for core and live extras on 3.14.

10. **[SPECULATIVE] Windows log permission guarantees.**
    Required: Windows CI or maintained local test proving file creation, ACL behavior, rotation, and concurrent invocation.

11. **[SPECULATIVE] Logging retention defaults under real usage.**
    Required: representative invocation frequency and log-size measurements; 14 days/100 runs/5 MiB are safe initial defaults, not empirical tuning.

12. **[SPECULATIVE] Maintainer decision on default offline mode.**
    Required: explicit acceptance on #64 before changing the current live-by-default behavior.

13. **[SPECULATIVE] License and private security contact.**
    Required: maintainer decision before #65.

14. **[SPECULATIVE] External backend API value.**
    Required: one independent backend prototype after Snowflake extraction. The fake test distribution proves mechanics, not public API usefulness.

15. **[SPECULATIVE] Performance at large manifest sizes.**
    Required: anonymized node/edge/result counts and one-index/probe-count measurements on a realistically large project.

---

## 21. Final file-impact matrix.

| Current file/package                          | Final impact                                                                                                         |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `pyproject.toml`                              | Narrow Python range; add tested dev tools; no public backend entry point; private test group only when W5 lands      |
| `main.py`                                     | Composition root; offline default; backend selection; logging setup; canonical output dispatch                       |
| `models.py`                                   | Compatibility imports/re-exports or split into typed `core` models; no mutable evidence state                        |
| `classifiers/base.py`                         | Consume validated views and normalized errors; no backend bundle                                                     |
| `runtime_error.py`                            | Generic normalized categories only                                                                                   |
| `contract_violation.py`                       | Generic contract observation; no Snowflake timestamp semantics                                                       |
| `data_error.py`                               | Generic data observations; no Snowflake types/functions/remedies                                                     |
| `timeout_error.py`                            | Generic timeout observation and semantic setting request                                                             |
| `schema_change_error.py`                      | Hypothesis until typed live column evidence                                                                          |
| `test_failure.py`                             | Backend-decoded execution metadata and typed relations                                                               |
| `registry.py`                                 | Deterministic internal rule registration; no public rule plugins                                                     |
| `tracers/column_tracer.py`                    | Injected dialect and typed relation schema                                                                           |
| `tracers/dag_walker.py`                       | Edge-preserving graph, real paths, truncation, typed relation keys                                                   |
| `tracers/diff_tracer.py`                      | Validated artifact views                                                                                             |
| `compat/safe.py`                              | Fallback order sourced from registry; no Snowflake query-ID accessor                                                 |
| `compat/consumed_paths.py`                    | Complete semantic registry                                                                                           |
| `compat/path_resolver.py` / `schema_model.py` | Compare relevant definitions, type, requiredness, nullability                                                        |
| `enrichers/connection.py`                     | Move to Snowflake backend; optional import shim only during migration                                                |
| `enrichers/schema_inspector.py`               | Replace with Snowflake relation/column provider                                                                      |
| `enrichers/query_history.py`                  | Replace with Snowflake query-history provider                                                                        |
| `enrichers/run_identity.py`                   | Replace with Snowflake identity provider                                                                             |
| `enrichers/grants.py`                         | Replace with Snowflake privilege provider                                                                            |
| `enrichers/params.py`                         | Replace with Snowflake semantic session provider                                                                     |
| `enrichers/enrich.py`                         | Remove after per-capability cutover                                                                                  |
| `root_cause.py`                               | Move resolution/grouping to core; remove `LiveObjectProbe`                                                           |
| `grouping.py`                                 | Structured symptom/root-cause grouping over final resolutions                                                        |
| `renderer.py`                                 | Accept canonical report document only                                                                                |
| Jinja templates                               | Formatting only; no diagnosis, grouping, or generated command logic                                                  |
| `discover.py`                                 | Generic project/raw-target discovery only                                                                            |
| `schema_version.py`                           | Structural support separate from real-version validation                                                             |
| `colors.py`                                   | Retain                                                                                                               |
| `opslog/**`                                   | New sanitized JSONL facility                                                                                         |
| `backends/snowflake/**`                       | New sole location for Snowflake semantics and live implementation                                                    |
| `core/**`                                     | New typed internal contracts                                                                                         |
| `artifacts/**`                                | New validated views and indexes                                                                                      |
| `engine/**`                                   | New planner, de-duplicating collector, resolver, assembler                                                           |
| Tests                                         | Split into core, artifacts, backend conformance, Snowflake, fake distribution, golden, logging, redaction, e2e, live |
| `.github/workflows/ci.yml`                    | Complete offline/security/build matrix plus protected live job                                                       |
| README/docs                                   | Snowflake-only support, private SPI, offline default, canonical JSON, operational logging                            |
| `CHANGELOG.md`                                | Per-PR behavior and compatibility entries                                                                            |

**Recommended first PR:** `test: freeze Snowflake canonical-output and probe-count baselines before extraction`.

**Exact evidence required to begin safely:** a writable checkout of `donkey-kong-sandbox`, every committed real artifact and schema-cache file, the full current test/template suite, existing scrubbed real Snowflake rows and exceptions, and an issue-linked list of current known output defects.

[1]: https://docs.python.org/3.12/library/importlib.metadata.html "https://docs.python.org/3.12/library/importlib.metadata.html"
[2]: https://docs.snowflake.com/sql-reference/identifiers-syntax.html "https://docs.snowflake.com/sql-reference/identifiers-syntax.html"
[3]: https://docs.getdbt.com/reference/artifacts/run-results-json "https://docs.getdbt.com/reference/artifacts/run-results-json"
[4]: https://devguide.python.org/versions/index.html "https://devguide.python.org/versions/index.html"
[5]: https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-api "https://docs.snowflake.com/en/developer-guide/python-connector/python-connector-api"
[6]: https://docs.snowflake.com/en/sql-reference/functions/query_history "https://docs.snowflake.com/en/sql-reference/functions/query_history"
[7]: https://docs.snowflake.com/en/sql-reference/sql/show-grants "https://docs.snowflake.com/en/sql-reference/sql/show-grants"
[8]: https://docs.python.org/3.11/howto/logging-cookbook.html "https://docs.python.org/3.11/howto/logging-cookbook.html"
[9]: https://docs.python.org/ja/3.14/library/logging.handlers.html "https://docs.python.org/ja/3.14/library/logging.handlers.html"
[10]: https://coverage.readthedocs.io/ "https://coverage.readthedocs.io/"
[11]: https://docs.astral.sh/ruff "https://docs.astral.sh/ruff"
[12]: https://mypy.readthedocs.io/en/stable/config_file.html?highlight=follow_imports "https://mypy.readthedocs.io/en/stable/config_file.html?highlight=follow_imports"
[13]: https://github.com/actions/dependency-review-action "https://github.com/actions/dependency-review-action"
[14]: https://github.com/github/codeql-action/releases "https://github.com/github/codeql-action/releases"
[15]: https://build.pypa.io/en/latest/how-to/basic-usage.html "https://build.pypa.io/en/latest/how-to/basic-usage.html"
[16]: https://github.com/actions/checkout/releases "https://github.com/actions/checkout/releases"
[17]: https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts "https://docs.github.com/en/actions/concepts/workflows-and-actions/workflow-artifacts"
[18]: https://docs.snowflake.com/en/sql-reference/sql/show-tables "https://docs.snowflake.com/en/sql-reference/sql/show-tables"
