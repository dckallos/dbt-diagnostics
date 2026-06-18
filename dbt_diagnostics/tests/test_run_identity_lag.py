"""Unit tests for run-lag detection (_is_lagging / _as_utc). Regression for #50:
a naive run timestamp paired with an aware history watermark must not raise."""

from datetime import datetime, timezone

import pytest

from dbt_diagnostics.enrichers import run_identity as ri

pytestmark = pytest.mark.unit


class _FakeCursor:
    def __init__(self, value):
        self._value = value

    def execute(self, *args, **kwargs):
        return None

    def fetchone(self):
        return [self._value]

    def close(self):
        return None


class _FakeConn:
    """Minimal connection whose history watermark query returns `watermark`."""

    def __init__(self, watermark):
        self._watermark = watermark

    def cursor(self):
        return _FakeCursor(self._watermark)


def test_as_utc_coerces_naive_to_utc_and_preserves_aware():
    naive = datetime(2026, 1, 1, 12, 0, 0)
    assert ri._as_utc(naive).tzinfo is timezone.utc
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert ri._as_utc(aware) is aware


def test_no_run_end_time_is_not_lagging():
    assert ri._is_lagging(_FakeConn("2026-01-01T00:00:00Z"), None) is False


def test_no_watermark_is_lagging():
    assert ri._is_lagging(_FakeConn(None), "2026-01-01T12:00:00Z") is True


def test_aware_watermark_behind_run_is_lagging():
    wm = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
    assert ri._is_lagging(_FakeConn(wm), "2026-01-01T12:00:00Z") is True


def test_aware_watermark_ahead_of_run_is_not_lagging():
    wm = datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
    assert ri._is_lagging(_FakeConn(wm), "2026-01-01T12:00:00Z") is False


def test_naive_run_with_aware_watermark_does_not_raise():
    # The #50 regression: naive run_end_time (no offset) + aware watermark.
    wm_behind = datetime(2026, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
    assert ri._is_lagging(_FakeConn(wm_behind), "2026-01-01T12:00:00") is True
    wm_ahead = datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
    assert ri._is_lagging(_FakeConn(wm_ahead), "2026-01-01T12:00:00") is False


def test_aware_run_with_naive_watermark_does_not_raise():
    wm_naive_behind = datetime(2026, 1, 1, 11, 0, 0)
    assert ri._is_lagging(_FakeConn(wm_naive_behind), "2026-01-01T12:00:00Z") is True


def test_string_watermark_is_parsed():
    assert ri._is_lagging(_FakeConn("2026-01-01T11:00:00Z"), "2026-01-01T12:00:00Z") is True


def test_unparseable_watermark_is_not_lagging():
    assert ri._is_lagging(_FakeConn("not-a-timestamp"), "2026-01-01T12:00:00Z") is False


def test_unrecognized_watermark_type_is_not_lagging():
    assert ri._is_lagging(_FakeConn(12345), "2026-01-01T12:00:00Z") is False
