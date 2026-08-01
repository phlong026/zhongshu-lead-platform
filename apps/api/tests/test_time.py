from datetime import datetime, timedelta, timezone

from apps.api.src.core.time import as_utc, utcnow


def test_as_utc_normalizes_sqlite_naive_timestamp():
    naive = datetime(2026, 8, 1, 12, 0, 0)
    normalized = as_utc(naive)
    assert normalized.tzinfo == timezone.utc
    assert normalized.isoformat() == "2026-08-01T12:00:00+00:00"


def test_as_utc_preserves_instant_for_aware_timestamp():
    aware = datetime(2026, 8, 1, 20, 0, 0, tzinfo=timezone(timedelta(hours=8)))
    assert as_utc(aware).isoformat() == "2026-08-01T12:00:00+00:00"
    assert utcnow().tzinfo == timezone.utc
