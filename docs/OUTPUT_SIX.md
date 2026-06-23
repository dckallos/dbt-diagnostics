# Revised verdict

I accept the pushback. My earlier recommendation to defer full adapter extraction until after the first release was wrong under this project’s contributor and ecosystem goals.

**The initial public release should remain Snowflake-only, but the diagnostic core must be warehouse-neutral before release.** Snowflake should be a built-in plugin and the only compatible warehouse implementation, not a semantic dependency of the core.

No new context window is necessary. The current snapshot, tracker state, and official warehouse documentation are sufficient for the revised design.

The release statement should be:

> dbt-diagnostics currently supports Snowflake only. Its diagnostic engine is warehouse-neutral, and Snowflake support is provided by the built-in Snowflake warehouse plugin.

It must not say that Databricks, BigQuery, or other warehouses are supported.

---

# 1. Revised architectural decision

Do **not** create one large `WarehouseAdapter` protocol with optional methods or an `execute(sql)` escape hatch.

Instead, introduce a **`WarehouseBackend` bundle** composed of small, capability-specific interfaces:

```text
WarehouseBackend
  descriptor
  capabilities
  profile validator
  connection factory
  identifier/relation codec
  dbt adapter-response decoder
  error normalizer
  SQL dialect
  evidence planning extension
  evidence providers
  remedy provider
```

This distinction matters:

* The **core** owns the questions being asked.
* The **adapter** owns how a warehouse can answer them.
* The **evidence model** preserves what was actually established.
* The **resolver** decides what conclusions the evidence supports.
* The **renderer** formats already-resolved canonical output.

dbt itself documents that `adapter_response` is adapter-dependent and may contain different fields such as rows affected or bytes processed. That field therefore cannot be normalized by generic artifact accessors into Snowflake `query_id` assumptions. ([dbt Developer Hub][1])

---

# 2. Initial-release invariants

The release is blocked until all of these are true.

## Physical isolation

1. No module under the generic core imports `adapters.snowflake`.
2. No generic module imports `snowflake.connector`.
3. No generic module imports a Snowflake probe, row decoder, error parser, or remedy helper.
4. The CLI composition root selects a backend through a registry.
5. The selected backend is passed through the active runtime path.
6. Snowflake is the sole implementation used for live execution.
7. Legacy `enrichers/` paths are not run alongside the adapter path.

## Semantic isolation

Generic modules contain none of the following:

* Snowflake error codes such as `002003`, `000904`, `003001`, or `100035`;
* `SHOW TABLES`, `SHOW GRANTS`, `DESCRIBE TABLE`, or query-history SQL;
* Snowflake tuple positions;
* Snowflake identifier folding or double-quote rules;
* `TIMESTAMP_LTZ`, `TIMESTAMP_TYPE_MAPPING`, warehouses, or roles as generic assumptions;
* Snowflake `GRANT` or `ALTER WAREHOUSE` commands;
* a three-part-name parser that assumes `database.schema.relation`;
* direct reads of `adapter_response.query_id`.

## Behavioral guarantees

* Offline artifact analysis imports no optional connector and performs no credential discovery.
* The canonical JSON-compatible report document remains normative.
* Terminal output remains a projection of that document.
* `confirmed`, `not_found`, `not_visible`, `failed`, `unsupported`, and `unknown` remain distinct.
* Tier-A metadata and Tier-B scans remain distinct.
* Tier A means “metadata-only,” not “universally free.”
* No migration PR executes old and new probes against the same finding.
* Existing Snowflake behavior is proven by golden JSON and real-account verification.

---

# 3. Target package layout

```text
dbt_diagnostics/
  api/
    v1/
      adapter.py
      capabilities.py
      connection.py
      errors.py
      evidence.py
      identifiers.py
      json_types.py
      plugin.py
      probes.py
      remedies.py

  artifacts/
    bundle.py
    context.py
    manifest_view.py
    run_results_view.py
    catalog_view.py
    consumed_paths.py
    compatibility/
      schema_model.py
      path_resolver.py
      schema_diff.py

  domain/
    observations.py
    findings.py
    lineage.py
    resolution.py
    report.py

  engine/
    pipeline.py
    classifier_engine.py
    evidence_planner.py
    evidence_collector.py
    resolver.py
    report_assembler.py

  diagnostics/
    compilation.py
    contract.py
    runtime.py
    schema_change.py
    data.py
    timeout.py
    test_failure.py

  sql/
    column_tracer.py
    snippets.py

  adapters/
    registry.py
    snowflake/
      plugin.py
      capabilities.py
      profile.py
      connection.py
      identifiers.py
      artifact_response.py
      errors.py
      evidence_plan.py
      remedies.py
      probes/
        relations.py
        columns.py
        query_history.py
        identity.py
        privileges.py
        session.py

  renderers/
    terminal.py
    templates/

  cli/
    arguments.py
    paths.py
    main.py
```

Temporary compatibility re-exports may keep old import locations working, but they must not remain active runtime paths. Their removal is owned by a named final extraction issue.

---

# 4. Import direction and cycle proof

```text
api.v1
  imports: stdlib only

domain
  imports: api.v1 value types only

artifacts
  imports: api.v1 JSON/value types
  imports: domain artifact-neutral identifiers where necessary

diagnostics
  imports: artifacts + domain
  never imports adapters

sql
  imports: domain + api.v1 dialect contract
  never imports adapters

engine
  imports: artifacts + domain + api.v1 protocols
  never imports adapters.snowflake

adapters.snowflake
  imports: api.v1 + domain
  never imports engine, diagnostics, or renderers

renderers
  import: canonical report document only

adapters.registry
  imports: api.v1 plugin contract
  loads implementations lazily

cli
  imports: registry + engine + renderers
```

The only component allowed to know both the engine and the selected backend is the composition root in `cli`.

An automated import rule should enforce:

```text
dbt_diagnostics.domain       !-> dbt_diagnostics.adapters
dbt_diagnostics.artifacts    !-> dbt_diagnostics.adapters
dbt_diagnostics.diagnostics  !-> dbt_diagnostics.adapters
dbt_diagnostics.engine       !-> dbt_diagnostics.adapters.snowflake
dbt_diagnostics.renderers    !-> dbt_diagnostics.adapters
```

---

# 5. Core concepts versus adapter-owned concepts

| Core owns                                   | Adapter owns                                    |
| ------------------------------------------- | ----------------------------------------------- |
| dbt artifact views and indexes              | dbt profile-output validation                   |
| dbt DAG and lineage edges                   | connector and authentication                    |
| classifier observations                     | identifier grammar and quoting                  |
| normalized error categories                 | vendor error parsing                            |
| evidence status ontology                    | warehouse SQL and APIs                          |
| probe requests                              | cursor/API response decoding                    |
| cost policy and Tier A/B gate               | actual metadata cost characteristics            |
| canonical relation identity container       | relation-name parsing and canonicalization      |
| generic relation kinds                      | mapping vendor relation kinds                   |
| normalized execution identity               | roles, IAM, service principals, groups          |
| access intents such as read/create/discover | grant/IAM semantics and inheritance             |
| generic query-history result                | query-history source, retention, states, access |
| final resolution and confidence rules       | platform-specific resolution candidates         |
| canonical report schema                     | platform-specific evidence extensions           |
| terminal/JSON projections                   | SQL remedies and generated warehouse commands   |
| redaction policy                            | identification of sensitive adapter fields      |

Core-normalized concepts must not erase Snowflake evidence. Every normalized object therefore permits typed adapter extensions.

---

# 6. Public adapter API sketches

## JSON-compatible extension values

```python
from __future__ import annotations

from typing import TypeAlias, Union

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = Union[
    JsonScalar,
    list["JsonValue"],
    dict[str, "JsonValue"],
]
JsonObject: TypeAlias = dict[str, JsonValue]
```

This is preferable to `Any` in public evidence contracts.

## Plugin descriptor

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class AdapterDescriptor:
    name: str
    display_name: str
    adapter_api_version: int
    distribution_name: str
    distribution_version: str
    profile_types: tuple[str, ...]
```

## Capabilities

Capabilities must describe more than yes/no support.

```python
from dataclasses import dataclass
from enum import StrEnum


class SupportLevel(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"
    LIVE_VERIFICATION_REQUIRED = "live_verification_required"


class ProbeTier(StrEnum):
    METADATA = "tier_a_metadata"
    DATA_SCAN = "tier_b_data_scan"


class ComputeRequirement(StrEnum):
    NONE = "none"
    REQUIRED = "required"
    UNKNOWN = "unknown"


class BillingModel(StrEnum):
    NO_INCREMENTAL_COMPUTE = "no_incremental_compute"
    BILLABLE_QUERY = "billable_query"
    CAPACITY_CONSUMING = "capacity_consuming"
    UNKNOWN = "unknown"


class VisibilitySemantics(StrEnum):
    AUTHORITATIVE = "authoritative"
    IDENTITY_SCOPED = "identity_scoped"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CapabilityDescriptor:
    capability_id: str
    support: SupportLevel
    probe_tier: ProbeTier
    compute: ComputeRequirement
    billing: BillingModel
    visibility: VisibilitySemantics
    notes: tuple[str, ...] = ()
```

`WarehouseCapabilities` should be an immutable mapping keyed by capability ID. New adapters can add namespaced capabilities without changing a large dataclass.

```python
@dataclass(frozen=True)
class WarehouseCapabilities:
    values: dict[str, CapabilityDescriptor]

    def get(self, capability_id: str) -> CapabilityDescriptor:
        ...
```

## Identifiers and relations

Core must never split a relation string on `"."`.

```python
from dataclasses import dataclass
from enum import StrEnum


class NamespaceRole(StrEnum):
    PROJECT = "project"
    CATALOG = "catalog"
    DATABASE = "database"
    DATASET = "dataset"
    SCHEMA = "schema"
    NAMESPACE = "namespace"
    RELATION = "relation"


@dataclass(frozen=True)
class Identifier:
    value: str
    quoted: bool
    original: str


@dataclass(frozen=True)
class NamePart:
    role: NamespaceRole
    identifier: Identifier


@dataclass(frozen=True)
class RelationRef:
    adapter_name: str
    parts: tuple[NamePart, ...]
    raw: str

    # Opaque, adapter-generated key for equality, indexing, and grouping.
    canonical_key: str
```

```python
class RelationCodec(Protocol):
    def parse_relation(self, raw: str) -> RelationRef | None: ...

    def render_relation(self, relation: RelationRef) -> str: ...

    def quote_identifier(self, identifier: Identifier) -> str: ...

    def relation_key(self, relation: RelationRef) -> str: ...
```

## Adapter-response decoding

```python
@dataclass(frozen=True)
class AdapterExecutionMetadata:
    statement_id: str | None
    rows_affected: int | None
    bytes_processed: int | None
    raw_fields: JsonObject


class AdapterResponseDecoder(Protocol):
    def decode(
        self,
        adapter_response: JsonObject | None,
    ) -> AdapterExecutionMetadata: ...
```

`ArtifactContext` exposes the raw JSON-compatible `adapter_response`. Snowflake decides whether a `query_id` field is meaningful.

## Error normalization

```python
@dataclass(frozen=True)
class RawWarehouseFailure:
    message: str
    adapter_response: JsonObject | None
    compiled_sql: str | None


class WarehouseErrorCategory(StrEnum):
    OBJECT_UNAVAILABLE = "object_unavailable"
    INVALID_IDENTIFIER = "invalid_identifier"
    INSUFFICIENT_ACCESS = "insufficient_access"
    SYNTAX = "syntax"
    TIMEOUT = "timeout"
    COMPUTE_UNAVAILABLE = "compute_unavailable"
    DATA_CONVERSION = "data_conversion"
    NUMERIC_OVERFLOW = "numeric_overflow"
    STRING_OVERFLOW = "string_overflow"
    DIVISION_BY_ZERO = "division_by_zero"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ErrorLocation:
    line: int | None
    position: int | None


@dataclass(frozen=True)
class NormalizedWarehouseError:
    category: WarehouseErrorCategory
    raw_message: str
    vendor_code: str | None
    sqlstate: str | None
    vendor_condition: str | None
    relation: RelationRef | None
    identifier: Identifier | None
    required_access: str | None
    location: ErrorLocation | None
    vendor_details: JsonObject


class ErrorNormalizer(Protocol):
    def normalize(
        self,
        failure: RawWarehouseFailure,
    ) -> NormalizedWarehouseError | None: ...
```

Generic runtime diagnosis consumes `NormalizedWarehouseError`. Snowflake codes and message regexes live only in `adapters/snowflake/errors.py`.

## Evidence status

```python
class EvidenceStatus(StrEnum):
    CONFIRMED = "confirmed"
    NOT_FOUND = "not_found"
    NOT_VISIBLE = "not_visible"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"
```

`NOT_FOUND` may be returned only when the adapter can establish absence with the recorded authority. A visibility-limited metadata query returns `NOT_VISIBLE` or `UNKNOWN`, not `NOT_FOUND`.

## Execution identity

```python
@dataclass(frozen=True)
class ExecutionIdentity:
    principal: str | None
    principal_id: str | None
    user: str | None
    role: str | None
    groups: tuple[str, ...]
    compute_resource: str | None
    provenance: str
    status: EvidenceStatus
    adapter_details: JsonObject
```

This supports:

* Snowflake user + active role + warehouse;
* Databricks user or service principal + groups + SQL warehouse;
* BigQuery user/service account + project/job context.

## Probe requests

```python
@dataclass(frozen=True)
class InspectRelationRequest:
    relation: RelationRef


@dataclass(frozen=True)
class InspectColumnsRequest:
    relation: RelationRef


@dataclass(frozen=True)
class QueryHistoryRequest:
    statement_id: str | None
    compiled_sql: str | None
    started_at: str | None
    completed_at: str | None


@dataclass(frozen=True)
class RecoverExecutionIdentityRequest:
    statement_id: str | None
    declared_identity: ExecutionIdentity | None


class AccessIntent(StrEnum):
    DISCOVER_RELATION = "discover_relation"
    READ_RELATION = "read_relation"
    CREATE_RELATION = "create_relation"
    REPLACE_RELATION = "replace_relation"


@dataclass(frozen=True)
class InspectPrivilegesRequest:
    relation: RelationRef
    principal: str | None
    intent: AccessIntent


class SemanticSetting(StrEnum):
    STATEMENT_TIMEOUT = "statement_timeout"
    TIMEZONE = "timezone"
    TIMESTAMP_TYPE_BEHAVIOR = "timestamp_type_behavior"


@dataclass(frozen=True)
class InspectSessionContextRequest:
    settings: tuple[SemanticSetting, ...]
```

Generic classifiers request semantic settings, not Snowflake parameter names.

## Evidence payloads

```python
class RelationKind(StrEnum):
    TABLE = "table"
    VIEW = "view"
    MATERIALIZED_VIEW = "materialized_view"
    EXTERNAL_TABLE = "external_table"
    SNAPSHOT = "snapshot"
    DYNAMIC_TABLE = "dynamic_table"
    OTHER = "other"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RelationEvidence:
    relation: RelationRef
    kind: RelationKind
    vendor_kind: str | None


@dataclass(frozen=True)
class ColumnDescriptor:
    name: Identifier
    data_type: str
    nullable: bool | None
    ordinal_position: int | None
    vendor_type: JsonObject


@dataclass(frozen=True)
class ColumnsEvidence:
    relation: RelationRef
    columns: tuple[ColumnDescriptor, ...]


@dataclass(frozen=True)
class QueryHistoryEvidence:
    statement_id: str | None
    execution_state: str | None
    error_code: str | None
    error_message: str | None
    identity: ExecutionIdentity | None
    started_at: str | None
    completed_at: str | None
    redacted_query_fingerprint: str | None
    adapter_details: JsonObject


@dataclass(frozen=True)
class PrivilegeEvidence:
    relation: RelationRef
    principal: str | None
    intent: AccessIntent
    direct_permissions: tuple[str, ...]
    inherited_permissions: tuple[str, ...]
    missing_prerequisites: tuple[str, ...]
    adapter_details: JsonObject


@dataclass(frozen=True)
class SessionSettingEvidence:
    setting: SemanticSetting
    value: str | None
    source_level: str | None
    adapter_details: JsonObject


@dataclass(frozen=True)
class AdapterExtensionEvidence:
    schema_id: str
    payload: JsonObject
```

```python
EvidencePayload = (
    RelationEvidence
    | ColumnsEvidence
    | QueryHistoryEvidence
    | PrivilegeEvidence
    | SessionSettingEvidence
    | ExecutionIdentity
    | AdapterExtensionEvidence
)
```

## Evidence record

```python
@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    capability_id: str
    adapter_name: str
    status: EvidenceStatus
    payload: EvidencePayload | None
    observed_by: ExecutionIdentity | None
    probe_tier: ProbeTier
    observed_at: str | None
    reason: str | None
    redacted_query: str | None
```

## Session and connection factory

No DB-API assumption belongs in the generic contract.

```python
class WarehouseSession(Protocol):
    @property
    def adapter_name(self) -> str: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class ProfileTarget:
    profile_name: str
    target_name: str
    adapter_type: str
    values: JsonObject


@dataclass(frozen=True)
class ProfileValidation:
    valid: bool
    errors: tuple[str, ...]
    declared_identity: ExecutionIdentity | None


class WarehouseConnectionFactory(Protocol):
    def validate_profile(
        self,
        target: ProfileTarget,
    ) -> ProfileValidation: ...

    def connect(
        self,
        target: ProfileTarget,
    ) -> WarehouseSession: ...
```

Core discovers and selects the raw dbt profile target. The adapter validates and interprets its fields.

## Evidence providers

```python
ProbeRequest = (
    InspectRelationRequest
    | InspectColumnsRequest
    | QueryHistoryRequest
    | RecoverExecutionIdentityRequest
    | InspectPrivilegesRequest
    | InspectSessionContextRequest
)


class EvidenceProvider(Protocol):
    capability_id: str

    def supports(self, request: ProbeRequest) -> bool: ...

    def collect(
        self,
        request: ProbeRequest,
        session: WarehouseSession,
    ) -> EvidenceRecord: ...
```

There is deliberately no `execute(sql)` method.

## Adapter-specific evidence planning

The Snowflake timestamp-mapping diagnosis should not make generic classifiers request `TIMESTAMP_TYPE_MAPPING`.

```python
class AdapterEvidencePlanner(Protocol):
    def plan_for_observation(
        self,
        observation: DiagnosticObservation,
        context: ArtifactContext,
    ) -> tuple[ProbeRequest, ...]: ...
```

The generic planner combines:

* core requests implied by the observation;
* adapter-specific requests contributed by the selected backend;
* cost and user-policy constraints;
* de-duplication by stable request key.

## Platform remedies

```python
class RemedyStepKind(StrEnum):
    DBT_COMMAND = "dbt_command"
    WAREHOUSE_COMMAND = "warehouse_command"
    MANUAL_CHECK = "manual_check"
    EXPLANATION = "explanation"


@dataclass(frozen=True)
class RemedyStep:
    kind: RemedyStepKind
    description: str
    command: str | None
    requires_privilege: str | None
    probe_tier: ProbeTier | None


@dataclass(frozen=True)
class RemedyCandidate:
    candidate_id: str
    title: str
    steps: tuple[RemedyStep, ...]
    required_evidence_ids: tuple[str, ...]
    confidence_ceiling: str


class RemedyProvider(Protocol):
    def candidates(
        self,
        observation: DiagnosticObservation,
        evidence: tuple[EvidenceRecord, ...],
    ) -> tuple[RemedyCandidate, ...]: ...
```

Snowflake `GRANT`, `ALTER WAREHOUSE`, `SHOW`, `DESCRIBE`, and type-cast suggestions belong here.

## Backend bundle

```python
@dataclass(frozen=True)
class WarehouseBackend:
    descriptor: AdapterDescriptor
    capabilities: WarehouseCapabilities
    connection_factory: WarehouseConnectionFactory
    relation_codec: RelationCodec
    adapter_response_decoder: AdapterResponseDecoder
    error_normalizer: ErrorNormalizer
    sqlglot_dialect: str
    evidence_planner: AdapterEvidencePlanner
    evidence_providers: tuple[EvidenceProvider, ...]
    remedy_provider: RemedyProvider
```

---

# 7. Plugin registration and selection

Warehouse adapters should be the one public plugin surface in the initial release.

Use a Python package entry-point group:

```toml
[project.entry-points."dbt_diagnostics.warehouse_backends"]
snowflake = "dbt_diagnostics.adapters.snowflake.plugin:get_backend"
```

External packages can later declare:

```toml
[project.entry-points."dbt_diagnostics.warehouse_backends"]
example = "dbt_diagnostics_example.plugin:get_backend"
```

Package metadata entry points are the standard mechanism for separately distributed Python plugins, and `importlib.metadata.entry_points()` supports discovery by group. ([Python Packaging][2])

Selection rules:

```python
def select_backend(
    registry: WarehouseBackendRegistry,
    *,
    explicit_name: str | None,
    profile_type: str | None,
    offline_default: str = "snowflake",
) -> WarehouseBackend:
    ...
```

Rules:

1. `--warehouse snowflake` wins.
2. In explicit live mode, the selected profile output type must match the backend.
3. Offline initial-release default is `snowflake`.
4. An installed but unselected third-party backend is not imported.
5. Duplicate backend names are a configuration error.
6. An adapter API version mismatch is a clear load error.
7. The built-in Snowflake backend cannot be silently shadowed.

CLI additions:

```text
dbt-diagnostics adapters list
dbt-diagnostics adapters inspect snowflake
dbt-diagnostics --warehouse snowflake
```

Output must make support status explicit:

```text
snowflake  built-in  compatible
```

No Databricks or BigQuery entries ship with the first release.

---

# 8. Active runtime pipeline

```text
ArtifactSource
    |
    v
ArtifactBundle
    |
    v
validated ArtifactContext / indexed views
    |
    +--> backend adapter-response decoder
    |
    v
classifier observations
    |
    +--> normalized warehouse error from selected backend
    |
    v
lineage graph + offline evidence
    |
    v
evidence plan
    |
    +--> backend-specific planning extension
    +--> capability and cost-policy gate
    +--> request de-duplication
    |
    v
typed evidence collection
    |
    v
one final resolution pass
    |
    +--> backend remedy candidates
    |
    v
canonical report document
    |
    +--> JSON serialization
    |
    +--> terminal projection
```

Offline mode follows the same pipeline with no live session:

* supported probes become unexecuted/unknown evidence;
* unsupported capabilities remain unsupported;
* the report records exact manual confirmation steps;
* no connector or credentials are required.

---

# 9. Snowflake-to-backend ownership map

| Current code                                              | Target                                          |
| --------------------------------------------------------- | ----------------------------------------------- |
| `enrichers.connection.parse_profile/open_connection`      | `adapters.snowflake.profile` and `connection`   |
| `schema_inspector._validate_identifier/_validate_fq_name` | `adapters.snowflake.identifiers`                |
| `schema_inspector.table_exists/describe_table`            | Snowflake relation and column providers         |
| `query_history.find_matching_query`                       | Snowflake query-history provider                |
| `run_identity.recover_run_role`                           | Snowflake identity provider                     |
| `grants.check_role_grants`                                | Snowflake privilege provider                    |
| `grants.check_write_access`                               | Snowflake privilege provider                    |
| `params.get_parameters`                                   | Snowflake session-context provider              |
| Snowflake error regexes in classifiers                    | `adapters.snowflake.errors`                     |
| `safe.result_query_id`                                    | Snowflake adapter-response decoder              |
| hardcoded `dialect="snowflake"`                           | backend `sqlglot_dialect`                       |
| relation `.split(".")` and `.upper()`                     | backend relation codec                          |
| `_fix_denied()` and Snowflake SQL fixes                   | Snowflake remedy provider                       |
| `TIMESTAMP_TYPE_MAPPING` reconciliation                   | Snowflake evidence planner + remedy provider    |
| `LiveObjectProbe` in `root_cause.py`                      | engine evidence planner/collector               |
| Snowflake tuple mocks                                     | adapter contract fixtures under Snowflake tests |

After extraction, `enrichers/` should either be removed or contain short deprecated re-exports that are not used by the package itself.

---

# 10. Reality check against three warehouses

This matrix validates why the backend cannot be reduced to SQL execution.

| Dimension             | Snowflake                                                                      | Databricks                                                                                       | BigQuery                                                                                                       | Contract implication                                                                                         |
| --------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Connection            | Native Python connector; DB-API connection/cursor model                        | SQL connector uses hostname/HTTP path and PAT or OAuth methods                                   | Cloud client library commonly uses Application Default Credentials                                             | Connection must be opaque; no generic DB-API requirement. ([Snowflake Documentation][3])                     |
| Namespace             | Database/schema/relation                                                       | Unity Catalog uses catalog/schema/relation                                                       | Project/dataset/table, with optional qualification                                                             | Core must not assign database/schema semantics by position. ([Databricks Documentation][4])                  |
| Quoting/case          | Double quotes; unquoted names fold to uppercase                                | Backticks; identifiers are case-insensitive when referenced                                      | Backticks; table and dataset case behavior differs and can be configured                                       | Identifier codec must be adapter-owned. ([Snowflake Documentation][5])                                       |
| Relation kinds        | Tables, views, materialized views, external and other Snowflake-specific kinds | Tables, views, materialized views, metric views, streaming tables and others                     | Standard, external, view, materialized view, snapshot, clone                                                   | Generic relation kind needs `OTHER` plus vendor kind. ([Snowflake Documentation][6])                         |
| Metadata visibility   | Information Schema and SHOW are identity/role scoped                           | Information Schema rows are limited to relations the principal may interact with                 | Metadata views require specific IAM permissions                                                                | Empty result is not universally authoritative absence. ([Snowflake Documentation][6])                        |
| Query history         | Information Schema query history, seven-day window, Snowflake-specific states  | `system.query.history` is currently preview, account/region-scoped, admin-only by default        | `INFORMATION_SCHEMA.JOBS` is near real time and project/region/IAM scoped                                      | Query-history support needs retention, visibility, source and state metadata. ([Snowflake Documentation][7]) |
| Identity              | User, active role, warehouse                                                   | User or service principal; Unity Catalog principals include users, service principals and groups | User or service account, project/job context, IAM roles                                                        | `ExecutionIdentity` cannot be just a role string. ([Databricks Documentation][8])                            |
| Privileges            | Role hierarchy, database/schema usage and object privileges                    | Catalog/schema/object privileges with inheritance and `USE CATALOG`/`USE SCHEMA`                 | IAM policies at project/dataset/table levels; inherited bindings differ from explicit object bindings          | Access inspection needs generic intent plus adapter details. ([Snowflake Documentation][9])                  |
| Session context       | Account/user/session/object parameter hierarchy                                | SQL configuration and compute/session settings differ                                            | No equivalent Snowflake-style session-parameter hierarchy                                                      | Session context is an optional capability, not a mandatory method. ([Snowflake Documentation][10])           |
| Error model           | Numeric vendor codes, SQLSTATE and messages                                    | Structured Databricks error conditions/SQLSTATE                                                  | HTTP status plus API `ErrorProto.reason` and job errors                                                        | Error normalizer must consume adapter-native structures. ([Google Cloud Documentation][11])                  |
| Metadata cost         | Many `SHOW` commands require no running warehouse, but remain identity-scoped  | SQL connector targets compute; exact probe cost must be verified per probe                       | `INFORMATION_SCHEMA` queries are billable or consume slots, with a 10 MB on-demand minimum and no result cache | Tier A cannot mean universally free. ([Snowflake Documentation][12])                                         |
| Programmatic metadata | Snowflake row layouts                                                          | Databricks recommends JSON form because human-readable `DESCRIBE` output can change              | APIs and Information Schema expose typed resources                                                             | Adapters own result decoding and may use SQL or APIs. ([Databricks Documentation][13])                       |

This comparison does **not** constitute Databricks or BigQuery support. It is a contract-shaping exercise.

---

# 11. Growth-friendly architecture beyond warehouses

Warehouse portability is the highest-priority extension axis, but it is not the only one.

## 11.1 Warehouse backends: public plugin surface at initial release

This should be the only initially public Python plugin contract.

Deliver with:

* entry-point discovery;
* adapter API versioning;
* conformance test kit;
* capability inspection;
* a fake external distribution used in wheel tests;
* built-in Snowflake backend;
* contributor documentation;
* no second production backend.

## 11.2 Diagnostic rules: internal extension surface initially

Current classifiers are tightly coupled to mutable `DiagnosticFinding` objects. Replace them with deterministic rules:

```python
class DiagnosticRule(Protocol):
    rule_id: str
    priority: int

    def observe(
        self,
        result: RunResultView,
        context: ArtifactContext,
        backend: WarehouseBackend,
    ) -> tuple[DiagnosticObservation, ...]: ...
```

Rules should:

* produce observations, not fixes;
* not execute probes;
* declare applicable dbt statuses;
* have deterministic priority and conflict behavior;
* retain raw evidence references.

Do not expose third-party classifier entry points at the first release. Stabilize observations and resolution semantics first.

## 11.3 Evidence sources: first-class provider model

Warehouse evidence is only one evidence source.

The same model can later support:

* current and previous manifests;
* catalog artifacts;
* `sources.json`;
* structured dbt logs;
* attested run identity;
* warehouse metadata;
* optional Tier-B scans.

Every evidence source returns the same `EvidenceRecord` envelope. This prevents each new artifact or live source from creating another mutation pass.

## 11.4 Artifact sources

The engine should receive an `ArtifactBundle`, not filesystem paths.

```python
class ArtifactSource(Protocol):
    def load(self) -> ArtifactBundle: ...
```

Initial implementation:

```text
LocalArtifactSource
```

Future implementations can include:

```text
StdinArtifactSource
ArchiveArtifactSource
DbtPlatformArtifactSource
ObjectStorageArtifactSource
```

These should remain internal until credential, caching and provenance behavior is stable.

## 11.5 Execution-correlation strategies

Query-history correlation varies by warehouse and by available evidence.

Adapters should provide a strategy chain such as:

```text
adapter statement ID
query tag or invocation marker
exact statement fingerprint
bounded time/text correlation
attested run identity
```

Each strategy records fidelity and failure reason. The core should never silently fall from exact ID correlation to approximate text matching without reporting that downgrade.

## 11.6 Cost policy

Cost control is a policy, not a warehouse method.

```python
@dataclass(frozen=True)
class ProbeBudget:
    allow_metadata: bool
    allow_data_scans: bool
    maximum_scan_requests: int
    maximum_estimated_bytes: int | None
    maximum_lineage_depth: int
```

The adapter estimates or characterizes cost; the core policy approves or rejects requests.

This retains Tier A/Tier B while acknowledging that BigQuery metadata queries can be billable and Databricks metadata may consume SQL compute. ([Google Cloud Documentation][14])

## 11.7 Remedy providers

Platform-neutral resolution and platform-specific repair instructions must be separate.

Core can conclude:

```text
execution principal lacks confirmed create capability
```

The Snowflake adapter may render:

```sql
GRANT USAGE ON DATABASE ...
GRANT USAGE ON SCHEMA ...
GRANT CREATE TABLE ON SCHEMA ...
```

A future BigQuery adapter would instead describe IAM roles or policies. A Databricks adapter would use Unity Catalog privileges.

## 11.8 Output exporters

The canonical report document enables future output formats without changing diagnosis:

```python
class ReportExporter(Protocol):
    format_name: str

    def export(self, report: CanonicalReport) -> str | bytes: ...
```

Initial release:

* canonical JSON;
* terminal text.

Potential later exporters:

* Markdown;
* SARIF-like integration;
* incident-ticket payloads;
* HTML;
* telemetry events.

Do not expose exporter entry points until redaction and report schema are stable.

## 11.9 Redaction and disclosure policy

Redaction belongs between resolution and report assembly, not in individual renderers.

```python
@dataclass(frozen=True)
class RedactionPolicy:
    include_query_text: bool = False
    include_object_names: bool = True
    include_principals: bool = False
    include_literals: bool = False
```

The canonical document should record that data was omitted:

```json
{
  "redactions": [
    {
      "field": "query_text",
      "reason": "default_sensitive_sql_policy"
    }
  ]
}
```

## 11.10 Contributor conformance kit

Publish an adapter test kit under:

```text
dbt_diagnostics.testing.adapters
```

It should validate:

* plugin descriptor and API version;
* capability consistency;
* relation parse/render round-trip;
* quoted-identifier behavior;
* normalized error stability;
* every declared capability has a provider;
* unsupported capability behavior;
* no connector import during offline discovery;
* typed JSON serialization;
* failed/not-visible/unknown distinctions;
* connection cleanup;
* no Tier-B execution without approval.

This is more valuable for open-source participation than a large informal protocol.

---

# 12. Revised migration sequence

## Strict total order

| Order | Issue               | Scope                                                                                           | Effort   | Risk     |
| ----: | ------------------- | ----------------------------------------------------------------------------------------------- | -------- | -------- |
|     1 | **NEW W0**          | Freeze current Snowflake public-output and probe-call baselines                                 | S        | Low      |
|     2 | **#67 modified**    | Validated artifact context and indexes; raw adapter-response view                               | M        | Medium   |
|     3 | **NEW W1**          | Active backend registry, relation codec, dialect, error normalizer and adapter-response decoder | L        | High     |
|     4 | **#61 modified**    | Edge-preserving warehouse-neutral lineage graph                                                 | L        | High     |
|     5 | **#57 modified**    | Generic config/profile selection and validation boundary                                        | M        | Medium   |
|     6 | **#64 modified**    | Explicit live mode, `--warehouse`, standalone artifacts                                         | M        | Medium   |
|     7 | **NEW W2**          | Snowflake profile validation and connection factory behind backend                              | M        | High     |
|     8 | **#55 modified**    | Snowflake query-history and execution-identity providers                                        | M-L      | High     |
|     9 | **#54 modified**    | Snowflake relation/column/visibility provider                                                   | L        | High     |
|    10 | **NEW W3**          | Snowflake privilege and session-context providers                                               | L        | High     |
|    11 | **#62 modified**    | Observations, typed evidence and one resolver; remove prose mutation                            | L        | High     |
|    12 | **NEW W4**          | Snowflake type semantics and remedy provider                                                    | M-L      | High     |
|    13 | **#56 modified**    | Structured symptom/root-cause grouping                                                          | M-L      | High     |
|    14 | **#63 modified**    | Canonical report document and terminal projection                                               | L        | High     |
|    15 | **NEW W5**          | Snowflake sole-path cutover, plugin discovery and legacy removal                                | M-L      | High     |
|    16 | **#66 modified**    | Live Snowflake verification and adapter conformance evidence                                    | M        | High     |
|    17 | **#59 / #65 / #33** | Offline gates, package/legal baseline, release                                                  | Existing | Existing |

## Dependency DAG

```text
W0
 |
#67
 |
W1 ------------------+
 |                   |
#61                #57
 |                   |
 |                 #64
 |                   |
 +------------------ W2
                      |
                     #55
                      |
                     #54
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
                     W5
                      |
                     #66
                      |
                  #59/#65/#33
```

## Parallel work

* #57 can run in parallel with #61 after #67.
* #65 can run in parallel with most architecture work.
* Real fixture capture for #52 can run whenever Snowflake access is available.
* Documentation for adapter contributors can begin after W1’s contract is merged, but must describe later steps as target state until they land.

## Critical path

```text
W0 -> #67 -> W1 -> W2 -> #55 -> #54 -> W3
   -> #62 -> W4 -> #56 -> #63 -> W5 -> #66 -> release
```

---

# 13. Migration rules and compatibility shims

## Permitted shim

During extraction, existing import paths may re-export moved Snowflake functions:

```python
# dbt_diagnostics/enrichers/query_history.py
from dbt_diagnostics.adapters.snowflake.probes.query_history import (
    SnowflakeQueryHistoryProvider,
)
```

The package runtime must not call that old module.

## Forbidden shim

This is prohibited:

```python
new_evidence_collector.collect(...)
legacy_enrich_reports(...)
```

Only one path may execute a capability for a finding.

## Capability-by-capability cutover

Each PR must:

1. add the adapter implementation;
2. switch every runtime caller for that capability;
3. remove the old runtime call;
4. retain only a documented import shim if required;
5. add a probe-count assertion proving no duplicate execution;
6. preserve golden JSON;
7. name the shim-removal issue.

## Shim removal

W5 removes:

* old `LiveObjectProbe`;
* runtime imports from `enrichers`;
* direct Snowflake functions from generic modules;
* compatibility re-exports not covered by an explicit deprecation policy;
* duplicate Snowflake constants;
* generic adapter-response query-ID accessors.

---

# 14. Golden parity and rollback

## W0 baseline

Before extraction, capture:

* public JSON for every diagnosis class;
* terminal output derived from the same fixture;
* offline and mocked-live outputs;
* root-cause group membership;
* evidence wording and confidence;
* probe request count and stable query fingerprints;
* redaction behavior.

These baselines characterize current Snowflake behavior. Known incorrect behavior should have explicit expected-failure or correction issues, not silently become the parity target.

## Per-PR rollback

Every adapter extraction PR has a clean rollback boundary because it switches one capability:

* W1: pure interpretation and dialect;
* W2: connection creation;
* #55: query history and identity;
* #54: relation and columns;
* W3: privileges and session;
* W4: remedies.

Rollback means reverting that PR, not enabling both paths.

## Final parity

W5 must prove:

```text
pre-extraction public JSON
    ==
post-extraction canonical JSON compatibility projection
```

except for:

* explicitly approved correctness fixes;
* additive adapter provenance and capability fields;
* approved redaction changes.

---

# 15. Tracker revisions

## New epic

```markdown
# [Epic] Warehouse-neutral diagnostic engine and Snowflake adapter release gate

## Thesis

The first public release supports Snowflake only, but the diagnostic core must
contain no Snowflake implementation or semantic assumptions.

Snowflake support is provided by a built-in warehouse backend selected through
the same versioned plugin contract available to future warehouse packages.
This epic does not add Databricks, BigQuery, or any other supported warehouse.

## Release definition of done

- [ ] Generic modules import no Snowflake implementation.
- [ ] Generic modules contain no Snowflake SQL, error codes, identifier rules,
      profile fields, connector types, tuple decoding, type semantics, or fixes.
- [ ] The active runtime receives a selected WarehouseBackend.
- [ ] Snowflake is the only live backend implementation and the sole live path.
- [ ] No old and new probe path runs against the same finding.
- [ ] Offline artifact analysis imports no optional connector and discovers no
      credentials.
- [ ] Adapter-response decoding is backend-owned.
- [ ] Relation parsing and SQLGlot dialect selection are backend-owned.
- [ ] Evidence preserves confirmed, not-found, not-visible, failed,
      unsupported, and unknown states.
- [ ] Canonical JSON parity is proven before and after extraction.
- [ ] Terminal output is a projection of canonical JSON.
- [ ] Offline adapter-contract tests run on every PR.
- [ ] Real Snowflake verification proves live parity before release.
- [ ] Entry-point discovery and adapter API version checks are tested from an
      installed wheel.
- [ ] README states Snowflake-only compatibility without implying support for
      other warehouses.

## Build order

- [ ] W0 - freeze Snowflake output and probe-call baselines
- [ ] #67 - validated artifact context and indexes
- [ ] W1 - active backend SPI for errors, relations, dialect and adapter response
- [ ] #61 - edge-preserving lineage
- [ ] #57 - config/profile validation
- [ ] #64 - explicit live mode and backend selection
- [ ] W2 - Snowflake connection factory
- [ ] #55 - Snowflake query history and execution identity
- [ ] #54 - Snowflake relation and column inspection
- [ ] W3 - Snowflake privilege and session inspection
- [ ] #62 - observations, evidence and final resolution
- [ ] W4 - Snowflake type semantics and remedies
- [ ] #56 - structured grouping
- [ ] #63 - canonical report document
- [ ] W5 - sole-path cutover and legacy removal
- [ ] #66 - live Snowflake and adapter-conformance verification

## Relationship to existing epics

- #4 owns live-verification correctness and release behavior.
- #48 owns artifact compatibility and validated views.
- This epic owns dependency inversion and warehouse isolation.

## Constraints

- One issue per PR.
- No second production warehouse implementation in this epic.
- No lowest-common-denominator evidence model.
- No generic execute(sql) adapter method.
- No Tier-B probe without explicit cost approval.
```

---

# 16. New child-issue drafts

## W0

```markdown
# test: freeze Snowflake output and probe-call parity before adapter extraction

## Type

Test / CI / fixtures

## Labels

test, architecture, snowflake, priority: now

## Parent epic

Warehouse-neutral diagnostic engine and Snowflake adapter release gate

## Summary

Capture the current public Snowflake behavior before moving implementation
behind warehouse boundaries.

This is a characterization and parity issue, not an endorsement of known
incorrect behavior.

## Offline behavior

Run every committed failure family through artifact-only diagnosis and store:

- public JSON;
- terminal projection;
- report IDs;
- group membership;
- lineage;
- remedies and confidence;
- redaction metadata.

## Mocked-live behavior

Use recorded Snowflake rows to store:

- typed probe outcomes;
- request counts;
- stable query fingerprints;
- evidence provenance;
- final JSON.

## Acceptance criteria

- [ ] Every diagnosis class has an offline golden JSON document.
- [ ] Every live capability has a recorded-row golden case.
- [ ] Terminal parity is asserted against the same semantic document.
- [ ] Probe-count tests detect duplicate live execution.
- [ ] Known correctness defects are identified by issue number rather than
      silently frozen as desired behavior.
- [ ] No credentials, unredacted SQL literals, or private identifiers are
      committed.
- [ ] No runtime behavior changes in this issue.

## Files touched

- `dbt_diagnostics/tests/golden/**`
- `dbt_diagnostics/tests/adapter_rows/snowflake/**`
- parity-test helpers

## Dependencies

None.

## Release target

Initial release.
```

## W1

````markdown
# refactor: make the warehouse backend SPI the active interpretation path

## Type

Refactor

## Labels

architecture, snowflake, priority: now

## Parent epic

Warehouse-neutral diagnostic engine and Snowflake adapter release gate

## Summary

Introduce the versioned warehouse-backend SPI and immediately use it for:

- backend selection;
- relation parsing and canonicalization;
- SQLGlot dialect selection;
- dbt adapter-response decoding;
- warehouse error normalization.

This issue must not add an unused facade.

## Target structure

```text
CLI -> backend registry -> selected WarehouseBackend
classifiers -> ErrorNormalizer protocol
column tracer -> backend dialect
artifact context -> AdapterResponseDecoder protocol
lineage/grouping -> opaque RelationRef canonical keys
````

## Compatibility

Snowflake remains the default and only compatible backend.

Existing public JSON keys remain unchanged. Adapter provenance fields may be
added only additively.

## Acceptance criteria

* [ ] The Snowflake backend is selected and passed into the active engine.
* [ ] Runtime classifiers consume `NormalizedWarehouseError`.
* [ ] Generic classifiers contain no Snowflake numeric error codes.
* [ ] `ColumnTracer` contains no hardcoded Snowflake dialect.
* [ ] Generic code never splits or uppercases physical relation names.
* [ ] `query_id` and other Snowflake response fields are decoded only by the
  Snowflake backend.
* [ ] A capability-sparse fake backend completes artifact-only diagnosis.
* [ ] An installed fake external distribution is discoverable by entry point.
* [ ] Generic modules import no `adapters.snowflake`.
* [ ] Golden JSON remains equivalent.
* [ ] No live SQL is moved or duplicated in this issue.

## Files touched

* new `dbt_diagnostics/api/v1/**`
* new `dbt_diagnostics/adapters/registry.py`
* new pure Snowflake backend modules
* classifiers
* column tracer
* artifact views
* CLI composition root
* import-graph tests

## Dependencies

W0 and #67.

## Release target

Initial release.

````

## W2

```markdown
# refactor: move Snowflake profile validation and connection creation behind the backend

## Type

Refactor

## Labels

architecture, live, snowflake, priority: now

## Parent epic

Warehouse-neutral diagnostic engine and Snowflake adapter release gate

## Summary

Move all Snowflake target fields, authentication handling, connector imports,
and connection construction behind `WarehouseConnectionFactory`.

Generic code locates and selects a raw dbt profile target. The selected backend
validates and interprets it.

## Offline behavior

- No Snowflake connector import.
- No dotenv or profile discovery unless explicitly needed.
- Artifact-only diagnosis remains available with the built-in pure Snowflake
  backend.

## Live behavior

- Explicit `--live`.
- The profile output type must match the selected backend.
- The returned session is opaque to the engine.
- Connection failure becomes structured live-degradation evidence.

## Acceptance criteria

- [ ] Generic code contains no Snowflake profile field names.
- [ ] Generic code imports no `snowflake.connector`.
- [ ] Snowflake connector is imported only inside the Snowflake connection
      factory.
- [ ] Password, key-pair, authenticator, OAuth and other supported Snowflake
      target handling remain backend-owned.
- [ ] Backend/profile mismatch fails clearly before connection.
- [ ] Offline execution proves no connector/profile/dotenv call occurs.
- [ ] Connection cleanup is reliable.
- [ ] Golden JSON remains equivalent.
- [ ] The old connection helper is no longer an active runtime path.

## Files touched

- Snowflake profile and connection modules
- adapter registry
- CLI live composition
- `pyproject.toml`
- connection tests

## Dependencies

W1, #57 and #64.

## Release target

Initial release.
````

## W3

```markdown
# refactor: move Snowflake privilege and session-context evidence behind capabilities

## Type

Refactor

## Labels

architecture, live, snowflake, correctness, priority: now

## Parent epic

Warehouse-neutral diagnostic engine and Snowflake adapter release gate

## Summary

Move Snowflake privilege, effective-access and session-parameter behavior into
capability-specific providers.

Generic code requests access intents and semantic settings. It does not name
Snowflake roles, grants, warehouses or parameters.

## Offline behavior

Requests remain in the canonical report as unverified confirmation steps.

## Live behavior

Tier-A metadata only. Evidence records:

- status;
- observed identity;
- direct and inherited access information;
- database/schema/object prerequisites;
- setting value and source level;
- query failure separately from negative evidence.

## Acceptance criteria

- [ ] Generic code contains no `SHOW GRANTS`.
- [ ] Generic code contains no Snowflake parameter names.
- [ ] Database USAGE, schema USAGE, object privilege and create privilege remain
      separate.
- [ ] Query failure is not interpreted as no access.
- [ ] Direct and inherited evidence are distinguishable.
- [ ] Session-setting evidence uses semantic setting IDs.
- [ ] Every cursor is closed.
- [ ] Old and new providers never run together.
- [ ] Golden JSON remains equivalent or changes only for an approved
      correctness fix.

## Files touched

- Snowflake privilege provider
- Snowflake session provider
- evidence planning
- live collector
- tests and recorded rows

## Dependencies

#55 and #54.

## Release target

Initial release.
```

## W4

```markdown
# refactor: move Snowflake type semantics and generated remedies out of core

## Type

Refactor

## Labels

architecture, snowflake, correctness, priority: now

## Parent epic

Warehouse-neutral diagnostic engine and Snowflake adapter release gate

## Summary

Remove Snowflake types, parameter explanations, SQL casts, GRANT statements,
warehouse commands and other platform-specific remedies from generic
classifiers and resolvers.

The Snowflake backend contributes typed evidence requests and remedy candidates.

## Acceptance criteria

- [ ] Generic diagnostics contain no `TIMESTAMP_LTZ`, `TIMESTAMP_NTZ`,
      `TIMESTAMP_TYPE_MAPPING`, `NUMBER(38,0)`, Snowflake maximum VARCHAR size,
      `IFF`, `ALTER WAREHOUSE`, `SHOW`, or `GRANT`.
- [ ] Generic timeout diagnosis requests semantic timeout evidence.
- [ ] Generic access diagnosis produces an access-intent observation.
- [ ] Snowflake remedies retain all currently useful Snowflake detail.
- [ ] Remedies are structured and serialized before terminal rendering.
- [ ] Remedies identify required privileges and probe tier.
- [ ] Unknown or failed evidence cannot produce confirmed wording.
- [ ] Golden Snowflake output remains equivalent except approved corrections.

## Files touched

- Snowflake evidence planner
- Snowflake remedy provider
- contract/data/timeout/runtime diagnostics
- final resolver
- canonical report serializers
- templates

## Dependencies

#62 and W3.

## Release target

Initial release.
```

## W5

```markdown
# refactor: make the Snowflake backend the sole warehouse path and remove legacy coupling

## Type

Refactor

## Labels

architecture, live, snowflake, test, priority: now

## Parent epic

Warehouse-neutral diagnostic engine and Snowflake adapter release gate

## Summary

Complete the extraction by removing legacy warehouse execution paths and
proving that the built-in Snowflake backend is the sole active implementation.

## Acceptance criteria

- [ ] No generic module imports `adapters.snowflake`.
- [ ] No generic module contains Snowflake codes, SQL, types, profile fields,
      identifier rules, tuple decoding or fixes.
- [ ] No package runtime path calls legacy `enrichers` functions.
- [ ] `LiveObjectProbe` is removed.
- [ ] Compatibility re-exports are removed or documented under a real
      deprecation policy.
- [ ] An AST/import guard enforces dependency direction.
- [ ] A token/string guard detects new Snowflake leakage outside allowed paths.
- [ ] A fake capability-sparse backend runs the engine without Snowflake.
- [ ] A separately packaged fake backend loads through the entry-point API.
- [ ] Public Snowflake JSON parity passes.
- [ ] Probe counts prove no duplicate execution.
- [ ] Installed-wheel offline mode imports no Snowflake connector.
- [ ] README says Snowflake-only compatibility and documents the adapter API
      without implying other warehouse support.

## Files touched

- legacy `enrichers/**`
- adapter registry
- import guards
- packaging metadata
- contributor adapter documentation
- parity tests

## Dependencies

#63 and W4.

## Release target

Initial release.
```

---

# 17. Existing issue dispositions under the revised plan

| Issue | Revised disposition                                                                                                                                                           |
| ----: | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
|    #4 | **KEEP OPEN — MODIFY.** Add the warehouse-neutral release epic as a mandatory release dependency.                                                                             |
|   #54 | **SPLIT / KEEP OPEN — MODIFY.** Retain relation/column/visibility evidence; move privilege/session scope to W3. Implement through Snowflake providers, not generic enrichers. |
|   #55 | **KEEP OPEN — MODIFY.** Implement query history and execution identity directly under the Snowflake backend.                                                                  |
|   #56 | **KEEP OPEN — MODIFY.** Consume final structured resolutions and opaque canonical relation keys.                                                                              |
|   #57 | **KEEP OPEN — MODIFY.** Generic code validates config shape and selects a raw target; adapter validates target-specific fields.                                               |
|   #58 | **KEEP OPEN — MODIFY.** Replace Snowflake recovery prose with semantic capability IDs. Remove generic `query_id`/`rows_affected` assumptions.                                 |
|   #61 | **KEEP OPEN — MODIFY.** Lineage stores `RelationRef`; live evidence annotates nodes without changing graph topology.                                                          |
|   #62 | **KEEP OPEN — MODIFY.** Define the warehouse-neutral observation/evidence/resolution model. Generic core must import no implementation.                                       |
|   #63 | **KEEP OPEN — MODIFY.** Include backend descriptor, capability snapshot, typed evidence, adapter extensions and redaction metadata.                                           |
|   #64 | **KEEP OPEN — MODIFY.** Add explicit `--warehouse`; make offline default safe; backend selection is composition-root behavior.                                                |
|   #66 | **KEEP OPEN — MODIFY.** Add adapter-contract conformance, sole-runtime-path proof and plugin-discovery wheel test before live parity is declared.                             |
|   #67 | **KEEP OPEN — MODIFY.** Expose raw adapter-response data through the view; backend decoder produces normalized execution metadata.                                            |
|   #59 | **KEEP OPEN.** Add import-boundary, fake-backend and installed-plugin tests to offline release gates.                                                                         |
|   #65 | **KEEP OPEN.** Compatibility table must say “Snowflake supported; adapter API available; other warehouses unsupported.”                                                       |
|   #33 | **KEEP OPEN.** Publishing remains blocked by W5 and #66.                                                                                                                      |
| #5/#6 | **KEEP POST-RELEASE.** Tier-B SQL must be generated/executed by backend providers.                                                                                            |
| #8/#9 | **KEEP POST-RELEASE.** Warehouse-specific evidence and remedies must use the backend extension points.                                                                        |
|   #15 | **KEEP DEFERRED.** Any identity-attestation mechanism becomes an adapter correlation strategy.                                                                                |

The existing tracker already treats #62 as the observations/evidence/resolution issue, #63 as canonical-report ownership, #64 as explicit live behavior, #66 as real Snowflake verification and #67 as indexed artifact views. Those issue boundaries remain useful but need the warehouse-neutral amendments above.

---

# 18. Test strategy

## Core tests

* Engine runs with no backend session.
* Engine runs with a capability-sparse fake backend.
* No core test imports Snowflake classes.
* Observation and resolution tests use generic evidence.
* Branching lineage tests preserve real edges.
* Canonical report tests contain no renderer-derived semantics.

## Adapter contract tests

Each adapter implementation must pass:

```text
descriptor
API compatibility
profile validation
offline import safety
relation parsing
relation render round-trip
canonical key stability
quoted identifiers
error normalization
adapter-response decoding
capability consistency
typed evidence serialization
failed/not-visible/not-found distinctions
session cleanup
unsupported capability behavior
cost declaration
remedy serialization
```

## Snowflake recorded-row tests

Recorded and scrubbed rows for:

* `SHOW OBJECTS` or chosen metadata path;
* table, view and materialized-view metadata;
* `DESCRIBE`;
* query-history successful and failed states;
* direct and inherited roles;
* database/schema/object/create privileges;
* session parameter levels;
* connector exceptions;
* quoted and mixed-case identifiers.

## Fake external plugin test

CI builds a tiny separate distribution:

```text
dbt-diagnostics-test-backend
```

It registers an entry point and is installed into the wheel-smoke environment. This proves discovery works outside the main source tree.

## Import/leakage guard

Scan generic source for prohibited imports and platform tokens.

Allowed Snowflake references:

```text
dbt_diagnostics/adapters/snowflake/**
dbt_diagnostics/tests/adapters/snowflake/**
docs explicitly discussing Snowflake
README support statement
packaging extra names
```

Disallowed outside those paths:

```text
snowflake.connector
002003
000904
003001
SHOW TABLES
SHOW GRANTS
TIMESTAMP_TYPE_MAPPING
dialect="snowflake"
```

The guard is not the primary proof, but it prevents accidental regression.

## Live Snowflake release verification

Before parity is declared:

* separate diagnostic and run identities;
* visible, hidden and absent relations;
* tables, views and quoted relations;
* query-ID correlation and failed query states;
* direct and inherited privilege cases;
* session parameter source levels;
* connector tuple and exception shapes;
* canonical JSON output;
* probe-count verification;
* no Tier-B data scans.

#66 already correctly identifies most of this real-account evidence as a release prerequisite.

---

# 19. Final file-impact matrix

| Current file or package         | Final impact                                                                                                |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `main.py`                       | Reduced to compatibility entry point or split into `cli/` and engine composition.                           |
| `models.py`                     | Split into warehouse-neutral domain/report models.                                                          |
| `root_cause.py`                 | Becomes generic resolver/grouping logic; `LiveObjectProbe` removed.                                         |
| `grouping.py`                   | Uses normalized observations and final resolution signatures.                                               |
| `renderer.py`                   | Accepts canonical report only.                                                                              |
| `classifiers/base.py`           | Receives `ArtifactContext` and selected backend contracts.                                                  |
| `runtime_error.py`              | Consumes normalized errors; no Snowflake regexes or remedies.                                               |
| `data_error.py`                 | Generic categories only; Snowflake types/remedies removed.                                                  |
| `timeout_error.py`              | Generic timeout observation; no warehouse parameter or DDL.                                                 |
| `contract_violation.py`         | Generic contract observation; adapter contributes type semantics.                                           |
| `schema_change_error.py`        | Evidence-calibrated generic schema hypothesis.                                                              |
| `test_failure.py`               | Uses adapter-decoded execution metadata and `RelationRef`.                                                  |
| `column_tracer.py`              | Receives dialect; no Snowflake hardcoding.                                                                  |
| `dag_walker.py`                 | Edge-preserving graph; no string-splitting/uppercasing relation logic.                                      |
| `compat/safe.py`                | Generic artifact aliases only; no Snowflake query-ID accessor.                                              |
| `compat/consumed_paths.py`      | Semantic recovery capability IDs, not Snowflake SQL prose.                                                  |
| `enrichers/connection.py`       | Moved to Snowflake adapter or retained briefly as re-export.                                                |
| `enrichers/schema_inspector.py` | Replaced by Snowflake relation/column providers.                                                            |
| `enrichers/query_history.py`    | Replaced by Snowflake query-history provider.                                                               |
| `enrichers/run_identity.py`     | Replaced by Snowflake identity provider.                                                                    |
| `enrichers/grants.py`           | Replaced by Snowflake privilege provider.                                                                   |
| `enrichers/params.py`           | Replaced by Snowflake session provider.                                                                     |
| `enrichers/enrich.py`           | Replaced by generic planner/collector/resolver pipeline.                                                    |
| templates                       | Render structured remedies and evidence; contain no generated Snowflake SQL logic.                          |
| `pyproject.toml`                | Adds backend entry point and `snowflake` optional extra; retains `live` alias if compatibility requires it. |
| tests                           | Split into core, generic adapter contracts, Snowflake adapter, fake external plugin and golden parity.      |

---

# Final release boundary

The first public release is ready only when:

1. The warehouse-neutral engine is complete.
2. The Snowflake backend is the sole active warehouse path.
3. The adapter API and external discovery mechanism are tested.
4. Snowflake canonical JSON parity is established.
5. Real Snowflake evidence semantics are verified.
6. BigQuery and Databricks remain explicitly unsupported.
7. A future adapter can be delivered as a separate Python distribution without modifying the diagnostic engine.

That release boundary is stricter than the previous plan, but it better matches the project’s open-source intent and avoids asking future contributors to first excavate Snowflake assumptions from core code.

[1]: https://docs.getdbt.com/reference/artifacts/run-results-json "https://docs.getdbt.com/reference/artifacts/run-results-json"
[2]: https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/ "https://packaging.python.org/en/latest/guides/creating-and-discovering-plugins/"
[3]: https://docs.snowflake.com/en/developer-guide/python-connector/python-connector "https://docs.snowflake.com/en/developer-guide/python-connector/python-connector"
[4]: https://docs.databricks.com/aws/en/data-governance/unity-catalog/access-control/permissions-concepts "https://docs.databricks.com/aws/en/data-governance/unity-catalog/access-control/permissions-concepts"
[5]: https://docs.snowflake.com/en/sql-reference/identifiers-syntax "https://docs.snowflake.com/en/sql-reference/identifiers-syntax"
[6]: https://docs.snowflake.com/en/en/sql-reference/info-schema/tables "https://docs.snowflake.com/en/en/sql-reference/info-schema/tables"
[7]: https://docs.snowflake.com/en/sql-reference/info-schema "https://docs.snowflake.com/en/sql-reference/info-schema"
[8]: https://docs.databricks.com/data-governance/unity-catalog/manage-privileges/privileges.html "https://docs.databricks.com/data-governance/unity-catalog/manage-privileges/privileges.html"
[9]: https://docs.snowflake.com/en/sql-reference/sql/show-grants "https://docs.snowflake.com/en/sql-reference/sql/show-grants"
[10]: https://docs.snowflake.com/en/sql-reference/parameters "https://docs.snowflake.com/en/sql-reference/parameters"
[11]: https://docs.cloud.google.com/bigquery/docs/error-messages "https://docs.cloud.google.com/bigquery/docs/error-messages"
[12]: https://docs.snowflake.com/en/en/sql-reference/sql/show-tables "https://docs.snowflake.com/en/en/sql-reference/sql/show-tables"
[13]: https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-describe-table "https://docs.databricks.com/aws/en/sql/language-manual/sql-ref-syntax-aux-describe-table"
[14]: https://docs.cloud.google.com/bigquery/docs/information-schema-intro?hl=en "https://docs.cloud.google.com/bigquery/docs/information-schema-intro?hl=en"
