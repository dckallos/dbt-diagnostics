## Brief reconciliation

Both reports’ overlapping findings are confirmed by the code: flat lineage lists are treated as paths; `table_exists() -> None` becomes “missing”; grant failures look like negative access facts; `DiagnosticFinding` is an overloaded mutable record; enrichment/root-cause/grouping/rendering can produce duplicate or conflicting narratives. OUTPUT_TWO’s ordered refactor path matches those highest-confidence items.  

One-report findings, checked against code:

* OUTPUT_ONE: grouping by `error_class:schema` can group unrelated runtime errors — confirmed in `grouping.group_reports()`.
* OUTPUT_ONE: JSON omits live enrichment, live lineage state, and diff — confirmed in `DiagnosticReport._finding_to_dict()` and `to_json_dict()`.
* OUTPUT_ONE: role/object SQL interpolation is unsafe/inexact — confirmed in `grants.py` and `schema_inspector.table_exists()`.
* OUTPUT_ONE: explicit artifact paths still require a dbt project — confirmed in `_resolve_from_args()` ordering.
* OUTPUT_ONE: live default plus `.env` autodiscovery is a trust/product risk — confirmed, but treat as policy/CLI follow-up.
* OUTPUT_TWO: `safe.py` does not derive from `REGISTRY` and registry is incomplete — confirmed.
* OUTPUT_TWO: no current import cycles and package-level decomposition is worth keeping — confirmed.
* OUTPUT_TWO: classifier registry/local `if` dispatch is not the main problem — confirmed.
* OUTPUT_TWO: `parse_profile()` / `.env` discovery duplication and `_is_lagging()` unreachable tail — confirmed.
* I found no report-only claim that conflicts with the pasted source.

Rewrite verdict: **OUTPUT_TWO wins — the code supports a substantial subsystem refactor, not a package rewrite and not just local cleanup.** 

---

# Wave 1 — correctness-critical, shippable fixes

## 1. Preserve live probe failure as unknown

**Location:** `enrich.py` (`dbt_diagnostics.enrichers.enrich`), `_enrich_lineage_trail`, `_is_failing`; `models.py`, `LineageStep.status_*`.

**Source:** both.

**Before:**

```python
exists = table_exists(conn, step.relation_name)
...
if exists:
    step.live_status = "exists"
    ...
else:
    step.live_status = "missing"
    step.live_detail = "table does NOT exist in Snowflake"
```

**After:**

```python
# models.py, LineageStep
live_status: Optional[str] = None  # "exists", "missing", "no_column", "unknown"

@property
def status_emoji(self) -> str:
    if self.live_status == "exists":
        return "\u2705"
    if self.live_status == "missing":
        return "\u274c"
    if self.live_status == "no_column":
        return "\u26a0\ufe0f"
    if self.live_status == "unknown":
        return "\u2753"
    if self.run_status == "error":
        return "\u274c"
    if self.run_status == "pass":
        return "\u2705"
    if self.run_status == "skipped":
        return "\u23ed\ufe0f"
    if self.manifest_status == "declared":
        return "\u2705"
    if self.manifest_status == "not_found":
        return "\u274c"
    return "\u2753"

@property
def status_text(self) -> str:
    if self.live_status == "exists":
        return "[PASS]"
    if self.live_status == "missing":
        return "[FAIL]"
    if self.live_status == "no_column":
        return "[WARN]"
    if self.live_status == "unknown":
        return "[????]"
    if self.run_status == "error":
        return "[FAIL]"
    if self.run_status == "pass":
        return "[PASS]"
    if self.run_status == "skipped":
        return "[SKIP]"
    if self.manifest_status == "declared":
        return "[PASS]"
    if self.manifest_status == "not_found":
        return "[FAIL]"
    return "[????]"
```

```python
# enrich.py, _enrich_lineage_trail
exists = table_exists(conn, step.relation_name)

if exists is None:
    step.live_status = "unknown"
    step.live_detail = "existence check could not be verified"
    continue

if exists is True:
    step.live_status = "exists"
    if finding.target_identifier:
        try:
            cols = describe_table(conn, step.relation_name)
            if cols:
                col_names = [c.name.upper() for c in cols]
                target_upper = finding.target_identifier.upper()
                if target_upper in col_names:
                    step.live_detail = f"column '{finding.target_identifier}' found"
                else:
                    step.live_status = "no_column"
                    step.live_detail = (
                        f"column '{finding.target_identifier}' NOT found"
                    )
        except Exception:
            step.live_detail = "table exists (column check failed)"
    else:
        step.live_detail = "table exists"
else:
    step.live_status = "missing"
    step.live_detail = "table does NOT exist in Snowflake"
```

```python
# enrich.py, _is_failing
def _is_failing(step) -> bool:
    """A step is failing if live/manifest/run indicate absence or error."""
    if step.live_status == "unknown":
        return False
    if step.live_status in ("missing", "no_column"):
        return True
    if step.run_status == "error":
        return True
    if step.manifest_status in ("not_found", "missing"):
        return True
    return False
```

**Why safe:** This only stops converting failed probes into negative facts. Confirmed `True` and `False` behavior is preserved.

**Test:** `robustness`: monkeypatch `table_exists()` to return `None`; today the step becomes `missing`; after patch it becomes `unknown` and no high-confidence disconnect is created.

**Effort/risk:** small; no dependency.

---

## 2. Make grant probe failure explicit before root-cause verdicts

**Location:** `grants.py`, `check_role_grants`; `root_cause.py`, `_apply_verdict` branches for `exists is False` and `exists is None`.

**Source:** both.

**Before:**

```python
except Exception:
    # If SHOW GRANTS fails (e.g., role doesn't exist), return empty result
    pass

return {
    "has_access": has_access,
    "grants_found": grants_found,
    "role_checked": role_name,
}
```

**After:**

```python
# grants.py
def check_role_grants(conn, role_name: str, target_object: str) -> dict:
    grants_found: list[str] = []
    has_access = False
    query_succeeded = False
    error = None
    cursor = None

    try:
        cursor = conn.cursor()
        cursor.execute(f"SHOW GRANTS TO ROLE {role_name}")
        rows = cursor.fetchall()
        query_succeeded = True

        target_upper = target_object.upper()
        for row in rows:
            privilege = row[1] if len(row) > 1 else ""
            granted_on = row[2] if len(row) > 2 else ""
            name = row[3] if len(row) > 3 else ""

            if target_upper in name.upper():
                grant_desc = f"{privilege} on {granted_on} {name}"
                grants_found.append(grant_desc)
                if privilege.upper() in ("SELECT", "USAGE", "ALL", "OWNERSHIP"):
                    has_access = True

            parts = target_upper.split(".")
            if len(parts) >= 2:
                schema_fq = ".".join(parts[:2])
                if schema_fq in name.upper() and privilege.upper() in (
                    "USAGE", "ALL", "OWNERSHIP"
                ):
                    grant_desc = f"{privilege} on {granted_on} {name}"
                    if grant_desc not in grants_found:
                        grants_found.append(grant_desc)
    except Exception as exc:
        error = type(exc).__name__
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass

    return {
        "has_access": has_access,
        "grants_found": grants_found,
        "role_checked": role_name,
        "query_succeeded": query_succeeded,
        "error": error,
    }
```

```python
# root_cause.py, inside _apply_verdict when exists is False
if exists is False:
    access = probe.access_check(fqn)
    if role:
        group.probe_queries.append(f"SHOW GRANTS TO ROLE {role}")

    if not access.get("query_succeeded", False):
        group.verdict = VERDICT_UNVERIFIED
        group.headline = f"Object {fqn} appears absent, but grant probe failed"
        group.detail = (
            "SHOW TABLES returned no rows, but SHOW GRANTS could not be verified. "
            "Do not conclude never-built until role visibility is checked."
        )
        group.fix = _fix_unverified(show_q, models)
        group.confidence = "low"
    elif access.get("grants_found"):
        group.verdict = VERDICT_DENIED
        group.headline = f"Object {fqn} is NOT visible to role {role or '<run-role>'}"
        group.detail = (
            f"SHOW TABLES returned nothing, but role {role or '<run-role>'} "
            "holds grants touching this object -- treat as a privilege issue."
        )
        group.fix = _fix_denied(fqn, role)
        group.confidence = "medium"
    else:
        group.verdict = VERDICT_NEVER_BUILT
        group.headline = f"Object {fqn} does NOT exist"
        group.detail = (
            "The object is absent and no grants touching it were found for the "
            "checked role. These tests likely ran before their models were materialized."
        )
        group.fix = (
            "Materialize the models, then test (use `dbt build`, which "
            "interleaves run + test in DAG order -- not `dbt test`):\n"
            f"  dbt build -s {' '.join(models)}"
        )
        group.confidence = "high"
    return
```

```python
# root_cause.py, inside _apply_verdict when exists is None
access = probe.access_check(fqn)
if role:
    group.probe_queries.append(f"SHOW GRANTS TO ROLE {role}")

if access.get("query_succeeded") and not access.get("has_access", False):
    group.verdict = VERDICT_DENIED
    ...
else:
    group.verdict = VERDICT_UNVERIFIED
    group.headline = f"Object {fqn} state UNVERIFIED (probe failed)"
    group.detail = (
        "The live probe did not return a usable result. Run the query below "
        "manually to determine existence versus access."
    )
    group.fix = _fix_unverified(show_q, models)
    group.confidence = "low"
```

**Why safe:** Existing positive grant evidence still routes to denied; confirmed no-grant cases can still route to never-built. Failed grant probes no longer masquerade as evidence.

**Test:** `unit`: fake probe returns `object_exists=False`, `access_check={"query_succeeded": False}`; today verdict becomes `never_built`; after patch it is `unverified`.

**Effort/risk:** small/medium; depends on change 1 conceptually, but can ship independently.

---

## 3. Split database usage from schema usage and validate role names

**Location:** `grants.py`, `check_write_access`; `enrich.py`, `_check_write_access_for_unmaterialized`.

**Source:** OUTPUT_ONE.

**Before:**

```python
can_create = False
has_usage = False
...
if name == db_name and granted_on == "DATABASE":
    ...
    if privilege in ("USAGE", "ALL", "ALL PRIVILEGES", "OWNERSHIP"):
        has_usage = True
...
return {
    "can_create": can_create,
    ...
    "has_usage": has_usage,
}
```

**After:**

```python
# grants.py
import re
from typing import Optional

_VALID_ROLE_RE = re.compile(r"^[A-Z_][A-Z0-9_$]*$", re.IGNORECASE)

def _validate_role_name(role_name: str) -> bool:
    return bool(isinstance(role_name, str) and _VALID_ROLE_RE.match(role_name))


def check_write_access(conn, role_name: str, schema_fq: str) -> dict:
    can_create = False
    has_database_usage = False
    has_schema_usage = False
    grants_found: list[str] = []
    query_succeeded = False
    error = None

    if not _validate_role_name(role_name):
        return {
            "can_create": False,
            "grants_found": [],
            "role_checked": role_name,
            "schema_checked": schema_fq,
            "has_usage": False,
            "has_database_usage": False,
            "has_schema_usage": False,
            "query_succeeded": False,
            "error": "invalid role identifier",
        }

    schema_upper = schema_fq.upper()
    parts = schema_upper.split(".")
    db_name = parts[0] if parts else ""
    cursor = None

    try:
        cursor = conn.cursor()
        cursor.execute(f"SHOW GRANTS TO ROLE {role_name}")
        rows = cursor.fetchall()
        query_succeeded = True

        for row in rows:
            privilege = (row[1] if len(row) > 1 else "").upper()
            granted_on = (row[2] if len(row) > 2 else "").upper()
            name = (row[3] if len(row) > 3 else "").upper()

            if name == schema_upper and granted_on == "SCHEMA":
                grant_desc = f"{privilege} on SCHEMA {name}"
                grants_found.append(grant_desc)
                if privilege in ("CREATE TABLE", "ALL", "ALL PRIVILEGES", "OWNERSHIP"):
                    can_create = True
                if privilege in ("USAGE", "ALL", "ALL PRIVILEGES", "OWNERSHIP"):
                    has_schema_usage = True

            if name == db_name and granted_on == "DATABASE":
                grant_desc = f"{privilege} on DATABASE {name}"
                if grant_desc not in grants_found:
                    grants_found.append(grant_desc)
                if privilege in ("USAGE", "ALL", "ALL PRIVILEGES", "OWNERSHIP"):
                    has_database_usage = True

            if name == schema_upper and privilege == "OWNERSHIP":
                can_create = True
                has_schema_usage = True
    except Exception as exc:
        error = type(exc).__name__
    finally:
        if cursor is not None:
            try:
                cursor.close()
            except Exception:
                pass

    return {
        "can_create": can_create,
        "grants_found": grants_found,
        "role_checked": role_name,
        "schema_checked": schema_fq,
        "has_usage": has_database_usage and has_schema_usage,
        "has_database_usage": has_database_usage,
        "has_schema_usage": has_schema_usage,
        "query_succeeded": query_succeeded,
        "error": error,
    }
```

```python
# enrich.py, _check_write_access_for_unmaterialized
result = schema_cache[target_schema]

if not result.get("query_succeeded", False):
    finding.fix_suggestion = (
        f"WARNING: Could not verify CREATE TABLE grants for role {role_name} "
        f"on schema {target_schema} ({result.get('error') or 'unknown error'}).\n"
        f"Manually run: SHOW GRANTS TO ROLE {role_name};\n"
        f"Then: {finding.fix_suggestion}"
    )
    continue

if not result["can_create"]:
    db_name = target_schema.split(".")[0]
    grants: list[str] = []
    if not result.get("has_database_usage", False):
        grants.append(f"GRANT USAGE ON DATABASE {db_name} TO ROLE {role_name};")
    if not result.get("has_schema_usage", False):
        grants.append(f"GRANT USAGE ON SCHEMA {target_schema} TO ROLE {role_name};")
    grants.append(f"GRANT CREATE TABLE ON SCHEMA {target_schema} TO ROLE {role_name};")

    finding.fix_suggestion = (
        f"WARNING: Role {role_name} does NOT have CREATE TABLE "
        f"on schema {target_schema}.\n"
        "Grant access first:\n"
        + "\n".join(f"  {grant}" for grant in grants)
        + f"\nThen: {finding.fix_suggestion}"
    )
```

**Why safe:** Adds keys while preserving old `has_usage`. Invalid role strings no longer reach SQL.

**Test:** `unit/security`: role `BAD ROLE;DROP` returns `query_succeeded=False`. `unit`: database usage present, schema usage absent produces both schema USAGE and CREATE TABLE grants; today schema USAGE can be omitted.

**Effort/risk:** medium; depends on change 2 if root-cause uses `query_succeeded`.

---

## 4. Make query-history timing access defensive

**Location:** `enrich.py`, `_enrich_runtime_error`, timing lookup.

**Source:** OUTPUT_TWO immediate fix.

**Before:**

```python
timing = result_data.get("timing", [])
execute_timing = next((t for t in timing if t["name"] == "execute"), None)
```

**After:**

```python
timing = result_data.get("timing", [])
timing_items = timing if isinstance(timing, list) else []
execute_timing = next(
    (
        t for t in timing_items
        if isinstance(t, dict) and t.get("name") == "execute"
    ),
    None,
)
```

**Why safe:** Preserves valid timing behavior; malformed entries no longer crash live enrichment.

**Test:** `robustness`: run result has `timing=[None, {"started_at": "..."}]`; today raises `TypeError`/`KeyError`; after patch no matched query is attempted.

**Effort/risk:** small; no dependency.

---

## 5. Execution failure must outrank manifest declaration

**Location:** `models.py`, `LineageStep.status_emoji/status_text`; `enrich.py`, `_is_passing`, `_is_failing`.

**Source:** OUTPUT_ONE.

**Before:**

```python
if self.manifest_status == "declared":
    return "\u2705"
...
if self.run_status == "error":
    return "\u274c"
```

**After:**

```python
# enrich.py
def _is_passing(step) -> bool:
    """A step is passing only if stronger failure signals are absent."""
    if step.live_status in ("missing", "no_column"):
        return False
    if step.run_status == "error":
        return False
    if step.live_status == "exists":
        return True
    if step.run_status == "pass":
        return True
    if step.manifest_status == "declared":
        return True
    return False


def _is_failing(step) -> bool:
    """A step is failing if live/manifest/run indicate absence or error."""
    if step.live_status == "unknown":
        return False
    if step.live_status in ("missing", "no_column"):
        return True
    if step.run_status == "error":
        return True
    if step.manifest_status in ("not_found", "missing"):
        return True
    return False
```

`LineageStep.status_*` should use the same precedence as shown in change 1.

**Why safe:** A node that dbt says errored should not render as passing just because it exists in the manifest.

**Test:** `unit`: `LineageStep(manifest_status="declared", run_status="error")` returns fail emoji/text; `_is_passing()` is false and `_is_failing()` is true.

**Effort/risk:** small; can ship with change 1.

---

## 6. Do not infer disconnects for generic data-flow trails

**Location:** `enrich.py`, `_enrich_lineage_trail`.

**Source:** OUTPUT_TWO immediate fix.

**Before:**

```python
# After populating live_status, identify the disconnect point
_identify_disconnect(finding)
```

**After:**

```python
# After populating live_status, identify the disconnect point only for
# object/column absence hypotheses. Data-error trails show context, not a
# missing-object boundary.
if finding.target_object or finding.target_identifier:
    _identify_disconnect(finding)
```

**Why safe:** Runtime/schema-change lineage still gets disconnects; data errors stop getting bogus “furthest upstream failure” verdicts.

**Test:** `unit`: data-error finding with lineage steps and no target fields does not receive `disconnect`. Today it can.

**Effort/risk:** small; depends on change 5 for clearer status semantics.

---

## 7. Downgrade schema-drift wording until live evidence confirms it

**Location:** `schema_change_error.py`, `_diagnose_drift`.

**Source:** OUTPUT_ONE.

**Before:**

```python
summary=(
    f"Schema drift: column '{column_name}' declared in manifest "
    f"(from {upstream_model.split('.')[-1]}) but missing at runtime"
),
...
"This means the upstream table's schema was altered outside dbt "
```

**After:**

```python
return DiagnosticFinding(
    summary=(
        f"Possible schema drift: column '{column_name}' is declared in the manifest "
        f"for {upstream_model.split('.')[-1]} but Snowflake rejected it"
    ),
    location=location,
    upstream_origin=UpstreamOrigin(
        model_id=upstream_model, file_path=upstream_file
    ),
    explanation=(
        f"The column '{column_name}' is declared for upstream model {upstream_model}, "
        "but the failing SQL saw it as invalid. This is evidence for schema drift, "
        "but not proof: a wrong table alias, quoted-case mismatch, or stale manifest "
        "can produce the same symptom. Live DESCRIBE TABLE evidence is needed before "
        "calling the physical table altered outside dbt."
        + type_hint
    ),
    fix_suggestion=(
        f"1. DESCRIBE the upstream relation and confirm whether '{column_name}' exists.\n"
        f"2. If missing or renamed, rebuild upstream: dbt run -s {upstream_model.split('.')[-1]}.\n"
        "3. If present, inspect aliases/case sensitivity in the failing SQL."
    ),
    target_identifier=column_name,
)
```

**Why safe:** Classification remains `schema_change_error`; the claim is calibrated to available evidence.

**Test:** `contract`: existing schema-change fixture still routes to `schema_change_error`, but summary starts with “Possible schema drift” and explanation does not contain “This means”.

**Effort/risk:** small; no dependency.

---

## 8. Serialize live enrichment, live lineage, and diff in JSON

**Location:** `models.py`, `DiagnosticReport.to_json_dict`, `_finding_to_dict`.

**Source:** OUTPUT_ONE.

**Before:**

```python
"findings": [self._finding_to_dict(f) for f in self.findings],
...
if f.lineage_trail:
    d["lineage_trail"] = [
        {
            "node_id": step.node_id,
            "node_type": step.node_type,
            "short_name": step.short_name,
            "depth": step.depth,
            "manifest_status": step.manifest_status,
            "run_status": step.run_status,
        }
        for step in f.lineage_trail
    ]
```

**After:**

```python
# models.py, DiagnosticReport.to_json_dict
if self.diff is not None:
    d["diff"] = {
        "node_changed": self.diff.node_changed,
        "changed_lines": self.diff.changed_lines,
        "upstream_changes": self.diff.upstream_changes,
        "columns_added": self.diff.columns_added,
        "columns_removed": self.diff.columns_removed,
        "columns_type_changed": self.diff.columns_type_changed,
    }
```

```python
# models.py, DiagnosticReport._finding_to_dict
if f.session_params_to_check:
    d["session_params_to_check"] = f.session_params_to_check
if f.diagnostic_params:
    d["diagnostic_params"] = f.diagnostic_params

if f.enrichment:
    d["enrichment"] = {
        "actual_param_values": f.enrichment.actual_param_values,
        "actual_columns": [
            {"name": c.name, "data_type": c.data_type}
            for c in f.enrichment.actual_columns
        ],
        "object_exists": f.enrichment.object_exists,
        "matched_error_message": f.enrichment.matched_error_message,
        "matched_error_code": f.enrichment.matched_error_code,
        # Intentionally omit matched_query_text by default; query text can
        # contain literals. Add a CLI flag before exposing it.
    }

if f.lineage_trail:
    d["lineage_trail"] = [
        {
            "node_id": step.node_id,
            "node_type": step.node_type,
            "short_name": step.short_name,
            "file_path": step.file_path,
            "relation_name": step.relation_name,
            "depth": step.depth,
            "manifest_status": step.manifest_status,
            "manifest_detail": step.manifest_detail,
            "live_status": step.live_status,
            "live_detail": step.live_detail,
            "run_status": step.run_status,
            "annotation": step.annotation,
        }
        for step in f.lineage_trail
    ]
```

**Why safe:** Additive-only JSON keys; query text remains withheld.

**Test:** `e2e`: run `--json --previous-manifest` with live enrichment mocked; today `diff` and `enrichment` absent; after patch present.

**Effort/risk:** small/medium; update golden JSON expectations.

---

## 9. Use `generic.j2` when an error-class template is missing

**Location:** `report.j2`, every dynamic include of `findings/<error_class>.j2`.

**Source:** OUTPUT_ONE.

**Before:**

```j2
{% include 'findings/' + report.error_class + '.j2' ignore missing %}
```

**After:**

```j2
{% include ['findings/' + report.error_class + '.j2', 'findings/generic.j2'] %}
```

Apply to the group/verbose/ungrouped include sites.

**Why safe:** Existing templates still win. Missing templates no longer silently hide findings.

**Test:** `unit/e2e`: construct a report with `error_class="new_kind"` and a finding; rendered text contains the generic finding summary. Today it renders nothing for that finding.

**Effort/risk:** small; no dependency.

---

## 10. Validate loaded JSON shape and profile YAML shape

**Location:** `main.py`, `load_json`, `_load_config`; `connection.py`, `parse_profile`.

**Source:** OUTPUT_ONE.

**Before:**

```python
return json.loads(text)
```

```python
with open(profiles_path) as f:
    raw = yaml.safe_load(f)

if profile_name not in raw:
    return None
```

**After:**

```python
# main.py
def load_json(path: Path, label: str) -> dict:
    ...
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ArtifactLoadError(
            label, path, _corrupt_artifact_note(label), kind="corrupt"
        ) from exc

    if not isinstance(data, dict):
        raise ArtifactLoadError(
            label,
            path,
            f"{label} must be a JSON object; got {type(data).__name__}",
            kind="corrupt",
        )
    return data


def _load_config(config_path: Optional[Path]) -> Optional[dict]:
    if config_path is None or not config_path.exists():
        return None
    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return None
    return data if isinstance(data, dict) else None
```

```python
# connection.py
def parse_profile(
    profile_name: str,
    target_name: str,
    project_dir: Optional[Path] = None,
) -> Optional[dict]:
    _load_dotenv(project_dir)
    profiles_path = _find_profiles_yml(project_dir)
    if not profiles_path:
        return None

    try:
        with open(profiles_path) as f:
            raw = yaml.safe_load(f)
    except (yaml.YAMLError, OSError):
        return None

    if not isinstance(raw, dict) or profile_name not in raw:
        return None

    profile = raw.get(profile_name)
    if not isinstance(profile, dict):
        return None

    outputs = profile.get("outputs", {})
    if not isinstance(outputs, dict):
        return None

    target = target_name or profile.get("target", "dev")
    if target not in outputs or not isinstance(outputs[target], dict):
        return None

    target_config = _resolve_profile_values(outputs[target])
    ...
```

**Why safe:** Valid artifacts/profiles unchanged; wrong-shaped inputs degrade cleanly.

**Test:** `robustness`: `manifest.json` containing `[]` errors cleanly instead of later `AttributeError`; empty `profiles.yml` returns no connection.

**Effort/risk:** small; no dependency.

---

# Wave 2 — structural refactors behind compatibility shims

## 11. Add run-results views and index without removing raw dict access

**Location:** `[NEW] compat/views.py`; `base.py`, `DiagnosticContext`; `main.py`, `_diagnose_all`.

**Source:** OUTPUT_ONE/OUTPUT_TWO.

**Before:**

```python
def _find_result(run_results: dict, unique_id: str) -> Optional[dict]:
    for result in run_results.get("results", []):
        if result.get("unique_id") == unique_id:
            return result
    return None
```

**After:**

```python
# [NEW] dbt_diagnostics/compat/views.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional

from dbt_diagnostics.compat import safe


@dataclass(frozen=True)
class ExecuteWindow:
    started_at: Optional[str]
    completed_at: Optional[str]


@dataclass(frozen=True)
class RunResultView:
    raw: Mapping[str, Any]

    @property
    def unique_id(self) -> Optional[str]:
        value = self.raw.get("unique_id")
        return value if isinstance(value, str) else None

    @property
    def status(self) -> Optional[str]:
        value = self.raw.get("status")
        return value if isinstance(value, str) else None

    @property
    def message(self) -> str:
        value = self.raw.get("message")
        return value if isinstance(value, str) else ""

    @property
    def failures(self) -> Optional[int]:
        value = self.raw.get("failures")
        return value if isinstance(value, int) and not isinstance(value, bool) else None

    @property
    def compiled_code(self) -> Optional[str]:
        return safe.node_compiled_code(self.raw)

    @property
    def query_id(self) -> Optional[str]:
        return safe.result_query_id(self.raw)

    def execute_window(self) -> Optional[ExecuteWindow]:
        timing = self.raw.get("timing")
        if not isinstance(timing, list):
            return None
        for item in timing:
            if not isinstance(item, dict) or item.get("name") != "execute":
                continue
            started = item.get("started_at")
            completed = item.get("completed_at")
            return ExecuteWindow(
                started_at=started if isinstance(started, str) else None,
                completed_at=completed if isinstance(completed, str) else None,
            )
        return None


class RunResultsIndex:
    def __init__(self, artifact: object) -> None:
        self._by_id: dict[str, RunResultView] = {}
        self._by_query_id: dict[str, RunResultView] = {}

        raw_results = artifact.get("results") if isinstance(artifact, dict) else None
        for raw in raw_results if isinstance(raw_results, list) else []:
            if not isinstance(raw, dict):
                continue
            result = RunResultView(raw)
            if result.unique_id:
                self._by_id[result.unique_id] = result
            if result.query_id:
                self._by_query_id[result.query_id] = result

    def get(self, unique_id: str) -> Optional[RunResultView]:
        return self._by_id.get(unique_id)

    def status(self, unique_id: str) -> Optional[str]:
        result = self.get(unique_id)
        return result.status if result else None

    def end_time_for_query(self, query_id: str) -> Optional[str]:
        result = self._by_query_id.get(query_id)
        if result is None:
            return None
        window = result.execute_window()
        return window.completed_at if window else None
```

```python
# base.py
from typing import Optional, Any

@dataclass
class DiagnosticContext:
    ...
    run_results: Optional[dict] = None
    run_index: Optional[Any] = None
    catalog: Optional[dict] = None
```

```python
# main.py, _diagnose_all
from dbt_diagnostics.compat.views import RunResultsIndex

run_index = RunResultsIndex(run_results)

context = DiagnosticContext(
    dag_walker=dag_walker,
    column_tracer=column_tracer,
    models_dir=paths["models_dir"],
    compiled_dir=paths["compiled_dir"],
    manifest=manifest,
    run_results=run_results,
    run_index=run_index,
    catalog=catalog,
)
```

**Why safe:** Additive; raw artifact remains available while call sites migrate.

**Test:** `unit`: malformed `results` entries are skipped; `status()` and `end_time_for_query()` return expected values.

**Effort/risk:** medium; no behavior change until later call-site migration.

---

## 12. Migrate status and result lookups to `RunResultsIndex`

**Location:** `runtime_error.py`, `_get_run_status`; `data_error.py`, `_get_run_status`; `enrich.py`, `_find_result`; `run_identity.py`, `_end_time_for`.

**Source:** OUTPUT_ONE/OUTPUT_TWO.

**Before:**

```python
for result in self.context.run_results.get("results", []):
    if result.get("unique_id") == unique_id:
        return result.get("status")
return None
```

**After:**

```python
# runtime_error.py and data_error.py
def _get_run_status(self, unique_id: str) -> Optional[str]:
    if self.context.run_index is not None:
        return self.context.run_index.status(unique_id)
    if not self.context.run_results:
        return None
    for result in self.context.run_results.get("results", []):
        if isinstance(result, dict) and result.get("unique_id") == unique_id:
            status = result.get("status")
            return status if isinstance(status, str) else None
    return None
```

```python
# enrich.py
def _find_result(run_results: dict, unique_id: str) -> Optional[dict]:
    # Keep for legacy callers until EvidenceCollector replaces this module.
    for result in run_results.get("results", []):
        if isinstance(result, dict) and result.get("unique_id") == unique_id:
            return result
    return None
```

```python
# run_identity.py
def _end_time_for(run_results: Optional[dict], query_id: Optional[str]) -> Optional[str]:
    if not run_results or not query_id:
        return None
    try:
        from dbt_diagnostics.compat.views import RunResultsIndex
        return RunResultsIndex(run_results).end_time_for_query(query_id)
    except Exception:
        return None
```

**Why safe:** Behavior preserved; malformed entries are safer; central index can later be passed directly.

**Test:** `unit`: repeated status lookup with non-dict result entries does not raise.

**Effort/risk:** small/medium; depends on change 11.

---

## 13. Add edge-preserving lineage graph while keeping `lineage_trail`

**Location:** `models.py`; `dag_walker.py`; classifiers assigning lineage.

**Source:** both.

**Before:**

```python
lineage_trail = self.context.dag_walker.trace_column_lineage(...)
finding.lineage_trail = lineage_trail
```

**After:**

```python
# models.py
@dataclass(frozen=True)
class LineageEdge:
    upstream_id: str
    downstream_id: str


@dataclass
class LineageGraph:
    root_id: str
    nodes: dict[str, LineageStep] = field(default_factory=dict)
    edges: list[LineageEdge] = field(default_factory=list)

    def ordered_steps(self) -> list[LineageStep]:
        return sorted(self.nodes.values(), key=lambda step: (step.depth, step.node_id))


@dataclass
class DiagnosticFinding:
    ...
    lineage_trail: list["LineageStep"] = field(default_factory=list)
    lineage_graph: Optional["LineageGraph"] = None
    disconnect: Optional["DisconnectVerdict"] = None
```

```python
# dag_walker.py
def trace_column_graph(
    self,
    unique_id: str,
    column_name: str,
    max_depth: int = 5,
    run_results: Optional[dict] = None,
) -> LineageGraph:
    run_status_map = self._build_run_status_map(run_results)
    graph = LineageGraph(root_id=unique_id)

    root_node = self.get_node(unique_id)
    root_step = self._make_step(unique_id, root_node, depth=0)
    root_step.manifest_status = "declared"
    root_step.run_status = run_status_map.get(unique_id)
    root_step.annotation = "failing model"
    graph.nodes[unique_id] = root_step

    visited: set[str] = {unique_id}
    queue: deque[tuple[str, str, int]] = deque(
        (parent_id, unique_id, 1)
        for parent_id in self.get_parents(unique_id)
    )

    while queue:
        current_id, downstream_id, depth = queue.popleft()
        graph.edges.append(LineageEdge(upstream_id=current_id, downstream_id=downstream_id))

        current_node = self.get_node(current_id)
        if current_id not in graph.nodes:
            step = self._make_step(current_id, current_node, depth)
            step.run_status = run_status_map.get(current_id)
            if current_node and self._node_has_column(current_node, column_name):
                step.manifest_status = "declared"
                step.manifest_detail = f"column '{column_name}' found"
            else:
                step.manifest_status = None
                step.manifest_detail = "column provenance not established"
            graph.nodes[current_id] = step

        if current_id in visited or depth >= max_depth:
            continue
        visited.add(current_id)

        for parent_id in self.get_parents(current_id):
            queue.append((parent_id, current_id, depth + 1))

    return graph


def trace_column_lineage(
    self,
    unique_id: str,
    column_name: str,
    max_depth: int = 5,
    run_results: Optional[dict] = None,
) -> list[LineageStep]:
    return self.trace_column_graph(
        unique_id, column_name, max_depth=max_depth, run_results=run_results
    ).ordered_steps()
```

Classifier call sites then become:

```python
lineage_graph = self.context.dag_walker.trace_column_graph(
    self.unique_id,
    identifier,
    run_results=self.context.run_results,
)
lineage_trail = lineage_graph.ordered_steps()

return DiagnosticFinding(
    ...
    lineage_trail=lineage_trail,
    lineage_graph=lineage_graph,
)
```

**Why safe:** Display remains list-based; new graph is available for correct verdicts.

**Test:** `unit`: branching DAG `root -> parent_a`, `root -> parent_b`, `parent_a -> grandparent_a`; graph edges contain only real edges and ordered display still includes all nodes.

**Effort/risk:** large; depends on tests for branching DAGs.

---

## 14. Use graph edges for disconnect inference

**Location:** `enrich.py`, `_identify_disconnect`.

**Source:** both.

**Before:**

```python
for i in range(len(trail) - 1):
    current = trail[i]
    next_step = trail[i + 1]
    if _is_passing(current) and _is_failing(next_step):
        finding.disconnect = DisconnectVerdict(...)
```

**After:**

```python
def _identify_disconnect(finding) -> None:
    if finding.disconnect is not None:
        return

    graph = getattr(finding, "lineage_graph", None)
    if graph is not None:
        candidates: list[tuple[LineageStep, LineageStep]] = []
        for edge in graph.edges:
            upstream = graph.nodes.get(edge.upstream_id)
            downstream = graph.nodes.get(edge.downstream_id)
            if upstream is None or downstream is None:
                continue
            if _is_passing(downstream) and _is_failing(upstream):
                candidates.append((downstream, upstream))

        if candidates:
            passing_step, failing_step = min(
                candidates,
                key=lambda pair: (pair[1].depth, pair[1].short_name),
            )
            finding.disconnect = DisconnectVerdict(
                between_node_a=failing_step.short_name,
                between_node_b=passing_step.short_name,
                explanation=_build_verdict_text(passing_step, failing_step, finding),
                confidence="high" if failing_step.live_status else "medium",
            )
        return

    # Legacy fallback for findings not yet migrated to LineageGraph.
    trail = finding.lineage_trail
    if len(trail) < 2:
        return
    for i in range(len(trail) - 1):
        current = trail[i]
        next_step = trail[i + 1]
        if _is_passing(current) and _is_failing(next_step):
            finding.disconnect = DisconnectVerdict(
                between_node_a=next_step.short_name,
                between_node_b=current.short_name,
                explanation=_build_verdict_text(current, next_step, finding),
                confidence="high" if next_step.live_status else "medium",
            )
            return
```

**Why safe:** New graph-aware path is correct; legacy fallback keeps unmigrated findings working.

**Test:** `unit`: siblings adjacent in display order no longer produce a disconnect between siblings.

**Effort/risk:** medium/large; depends on change 13.

---

## 15. Restrict object lineage search to reachable ancestors

**Location:** `dag_walker.py`, `trace_object_lineage` / new `trace_object_graph`.

**Source:** both.

**Before:**

```python
# Check all sources in the manifest for a matching relation_name
for source_id, source_node in self.sources.items():
    relation = safe.node_relation_name(source_node) or ""
    if relation and relation.upper() == object_upper:
        matched_source_id = source_id
        break
```

**After:**

```python
# dag_walker.py
def _reachable_upstream_ids(self, unique_id: str, max_depth: int = 20) -> set[str]:
    reachable: set[str] = set()
    queue: deque[tuple[str, int]] = deque(
        (parent_id, 1) for parent_id in self.get_parents(unique_id)
    )
    while queue:
        node_id, depth = queue.popleft()
        if node_id in reachable:
            continue
        reachable.add(node_id)
        if depth >= max_depth:
            continue
        for parent_id in self.get_parents(node_id):
            queue.append((parent_id, depth + 1))
    return reachable
```

```python
# inside trace_object_lineage
reachable_ids = self._reachable_upstream_ids(unique_id)
matched_source_id = None

for candidate_id in reachable_ids:
    candidate_node = self.get_node(candidate_id)
    relation = safe.node_relation_name(candidate_node) or ""
    if relation and relation.upper() == object_upper:
        matched_source_id = candidate_id
        break
```

**Why safe:** A globally matching relation no longer appears as lineage unless it is actually upstream.

**Test:** `unit`: manifest has an unrelated source with matching `relation_name`; today it is shown as lineage; after patch synthetic missing step is used.

**Effort/risk:** medium; depends on graph tests but can ship before graph if implemented in old function.

---

## 16. Add structured enrichment request and evidence fields

**Location:** `models.py`; classifiers that ask for live evidence.

**Source:** OUTPUT_TWO.

**Before:**

```python
session_params_to_check: list[str] = field(default_factory=list)
diagnostic_params: list[str] = field(default_factory=list)
enrichment: Optional[EnrichmentData] = None
```

**After:**

```python
# models.py
from typing import Any

@dataclass(frozen=True)
class EnrichmentRequest:
    parameters: tuple[str, ...] = ()
    relation: Optional[str] = None
    column: Optional[str] = None
    match_query_history: bool = False


@dataclass(frozen=True)
class Evidence:
    source: str
    name: str
    value: Any
    detail: Optional[str] = None


@dataclass(frozen=True)
class FindingResolution:
    verdict: str
    confidence: str = "low"
    explanation: Optional[str] = None
    fix: Optional[str] = None


@dataclass
class DiagnosticFinding:
    ...
    enrichment: Optional[EnrichmentData] = None
    enrichment_request: EnrichmentRequest = field(default_factory=EnrichmentRequest)
    evidence: list[Evidence] = field(default_factory=list)
    resolution: Optional[FindingResolution] = None
```

Classifier example:

```python
# timeout_error.py
return DiagnosticFinding(
    summary=summary,
    location=location,
    explanation=...,
    fix_suggestion="\n".join(fix_parts),
    session_params_to_check=["STATEMENT_TIMEOUT_IN_SECONDS"],
    enrichment_request=EnrichmentRequest(
        parameters=("STATEMENT_TIMEOUT_IN_SECONDS",),
    ),
)
```

```python
# runtime_error.py object-not-found finding
return DiagnosticFinding(
    summary=f"{summary_label} not found: {object_name}",
    location=location,
    explanation=explanation,
    fix_suggestion=fix,
    target_object=object_name,
    compiled_snippet=snippet,
    lineage_trail=lineage_trail,
    enrichment_request=EnrichmentRequest(
        relation=object_name,
        match_query_history=True,
    ),
)
```

**Why safe:** Additive model fields; legacy enrichment still works.

**Test:** `unit`: timeout finding now has `enrichment_request.parameters`, proving live parameter requests are not limited to contract violations.

**Effort/risk:** medium; depends on change 8 if JSON exposes evidence later.

---

## 17. Introduce class-agnostic evidence collection

**Location:** `[NEW] enrichers/collector.py`; `main.py`, `_try_enrich`.

**Source:** OUTPUT_TWO.

**Before:**

```python
if report.error_class == "contract_violation":
    _enrich_contract_violation(conn, finding)
elif report.error_class == "runtime_error":
    _enrich_runtime_error(conn, finding, report, result_data)
```

**After:**

```python
# [NEW] enrichers/collector.py
from __future__ import annotations

from dbt_diagnostics.compat import safe
from dbt_diagnostics.enrichers.params import get_parameters
from dbt_diagnostics.enrichers.query_history import find_matching_query
from dbt_diagnostics.enrichers.schema_inspector import describe_table, table_exists
from dbt_diagnostics.models import DiagnosticReport, EnrichmentData, Evidence


class EvidenceCollector:
    def __init__(self, conn, run_results: dict) -> None:
        self.conn = conn
        self.run_results = run_results

    def collect(self, reports: list[DiagnosticReport]) -> None:
        for report in reports:
            result_data = self._find_result(report.unique_id)
            for finding in report.findings:
                self._collect_finding(report, finding, result_data)

    def _collect_finding(self, report, finding, result_data) -> None:
        request = finding.enrichment_request

        if request.parameters:
            values = get_parameters(self.conn, list(request.parameters))
            if values:
                enrichment = finding.enrichment or EnrichmentData()
                enrichment.actual_param_values.update(values)
                finding.enrichment = enrichment
                finding.evidence.append(
                    Evidence("snowflake", "session_parameters", values)
                )

        if request.relation:
            exists = table_exists(self.conn, request.relation)
            enrichment = finding.enrichment or EnrichmentData()
            enrichment.object_exists = exists
            if exists is True:
                enrichment.actual_columns = describe_table(self.conn, request.relation)
            finding.enrichment = enrichment
            finding.evidence.append(
                Evidence("snowflake", "relation_exists", exists)
            )

        if request.match_query_history and result_data:
            self._collect_query_history(finding, result_data)

    def _collect_query_history(self, finding, result_data: dict) -> None:
        timing = result_data.get("timing", [])
        timing_items = timing if isinstance(timing, list) else []
        execute_timing = next(
            (
                t for t in timing_items
                if isinstance(t, dict) and t.get("name") == "execute"
            ),
            None,
        )
        if not execute_timing:
            return

        compiled = safe.node_compiled_code(result_data) or ""
        match = find_matching_query(
            self.conn,
            compiled,
            execute_timing.get("started_at", ""),
            execute_timing.get("completed_at", ""),
        )
        if not match:
            return

        enrichment = finding.enrichment or EnrichmentData()
        enrichment.matched_query_text = match["query_text"]
        enrichment.matched_error_message = match["error_message"]
        enrichment.matched_error_code = match["error_code"]
        finding.enrichment = enrichment
        finding.evidence.append(Evidence("snowflake", "query_history_match", match))

    def _find_result(self, unique_id: str) -> dict | None:
        raw = self.run_results.get("results") if isinstance(self.run_results, dict) else None
        for result in raw if isinstance(raw, list) else []:
            if isinstance(result, dict) and result.get("unique_id") == unique_id:
                return result
        return None
```

```python
# main.py, _try_enrich
from dbt_diagnostics.enrichers import enrich_reports
from dbt_diagnostics.enrichers.collector import EvidenceCollector

collector = EvidenceCollector(conn, run_results)
collector.collect(reports)
enrich_reports(conn, reports, run_results)  # temporary legacy reconciliation
```

Later PR removes class-tag enrichment from `enrich_reports()` once parity tests pass.

**Why safe:** Runs in parallel with legacy behavior initially; proves evidence model without big-bang removal.

**Test:** `contract`: timeout parameter request is collected; legacy code ignored it.

**Effort/risk:** medium; depends on change 16.

---

## 18. Stop rendering root-cause members twice

**Location:** `grouping.py`, `group_reports`; `renderer.py`, `render_text`; `main.py`, `cmd_diagnose`.

**Source:** both.

**Before:**

```python
report_groups, ungrouped_reports = group_reports(reports)
```

**After:**

```python
# grouping.py
def group_reports(
    reports: list[DiagnosticReport],
    min_group_size: int = 2,
    exclude_unique_ids: set[str] | None = None,
) -> tuple[list[ReportGroup], list[DiagnosticReport]]:
    excluded = exclude_unique_ids or set()
    keyed: dict[str, list[DiagnosticReport]] = {}
    unkeyed: list[DiagnosticReport] = []

    for report in reports:
        if report.unique_id in excluded:
            continue
        schema_prefix = _extract_schema_prefix(report)
        ...
```

```python
# renderer.py
def render_text(
    reports: list[DiagnosticReport],
    ...
    root_cause_groups: list = None,
) -> str:
    ...
    collapsed_ids = {
        uid
        for group in (root_cause_groups or [])
        for uid in [r.unique_id for r in getattr(group, "reports", [])]
    }
    report_groups, ungrouped_reports = group_reports(
        reports,
        exclude_unique_ids=collapsed_ids,
    )
```

**Why safe:** Root-cause groups still render; their member reports are excluded from secondary grouping.

**Test:** `e2e`: one object-not-exist report with root-cause group appears once in text. Today root cause and ordinary report both render.

**Effort/risk:** medium; depends on root-cause tests.

---

# Wave 3 — database-portability seam and Snowflake gateway

## 19. Add a typed metadata gateway, keep old function wrappers

**Location:** `[NEW] enrichers/metadata.py`; `schema_inspector.py`, wrappers.

**Source:** both.

**Before:**

```python
def table_exists(conn, fq_table_name: str) -> Optional[bool]:
    ...
```

**After:**

```python
# [NEW] enrichers/metadata.py
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, Iterator, Optional, TypeVar

from dbt_diagnostics.enrichers.schema_inspector import (
    _validate_fq_name,
    describe_table as legacy_describe_table,
)

T = TypeVar("T")


class ProbeStatus(StrEnum):
    CONFIRMED = "confirmed"
    QUERY_FAILED = "query_failed"
    INVALID_INPUT = "invalid_input"


@dataclass(frozen=True)
class ProbeResult(Generic[T]):
    status: ProbeStatus
    value: Optional[T] = None
    reason: Optional[str] = None

    @property
    def confirmed(self) -> bool:
        return self.status == ProbeStatus.CONFIRMED


class SnowflakeMetadata:
    def __init__(self, conn: Any) -> None:
        self.conn = conn
        self._exists_cache: dict[str, ProbeResult[bool]] = {}

    @contextmanager
    def cursor(self) -> Iterator[Any]:
        cursor = None
        try:
            cursor = self.conn.cursor()
            yield cursor
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass

    def relation_exists(self, fq_name: str) -> ProbeResult[bool]:
        if fq_name in self._exists_cache:
            return self._exists_cache[fq_name]

        if not _validate_fq_name(fq_name):
            result = ProbeResult[bool](
                status=ProbeStatus.INVALID_INPUT,
                reason="invalid fully-qualified identifier",
            )
            self._exists_cache[fq_name] = result
            return result

        db, schema, table = fq_name.split(".")
        try:
            with self.cursor() as cursor:
                cursor.execute(f"SHOW TABLES LIKE '{table}' IN {db}.{schema}")
                rows = cursor.fetchall()
        except Exception as exc:
            result = ProbeResult[bool](
                status=ProbeStatus.QUERY_FAILED,
                reason=type(exc).__name__,
            )
        else:
            exact = [
                row for row in rows
                if len(row) > 1 and str(row[1]).upper() == table.upper()
            ]
            result = ProbeResult(status=ProbeStatus.CONFIRMED, value=bool(exact))

        self._exists_cache[fq_name] = result
        return result

    def describe_relation(self, fq_name: str):
        return legacy_describe_table(self.conn, fq_name)
```

```python
# schema_inspector.py wrapper remains
def table_exists(conn, fq_table_name: str) -> Optional[bool]:
    from dbt_diagnostics.enrichers.metadata import SnowflakeMetadata
    result = SnowflakeMetadata(conn).relation_exists(fq_table_name)
    return result.value if result.confirmed else None
```

**Why safe:** Public functions retain old return shape; new callers can use typed status.

**Test:** `unit`: `SnowflakeMetadata.relation_exists()` distinguishes invalid input, query failure, confirmed false, confirmed true. Existing `table_exists()` still returns `None` on failure.

**Effort/risk:** medium; should follow wave 1 to avoid duplicate semantics.

---

## 20. Add identifier/role parsing seam before full adapter extraction

**Location:** `[NEW] enrichers/identifiers.py`; `grants.py`; `schema_inspector.py`.

**Source:** OUTPUT_ONE.

**Before:**

```python
parts = fq_table_name.split(".")
...
cursor.execute(f"SHOW GRANTS TO ROLE {role_name}")
```

**After:**

```python
# [NEW] enrichers/identifiers.py
from __future__ import annotations

import re
from dataclasses import dataclass

_UNQUOTED_IDENT_RE = re.compile(r"^[A-Z_][A-Z0-9_$]*$", re.IGNORECASE)
_SAFE_ROLE_RE = re.compile(r"^[A-Z_][A-Z0-9_$]*$", re.IGNORECASE)


@dataclass(frozen=True)
class RelationName:
    database: str
    schema: str
    name: str

    @property
    def schema_fq(self) -> str:
        return f"{self.database}.{self.schema}"

    @property
    def fqn(self) -> str:
        return f"{self.database}.{self.schema}.{self.name}"


def parse_unquoted_relation(value: str) -> RelationName | None:
    parts = value.split(".") if isinstance(value, str) else []
    if len(parts) != 3:
        return None
    if not all(_UNQUOTED_IDENT_RE.match(part) for part in parts):
        return None
    return RelationName(parts[0], parts[1], parts[2])


def validate_unquoted_role(value: str) -> bool:
    return bool(isinstance(value, str) and _SAFE_ROLE_RE.match(value))
```

```python
# grants.py
from dbt_diagnostics.enrichers.identifiers import validate_unquoted_role

if not validate_unquoted_role(role_name):
    return {
        "has_access": False,
        "grants_found": [],
        "role_checked": role_name,
        "query_succeeded": False,
        "error": "invalid role identifier",
    }
```

**Why safe:** Narrowly supports the same unquoted identifiers the current code mostly assumes; blocks dangerous role strings. Quoted identifier support is a later adapter feature.

**Test:** `unit/security`: quoted or semicolon role rejected; normal `TRANSFORMER_ROLE` accepted.

**Effort/risk:** small/medium; quoted identifiers still require a later fixture-backed design.

---

## 21. Introduce `WarehouseAdapter` protocol and Snowflake implementation shell

**Location:** `[NEW] adapters/base.py`, `[NEW] adapters/snowflake.py`; `pyproject.toml` package discovery already covers `dbt_diagnostics*`.

**Source:** OUTPUT_ONE portability seam.

**Before:** Snowflake semantics are spread through enrichers/classifiers.

**After:**

```python
# [NEW] dbt_diagnostics/adapters/base.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Optional

from dbt_diagnostics.enrichers.metadata import ProbeResult
from dbt_diagnostics.models import ColumnInfo


@dataclass(frozen=True)
class NormalizedDatabaseError:
    category: str
    error_code: Optional[str] = None
    relation: Optional[str] = None
    identifier: Optional[str] = None
    required_privilege: Optional[str] = None
    line: Optional[int] = None
    position: Optional[int] = None
    raw_message: str = ""


class WarehouseAdapter(Protocol):
    name: str
    sqlglot_dialect: str

    def normalize_error(self, message: str) -> NormalizedDatabaseError:
        ...

    def relation_exists(self, conn, relation: str) -> ProbeResult[bool]:
        ...

    def describe_relation(self, conn, relation: str) -> list[ColumnInfo]:
        ...

    def current_role(self, conn) -> Optional[str]:
        ...
```

```python
# [NEW] dbt_diagnostics/adapters/snowflake.py
from __future__ import annotations

from dbt_diagnostics.adapters.base import NormalizedDatabaseError
from dbt_diagnostics.enrichers.grants import get_current_role
from dbt_diagnostics.enrichers.metadata import SnowflakeMetadata
from dbt_diagnostics.enrichers.schema_inspector import describe_table
from dbt_diagnostics.classifiers.runtime_error import (
    _IDENTIFIER_RE,
    _LINE_POS_RE,
    _OBJECT_NAME_RE,
    _PRIVILEGE_RE,
    _REQUIRED_PRIVILEGE_RE,
)


class SnowflakeAdapter:
    name = "snowflake"
    sqlglot_dialect = "snowflake"

    def normalize_error(self, message: str) -> NormalizedDatabaseError:
        line_match = _LINE_POS_RE.search(message)
        line = int(line_match.group(1)) if line_match else None
        position = int(line_match.group(2)) if line_match else None

        obj_match = _OBJECT_NAME_RE.search(message)
        if obj_match:
            return NormalizedDatabaseError(
                category="object_missing",
                relation=obj_match.group(2),
                line=line,
                position=position,
                raw_message=message,
            )

        id_match = _IDENTIFIER_RE.search(message)
        if id_match:
            return NormalizedDatabaseError(
                category="invalid_identifier",
                identifier=id_match.group(1),
                line=line,
                position=position,
                raw_message=message,
            )

        priv_match = _PRIVILEGE_RE.search(message)
        required = _REQUIRED_PRIVILEGE_RE.search(message)
        if priv_match:
            return NormalizedDatabaseError(
                category="permission",
                relation=required.group(3) if required else priv_match.group(2),
                required_privilege=required.group(1).upper() if required else None,
                line=line,
                position=position,
                raw_message=message,
            )

        return NormalizedDatabaseError(category="unknown", raw_message=message)

    def relation_exists(self, conn, relation: str):
        return SnowflakeMetadata(conn).relation_exists(relation)

    def describe_relation(self, conn, relation: str):
        return describe_table(conn, relation)

    def current_role(self, conn):
        return get_current_role(conn)
```

**Why safe:** No call-site switch yet; establishes a seam while reusing current regexes.

**Test:** `unit`: normalize three Snowflake messages into categories. This cannot safely replace classifier parsing until real message fixtures cover 002003/000904/003001 variants.

**Effort/risk:** medium; no dependency except wave 19.

---

# Wave 4 — artifact compatibility, orchestration, and cleanup

## 22. Make `consumed_paths.REGISTRY` truthful before tightening `schema_diff`

**Location:** `consumed_paths.py`; `schema_diff.py`.

**Source:** both.

**Before:**

```python
ConsumedPath("run-results", "results[].status"),
ConsumedPath("run-results", "results[].message", nullable_expected=True),
ConsumedPath("run-results", "results[].timing[].started_at", nullable_expected=True),
...
```

**After:**

```python
# consumed_paths.py additions
ConsumedPath("manifest", "sources[].relation_name", nullable_expected=True),
ConsumedPath("manifest", "sources[].columns"),
ConsumedPath("manifest", "parent_map", nullable_expected=True),
ConsumedPath("manifest", "nodes[].path", nullable_expected=True),
ConsumedPath("manifest", "nodes[].columns[].data_type", nullable_expected=True),
ConsumedPath("run-results", "results[].compiled_code", fallbacks=("compiled_sql",), nullable_expected=True),
ConsumedPath("run-results", "results[].failures", nullable_expected=True),
ConsumedPath("run-results", "results[].timing[].name", nullable_expected=True),
ConsumedPath("run-results", "results[].timing[].completed_at", nullable_expected=True),
```

Then add a stricter resolver report:

```python
# schema_diff.py
def _present_on_same_defs(base: SchemaDoc, new: SchemaDoc, path: str) -> bool:
    base_present = {p.defn for p in resolve(base, path) if p.present}
    new_present = {p.defn for p in resolve(new, path) if p.present}
    return base_present <= new_present
```

Use it before `present_anywhere()` for paths whose parent traverses `nodes[]` or `results[]`.

**Why safe:** Registry additions do not change runtime. Stricter diff should land only with first-party schema fixtures.

**Test:** `contract`: synthetic schema where `nodes[].relation_name` disappears from `ModelNode` but remains on `SeedNode`; today `present_anywhere()` passes; after patch it breaks.

**Effort/risk:** medium. **Needs fixture info:** first-party schema cache must be present in the repo/test snapshot to validate real dbt schema behavior before enabling CI failure.

---

## 23. Remove unreachable duplicate logic in `_is_lagging`

**Location:** `run_identity.py`, `_is_lagging`, `_to_aware_utc`.

**Source:** OUTPUT_TWO.

**Before:**

```python
except (ValueError, TypeError, AttributeError) as exc:
    logger.debug("run-lag comparison failed (%s); assuming not lagging", exc)
    return False
watermark = _history_watermark(conn)
if watermark is None:
    return True
...
return wm_dt < run_dt
```

**After:**

```python
def _is_lagging(conn, run_end_time: Optional[str]) -> bool:
    """
    Decide whether query history is behind the run timestamp. Never raises.
    """
    if not run_end_time:
        return False

    watermark = _history_watermark(conn)
    if watermark is None:
        return True

    run_dt = _to_aware_utc(run_end_time)
    wm_dt = _to_aware_utc(watermark)
    if run_dt is None or wm_dt is None:
        return False

    return wm_dt < run_dt
```

Keep `_to_aware_utc()` because it now has a live caller.

**Why safe:** Same intended logic, removes dead code and duplicate parsing.

**Test:** `unit`: naive/aware timestamp pairs compare without raising; unparseable values return false.

**Effort/risk:** small; no dependency.

---

## 24. Move provenance constants to one shared module

**Location:** `[NEW] provenance.py`; `root_cause.py`; `run_identity.py`.

**Source:** OUTPUT_ONE/OUTPUT_TWO.

**Before:**

```python
# run_identity.py
# Provenance strings mirror dbt_diagnostics.root_cause (kept local to avoid an
# import cycle; values must stay in sync).
PROV_RECOVERED = "recovered"
...
```

**After:**

```python
# [NEW] dbt_diagnostics/provenance.py
PROV_RECOVERED = "recovered"
PROV_DECLARED = "declared"
PROV_SESSION = "session"
PROV_UNKNOWN = "unknown"
```

```python
# root_cause.py and run_identity.py
from dbt_diagnostics.provenance import (
    PROV_DECLARED,
    PROV_RECOVERED,
    PROV_SESSION,
    PROV_UNKNOWN,
)
```

**Why safe:** Constant values unchanged; removes the “must stay in sync” hazard.

**Test:** `unit`: `recover_run_role(...declared_role="X")["provenance"] == PROV_DECLARED`; root-cause JSON still emits same strings.

**Effort/risk:** small; no dependency.

---

## 25. Consolidate profile discovery and dotenv loading

**Location:** `connection.py`; `discover.py`; `main.py`.

**Source:** OUTPUT_TWO.

**Before:**

```python
# connection.py
def _find_profiles_yml(project_dir: Optional[Path] = None) -> Optional[Path]:
    ...
```

**After:**

```python
# connection.py
from dbt_diagnostics.discover import find_profiles_yml

def _find_profiles_yml(project_dir: Optional[Path] = None) -> Optional[Path]:
    return find_profiles_yml(project_dir)
```

Then follow-up PR:

```python
# [NEW] dbt_diagnostics/env.py
from pathlib import Path
from typing import Optional

def load_env_file(env_file: Optional[str], project_dir: Optional[Path]) -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    if env_file:
        path = Path(env_file).resolve()
        if path.exists():
            load_dotenv(path, override=False)
        return

    if project_dir:
        for candidate in (project_dir.parent / ".env", project_dir / ".env", Path.cwd() / ".env"):
            if candidate.exists():
                load_dotenv(candidate, override=False)
                return
```

Use `load_env_file()` from both `main._load_env_file()` and `connection._load_dotenv()`.

**Why safe:** Search order remains the same; implementation lives in one place.

**Test:** `unit`: DBT_PROFILES_DIR wins over project-local and home in both discovery and connection parsing.

**Effort/risk:** small/medium; no dependency.

---

## 26. Allow explicit artifact diagnosis without a dbt project

**Location:** `main.py`, `_resolve_from_args`.

**Source:** OUTPUT_ONE.

**Before:**

```python
if project_dir is None:
    print("ERROR: Could not find a dbt project.", file=sys.stderr)
    sys.exit(1)

paths = resolve_project_paths(project_dir)
...
if args.run_results:
    paths["run_results"] = Path(args.run_results).resolve()
```

**After:**

```python
explicit_artifacts = bool(args.run_results and args.manifest)

if project_dir is None and explicit_artifacts:
    project_dir = Path.cwd()
    paths = {
        "project_dir": project_dir,
        "target_dir": project_dir / "target",
        "run_results": Path(args.run_results).resolve(),
        "manifest": Path(args.manifest).resolve(),
        "catalog": None,
        "compiled_dir": project_dir / "target" / "compiled",
        "models_dir": project_dir / "models",
    }
elif project_dir is None:
    print(
        "ERROR: Could not find a dbt project.\n"
        "  Searched upward from the current directory for dbt_project.yml.\n"
        "  Use --project-dir to specify the dbt project directory explicitly.",
        file=sys.stderr,
    )
    sys.exit(1)
else:
    paths = resolve_project_paths(project_dir)
    if args.run_results:
        paths["run_results"] = Path(args.run_results).resolve()
    if args.manifest:
        paths["manifest"] = Path(args.manifest).resolve()
```

**Why safe:** Existing project discovery unchanged. Explicit artifact mode becomes usable offline.

**Test:** `e2e`: from empty tmpdir, run with `--no-live --run-results fixture --manifest fixture --no-fail`; today exits missing project; after patch diagnoses.

**Effort/risk:** small/medium; no dependency.

---

## 27. Defer “live by default” policy change until after evidence semantics are fixed

**Location:** `main.py`, CLI flags; docs.

**Source:** OUTPUT_ONE.

**Conflict surfaced:** Changing live default before tri-state evidence could reduce bad live conclusions, but it also changes the product’s default behavior. The safer order is: first fix evidence semantics; then decide whether `--live` should be opt-in.

**Required info absent from snapshot:** maintainer product decision: keep “live by default” thesis or switch to explicit `--live`.

**Patch only after decision:**

```python
parser.add_argument(
    "--live",
    action="store_true",
    help="Run live Snowflake metadata probes",
)
parser.add_argument(
    "--no-live",
    action="store_true",
    help=argparse.SUPPRESS,
)
...
live_enabled = args.live and not args.no_live
if live_enabled:
    root_cause_groups = _try_enrich(...)
```

**Test:** `e2e`: default run does not call `open_connection`; `--live` does.

**Effort/risk:** medium product risk; depends on waves 1–3.
