"""
Tests for dbt_diagnostics/root_cause.py -- the single-root-cause aggregator.

These exercise grouping/collapse, the three live verdicts (probe mocked), and
the offline "unverified" degrade path. No database connection is used.
"""

from dbt_diagnostics.models import (
    DiagnosticReport,
    DiagnosticFinding,
    EnrichmentData,
)
from dbt_diagnostics import root_cause as rc


def _report(unique_id, msg="002003 (42S02): Object 'ARTWORK_DB.GOLD.DIM_ARTISTS' does not exist or not authorized.",
            target_object="ARTWORK_DB.GOLD.DIM_ARTISTS", query_id=None):
    finding = DiagnosticFinding(summary="object missing", target_object=target_object)
    return DiagnosticReport(
        unique_id=unique_id,
        error_class="runtime_error",
        raw_message=msg,
        findings=[finding],
        query_id=query_id,
    )


class FakeProbe:
    """Duck-typed stand-in for LiveObjectProbe."""

    def __init__(self, exists, access=None, role=("LOADER", rc.PROV_RECOVERED)):
        self._exists = exists
        self._access = access or {"has_access": False, "grants_found": [], "role_checked": role[0]}
        self._role = role

    def object_exists(self, fqn):
        return self._exists

    def access_check(self, fqn):
        return self._access

    def role_identity(self):
        return self._role


def test_detects_object_not_exist_by_message():
    assert rc.is_object_not_exist(_report("test.p.a"))


def test_detects_object_not_exist_by_enrichment_code():
    f = DiagnosticFinding(summary="x", enrichment=EnrichmentData(matched_error_code="002003"))
    r = DiagnosticReport(unique_id="test.p.b", error_class="runtime_error",
                         raw_message="some opaque message", findings=[f])
    assert rc.is_object_not_exist(r)


def test_collapses_many_into_one_group():
    reports = [_report(f"test.p.t{i}") for i in range(46)]
    groups = rc.build_root_cause_groups(reports, probe=None)
    assert len(groups) == 1
    assert groups[0].occurrences == 46
    assert groups[0].object_names == ["ARTWORK_DB.GOLD.DIM_ARTISTS"]


def test_distinct_objects_form_distinct_groups():
    reports = [
        _report("test.p.a", target_object="ARTWORK_DB.GOLD.DIM_ARTISTS"),
        _report("test.p.b", target_object="ARTWORK_DB.GOLD.FCT_SALES",
                msg="002003: Object 'ARTWORK_DB.GOLD.FCT_SALES' does not exist or not authorized"),
    ]
    groups = rc.build_root_cause_groups(reports, probe=None)
    assert len(groups) == 2


def test_offline_is_unverified_with_query():
    groups = rc.build_root_cause_groups([_report("test.p.a")], probe=None)
    g = groups[0]
    assert g.verdict == rc.VERDICT_UNVERIFIED
    assert g.probe_queries  # carries the SHOW TABLES query to run
    assert "SHOW TABLES" in g.probe_queries[0]


def test_verdict_never_built_when_absent_and_no_grants():
    probe = FakeProbe(exists=False)
    g = rc.build_root_cause_groups([_report("test.p.a")], probe=probe)[0]
    assert g.verdict == rc.VERDICT_NEVER_BUILT
    assert "dbt build" in (g.fix or "")
    assert g.role_checked == "LOADER"
    assert g.role_provenance == rc.PROV_RECOVERED


def test_verdict_exists_now_when_present():
    probe = FakeProbe(exists=True)
    g = rc.build_root_cause_groups([_report("test.p.a")], probe=probe)[0]
    assert g.verdict == rc.VERDICT_EXISTS_NOW
    assert "re-run" in (g.fix or "").lower()


def test_verdict_denied_when_absent_but_grants_present():
    access = {"has_access": False, "grants_found": ["SELECT on TABLE ARTWORK_DB.GOLD.DIM_ARTISTS"],
              "role_checked": "LOADER"}
    probe = FakeProbe(exists=False, access=access)
    g = rc.build_root_cause_groups([_report("test.p.a")], probe=probe)[0]
    assert g.verdict == rc.VERDICT_DENIED
    assert "GRANT" in (g.fix or "")


def test_verdict_denied_when_probe_blind_and_no_access():
    # object_exists returns None (probe could not run, e.g. no schema USAGE)
    probe = FakeProbe(exists=None, access={"has_access": False, "grants_found": [], "role_checked": "LOADER"})
    g = rc.build_root_cause_groups([_report("test.p.a")], probe=probe)[0]
    assert g.verdict == rc.VERDICT_DENIED


def test_to_json_dict_is_additive_and_stable():
    g = rc.build_root_cause_groups([_report("test.p.a")], probe=None)[0]
    d = g.to_json_dict()
    for key in ("signature", "error_class", "occurrences", "verdict",
                "object_names", "member_unique_ids", "probe_queries",
                "role_checked", "role_provenance", "confidence"):
        assert key in d
    assert d["occurrences"] == 1
