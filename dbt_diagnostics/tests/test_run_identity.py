"""
Tests for dbt_diagnostics/enrichers/run_identity.py -- recover the run's role
from query history, with honest "not yet vs never" detection and fallbacks.

A small programmable fake connection stands in for snowflake.connector. No real
database is used. retries=0 keeps the bounded-retry path from sleeping.
"""

from dbt_diagnostics.enrichers import run_identity as ri


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self._result = None

    def execute(self, sql, params=None):
        self.conn.calls.append((sql, params))
        if "MAX(END_TIME)" in sql:
            self._result = [self.conn.watermark]
        elif "CURRENT_ROLE" in sql:
            self._result = [self.conn.session_role]
        elif "QUERY_ID" in sql:
            self._result = self.conn.row_for_qid
        else:
            self._result = None

    def fetchone(self):
        return self._result

    def close(self):
        pass


class _FakeConn:
    def __init__(self, row_for_qid=None, watermark=None, session_role=None):
        self.row_for_qid = row_for_qid
        self.watermark = watermark
        self.session_role = session_role
        self.calls = []

    def cursor(self):
        return _FakeCursor(self)


_RUN_END = "2026-06-14T10:00:00"


def test_recovered_when_query_id_present():
    conn = _FakeConn(row_for_qid=["LOADER", "svc", "WH", "FAIL", _RUN_END])
    out = ri.recover_role_by_query_id(conn, "q1", run_end_time=_RUN_END, retries=0)
    assert out["status"] == ri.STATUS_RECOVERED
    assert out["role"] == "LOADER"


def test_no_query_id_status():
    conn = _FakeConn()
    out = ri.recover_role_by_query_id(conn, None)
    assert out["status"] == ri.STATUS_NO_QUERY_ID
    assert out["role"] is None
    assert out["queries"]  # still surfaces the query to run


def test_not_found_when_history_ahead_of_run():
    # Watermark newer than the run -> history has caught up; the id is simply
    # not there -> "never", do not retry.
    conn = _FakeConn(row_for_qid=None, watermark="2026-06-14T11:00:00")
    out = ri.recover_role_by_query_id(conn, "q1", run_end_time=_RUN_END, retries=0)
    assert out["status"] == ri.STATUS_NOT_FOUND


def test_lagging_when_history_behind_run():
    # Watermark older than the run -> history is still catching up -> "not yet".
    conn = _FakeConn(row_for_qid=None, watermark="2026-06-14T09:00:00")
    out = ri.recover_role_by_query_id(conn, "q1", run_end_time=_RUN_END, retries=0)
    assert out["status"] == ri.STATUS_LAGGING


def test_recover_run_role_flags_drift():
    conn = _FakeConn(row_for_qid=["LOADER", "svc", "WH", "FAIL", _RUN_END])
    out = ri.recover_run_role(conn, query_id="q1", declared_role="TRANSFORMER", retries=0)
    assert out["provenance"] == ri.PROV_RECOVERED
    assert out["role"] == "LOADER"
    assert "drift" in out


def test_recover_run_role_declared_fallback():
    conn = _FakeConn(row_for_qid=None, watermark="2026-06-14T11:00:00")
    out = ri.recover_run_role(conn, query_id="q1", declared_role="TRANSFORMER", retries=0)
    assert out["provenance"] == ri.PROV_DECLARED
    assert out["role"] == "TRANSFORMER"


def test_recover_run_role_session_fallback():
    conn = _FakeConn(row_for_qid=None, watermark="2026-06-14T11:00:00", session_role="SYSADMIN")
    out = ri.recover_run_role(conn, query_id="q1", declared_role=None, retries=0)
    assert out["provenance"] == ri.PROV_SESSION
    assert out["role"] == "SYSADMIN"


def test_recover_run_role_unknown_when_nothing_available():
    conn = _FakeConn(row_for_qid=None, watermark="2026-06-14T11:00:00", session_role=None)
    out = ri.recover_run_role(conn, query_id=None, declared_role=None, retries=0)
    assert out["provenance"] == ri.PROV_UNKNOWN
    assert out["role"] is None
