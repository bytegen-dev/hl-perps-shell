from datetime import UTC, datetime

import pytest
from hl_historical.exceptions import TimestampParseError
from hl_historical.timeparse import parse_timestamp, to_epoch_ms


def test_parse_timestamp_iso_and_unix() -> None:
    iso = parse_timestamp("2026-08-13T12:00:00Z")
    assert iso == datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    assert to_epoch_ms("2026-08-13T12:00:00Z") == int(iso.timestamp() * 1000)
    assert to_epoch_ms(1_700_000_000) == 1_700_000_000_000


def test_parse_flexible_gmt_plus_one_today() -> None:
    reference = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    parsed = parse_timestamp("9:35am GMT+1 today", reference=reference)
    assert parsed == datetime(2026, 8, 13, 8, 35, tzinfo=UTC)


def test_parse_flexible_utc_today() -> None:
    reference = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
    parsed = parse_timestamp("9:35am UTC today", reference=reference)
    assert parsed == datetime(2026, 8, 13, 9, 35, tzinfo=UTC)


def test_parse_flexible_with_explicit_date() -> None:
    parsed = parse_timestamp("9:35am GMT+1 2026-08-02")
    assert parsed == datetime(2026, 8, 2, 8, 35, tzinfo=UTC)


def test_parse_flexible_requires_date() -> None:
    with pytest.raises(TimestampParseError):
        parse_timestamp("9:35am GMT+1")
