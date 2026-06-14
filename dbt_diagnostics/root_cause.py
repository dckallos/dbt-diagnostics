"""
dbt_diagnostics/root_cause.py

Collapses many same-signature errors into a single root-cause group. For the
Snowflake "object does not exist" family (error 002003), it uses a live probe
to disambiguate the one true cause instead of repeating N identical lines:

  - none exist now  -> tests ran before the models were materialized; the fix
                       is `dbt build`, not `dbt test`.
  - exists now      -> the object was built by another process or after this
                       run started; re-run.
  - exists, denied  -> the run's role cannot see it; route to a grant check.

Tier A only: every probe is $0 cloud-services metadata (SHOW TABLES,
SHOW GRANTS, INFORMATION_SCHEMA.QUERY_HISTORY). When there is no live
connection -- or a probe cannot confirm state -- the verdict degrades to
"unverified" and carries the exact query to run. Nothing here raises.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from dbt_diagnostics.models import DiagnosticReport

# Snowflake error code for "object does not exist or not authorized". Snowflake
# deliberately conflates absence and missing privilege in this one code, which
# is exactly why the live probe below is needed to tell them apart.
OBJECT_NOT_EXIST_CODE = "002003"

_OBJECT_NOT_EXIST_RE = re.compile(
    r"002003|does not exist or not authorized|Object\s+'[^']+'\s+does not exist",
    re.IGNORECASE,
)

# A fully qualified DB.SCHEMA.OBJECT inside single quotes in an error message.
_FQN_RE = re.compile(r"'([A-Za-z0-9_$]+\.[A-Za-z0-9_$]+\.[A-Za-z0-9_$]+)'")

# Verdict identifiers (stable; emitted in JSON).
VERDICT_NEVER_BUILT = "never_built"
VERDICT_EXISTS_NOW = "exists_now"
VERDICT_DENIED = "denied"
VERDICT_UNVERIFIED = "unverified"

# Role-provenance identifiers (how trustworthy the role we report is).
PROV_RECOVERED = "recovered"   # read from query history -- the role the run used
PROV_DECLARED = "declared"     # resolved from the dbt profile/target
PROV_SESSION = "session"       # the diagnostic connection's own role
PROV_UNKNOWN = "unknown"


@dataclass
class RootCauseGroup:
    """One collapsed root cause shared by N same-signature errors."""

    signature: str
    error_class: str
    title: str
    object_names: list[str]
    reports: list[DiagnosticReport] = field(default_factory=list)
    verdict: str = VERDICT_UNVERIFIED
    headline: str = ""
    detail: str = ""
    fix: Optional[str] = None
    role_checked: Optional[str] = None
    role_provenance: str = PROV_UNKNOWN
    probe_queries: list[str] = field(default_factory=list)
    confidence: str = "low"
    representative: Optional[DiagnosticReport] = None

    @property
    def occurrences(self) -> int:
        return len(self.reports)

    @property
    def representative_finding(self):
        """The first finding of the representative report, if any (for the
        lineage_trace partial)."""
        rep = self.representative or (self.reports[0] if self.reports else None)
        if rep and rep.findings:
            return rep.findings[0]
        return None

    def to_json_dict(self) -> dict:
        return {
            "signature": self.signature,
            "error_class": self.error_class,
            "title": self.title,
            "object_names": self.object_names,
            "occurrences": self.occurrences,
            "member_unique_ids": [r.unique_id for r in self.reports],
            "verdict": self.verdict,
            "headline": self.headline,
            "detail": self.detail,
            "fix": self.fix,
            "role_checked": self.role_checked,
            "role_provenance": self.role_provenance,
            "probe_queries": self.probe_queries,
            "confidence": self.confidence,
        }


def is_object_not_exist(report: DiagnosticReport) -> bool:
    """True if a report is the Snowflake "object does not exist" family."""
    parts = [report.raw_message or ""]
    if report.dbt_message:
        parts.append(report.dbt_message)
    for finding in report.findings:
        if finding.enrichment and finding.enrichment.matched_error_code:
            if str(finding.enrichment.matched_error_code) == OBJECT_NOT_EXIST_CODE:
                return True
    return bool(_OBJECT_NOT_EXIST_RE.search(" ".join(parts)))


def object_fqn(report: DiagnosticReport) -> Optional[str]:
    """Best-effort fully qualified name of the missing object."""
    for finding in report.findings:
        if finding.target_object and finding.target_object.count(".") >= 2:
            return finding.target_object.upper()
        if finding.target_identifier and finding.target_identifier.count(".") >= 2:
            return finding.target_identifier.upper()
    if report.relation and report.relation.count(".") >= 2:
        return report.relation.upper()
    match = _FQN_RE.search(report.raw_message or "")
    if match:
        return match.group(1).upper()
    return None


def _model_names(reports: list[DiagnosticReport]) -> list[str]:
    names: list[str] = []
    for report in reports:
        short = report.unique_id.split(".")[-1]
        if short and short not in names:
            names.append(short)
    return names


def _show_tables_query(fqn: str) -> str:
    parts = fqn.split(".")
    if len(parts) == 3:
        db, schema, table = parts
        return f"SHOW TABLES LIKE '{table}' IN {db}.{schema}"
    return f"SHOW TABLES LIKE '{fqn}'"


def build_root_cause_groups(
    reports: list[DiagnosticReport],
    probe: Optional["LiveObjectProbe"] = None,
) -> list[RootCauseGroup]:
    """
    Collapse "object does not exist" errors into one group per missing object
    and attach a single disambiguated verdict.

    probe is optional: when None (offline, or the connector is unavailable) the
    verdict degrades to "unverified" with the query to run. Grouping itself
    never needs a database.
    """
    buckets: dict[str, list[DiagnosticReport]] = {}
    for report in reports:
        if not is_object_not_exist(report):
            continue
        fqn = object_fqn(report) or "UNKNOWN"
        buckets.setdefault(fqn, []).append(report)

    groups: list[RootCauseGroup] = []
    for fqn, members in buckets.items():
        group = RootCauseGroup(
            signature=f"object_not_exist:{fqn}",
            error_class="object_not_exist",
            title=f"{len(members)} error(s): object {fqn} does not exist",
            object_names=[fqn],
            reports=members,
            representative=members[0],
        )
        _apply_verdict(group, fqn, probe)
        groups.append(group)

    # Stable ordering: most-collapsed first, then by object name.
    groups.sort(key=lambda g: (-g.occurrences, g.object_names[0]))
    return groups


def _apply_verdict(group: RootCauseGroup, fqn: str, probe: Optional["LiveObjectProbe"]) -> None:
    models = _model_names(group.reports)
    show_q = _show_tables_query(fqn)
    group.probe_queries.append(show_q)

    if probe is None or fqn == "UNKNOWN":
        group.verdict = VERDICT_UNVERIFIED
        group.headline = f"Object {fqn} reported missing -- UNVERIFIED (offline)"
        group.detail = (
            "No live connection, so existence and access could not be "
            "confirmed. Run the query below; if it returns no rows the object "
            "was never built, otherwise check grants for the run's role."
        )
        group.fix = _fix_unverified(show_q, models)
        group.confidence = "low"
        return

    role, provenance = probe.role_identity()
    group.role_checked = role
    group.role_provenance = provenance
    exists = probe.object_exists(fqn)

    if exists is True:
        group.verdict = VERDICT_EXISTS_NOW
        group.headline = f"Object {fqn} EXISTS now"
        group.detail = (
            "The object is present at probe time even though the run failed on "
            "it. It was likely built by another process, or after this run "
            "started -- a re-run should pass. Note: existence now does not "
            "prove it existed at run time, so a recurring failure points to a "
            "DAG-ordering bug rather than a transient one."
        )
        group.fix = (
            "Re-run to confirm it was a transient/ordering issue:\n"
            f"  dbt build -s {' '.join(models)}"
        )
        group.confidence = "medium"
        return

    if exists is False:
        access = probe.access_check(fqn)
        if role:
            group.probe_queries.append(f"SHOW GRANTS TO ROLE {role}")
        if access and access.get("grants_found"):
            group.verdict = VERDICT_DENIED
            group.headline = f"Object {fqn} is NOT visible to role {role or '<run-role>'}"
            group.detail = (
                f"SHOW TABLES returned nothing, but role {role or '<run-role>'} "
                "holds grants touching this object -- the object likely exists "
                "but is not visible to this role. Treat as a privilege issue."
            )
            group.fix = _fix_denied(fqn, role)
            group.confidence = "medium"
        else:
            group.verdict = VERDICT_NEVER_BUILT
            group.headline = f"Object {fqn} does NOT exist"
            group.detail = (
                "The object is absent. These are tests that ran before their "
                "models were materialized -- run a full build so the models "
                "exist before tests execute."
            )
            group.fix = (
                "Materialize the models, then test (use `dbt build`, which "
                "interleaves run + test in DAG order -- not `dbt test`):\n"
                f"  dbt build -s {' '.join(models)}"
            )
            group.confidence = "high"
        return

    # exists is None: the probe itself could not run (e.g. no USAGE on the
    # schema). That is itself a strong privilege signal, but unproven -- route
    # to a grant check and stay honest about the uncertainty.
    access = probe.access_check(fqn)
    if role:
        group.probe_queries.append(f"SHOW GRANTS TO ROLE {role}")
    if access and not access.get("has_access", False):
        group.verdict = VERDICT_DENIED
        group.headline = (
            f"Cannot confirm {fqn}; role {role or '<run-role>'} lacks visibility"
        )
        group.detail = (
            "The existence probe could not run (likely no USAGE on the schema), "
            "which usually means a privilege problem rather than a missing "
            "object. Verify the grants below before assuming the object is gone."
        )
        group.fix = _fix_denied(fqn, role)
        group.confidence = "low"
    else:
        group.verdict = VERDICT_UNVERIFIED
        group.headline = f"Object {fqn} state UNVERIFIED (probe failed)"
        group.detail = (
            "The live probe did not return a usable result. Run the query "
            "below manually to determine existence vs access."
        )
        group.fix = _fix_unverified(show_q, models)
        group.confidence = "low"


def _fix_unverified(show_q: str, models: list[str]) -> str:
    return (
        "Confirm existence directly, then act on the result:\n"
        f"  {show_q};\n"
        "  -- no rows  -> never built: run `dbt build -s "
        f"{' '.join(models)}`\n"
        "  -- rows     -> built/transient: re-run, or check grants if the run "
        "role differs from yours."
    )


def _fix_denied(fqn: str, role: Optional[str]) -> str:
    parts = fqn.split(".")
    schema_fq = ".".join(parts[:2]) if len(parts) >= 2 else fqn
    role_name = role or "<run-role>"
    return (
        f"Grant the run's role read access (run as an owner of {schema_fq}):\n"
        f"  GRANT USAGE ON DATABASE {parts[0]} TO ROLE {role_name};\n"
        f"  GRANT USAGE ON SCHEMA {schema_fq} TO ROLE {role_name};\n"
        f"  GRANT SELECT ON {fqn} TO ROLE {role_name};"
    )


class LiveObjectProbe:
    """
    Tier-A live probe used to disambiguate object-not-exist verdicts.

    Wraps an open Snowflake connection plus the role the dbt run declared. All
    methods swallow errors and return None / empty so a flaky connection
    degrades to "unverified" rather than crashing the diagnostic.
    """

    def __init__(self, conn, declared_role: Optional[str] = None,
                 run_results: Optional[dict] = None,
                 representative_query_id: Optional[str] = None):
        self.conn = conn
        self.declared_role = declared_role
        self.run_results = run_results
        self.representative_query_id = representative_query_id
        self._exists_cache: dict[str, Optional[bool]] = {}
        self._access_cache: dict[str, dict] = {}
        self._role_identity: Optional[tuple] = None

    def object_exists(self, fqn: str) -> Optional[bool]:
        if fqn in self._exists_cache:
            return self._exists_cache[fqn]
        try:
            from dbt_diagnostics.enrichers.schema_inspector import table_exists
            result = table_exists(self.conn, fqn)
        except Exception:
            result = None
        self._exists_cache[fqn] = result
        return result

    def access_check(self, fqn: str) -> dict:
        if fqn in self._access_cache:
            return self._access_cache[fqn]
        role, _ = self.role_identity()
        result: dict = {"has_access": False, "grants_found": [], "role_checked": role}
        if role:
            try:
                from dbt_diagnostics.enrichers.grants import check_role_grants
                result = check_role_grants(self.conn, role, fqn)
            except Exception:
                pass
        self._access_cache[fqn] = result
        return result

    def role_identity(self) -> tuple:
        """Return (role_name, provenance) using the fidelity ladder."""
        if self._role_identity is not None:
            return self._role_identity
        role, provenance = None, PROV_UNKNOWN
        try:
            from dbt_diagnostics.enrichers.run_identity import recover_run_role
            recovered = recover_run_role(
                self.conn,
                query_id=self.representative_query_id,
                run_results=self.run_results,
                declared_role=self.declared_role,
            )
            role = recovered.get("role")
            provenance = recovered.get("provenance", PROV_UNKNOWN)
        except Exception:
            if self.declared_role:
                role, provenance = self.declared_role, PROV_DECLARED
        self._role_identity = (role, provenance)
        return self._role_identity
