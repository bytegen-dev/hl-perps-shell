from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from hl_historical.exceptions import TimestampParseError

_FLEXIBLE_AT_RE = re.compile(
    r"""
    ^
    (?:(?P<date>today|yesterday|\d{4}-\d{2}-\d{2})\s+)?
    (?P<hour>\d{1,2})
    (?::(?P<minute>\d{2}))?
    \s*(?P<ampm>am|pm)?
    \s+
    (?P<tz>(?:GMT|UTC)(?:[+-]\d{1,2}(?::\d{2})?)?|[+-]\d{1,2}(?::\d{2})?|[A-Za-z0-9_/+.-]+)
    (?:\s+(?P<date_tail>today|yesterday|\d{4}-\d{2}-\d{2}))?
    $
    """,
    re.IGNORECASE | re.VERBOSE,
)


def parse_timestamp(
    value: str | int | float | datetime,
    *,
    reference: datetime | None = None,
) -> datetime:
    """Parse a timestamp into UTC.

    Supports ISO-8601, unix seconds/ms, and flexible strings like:
    - ``9:35am GMT+1 today``
    - ``2026-08-13 09:35 UTC``
    - ``09:35 Europe/London today``
    """
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    if isinstance(value, (int, float)):
        ms = int(value)
        if ms < 10_000_000_000:
            ms *= 1000
        return datetime.fromtimestamp(ms / 1000, tz=UTC)

    text = value.strip()
    if text.isdigit():
        return parse_timestamp(int(text), reference=reference)

    now = reference or datetime.now(UTC)
    flexible = _parse_flexible(text, now=now)
    if flexible is not None:
        return flexible.astimezone(UTC)

    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise TimestampParseError(
            f"Unable to parse timestamp: {value}. "
            "Try ISO-8601, unix ms, or formats like '9:35am GMT+1 today'."
        ) from exc

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def to_epoch_ms(
    value: str | int | float | datetime,
    *,
    reference: datetime | None = None,
) -> int:
    return int(parse_timestamp(value, reference=reference).timestamp() * 1000)


def _parse_flexible(text: str, *, now: datetime) -> datetime | None:
    match = _FLEXIBLE_AT_RE.match(text.strip())
    if match is None:
        return None

    groups = match.groupdict()
    date_token = groups["date"] or groups["date_tail"]
    if date_token is None:
        raise TimestampParseError(
            f"Unable to parse timestamp: {text}. Include a date such as 'today' or '2026-08-13'."
        )

    hour = int(groups["hour"])
    minute = int(groups["minute"] or 0)
    hour, minute = _normalize_clock(hour, minute, groups["ampm"])
    day = _resolve_date_token(date_token, now=now)
    tzinfo = _parse_timezone(groups["tz"])

    local_dt = datetime(day.year, day.month, day.day, hour, minute, tzinfo=tzinfo)
    return local_dt


def _normalize_clock(hour: int, minute: int, ampm: str | None) -> tuple[int, int]:
    if minute > 59:
        raise TimestampParseError(f"Invalid minute: {minute}")
    if ampm:
        ampm_lower = ampm.lower()
        if hour < 1 or hour > 12:
            raise TimestampParseError(
                f"Invalid 12-hour clock time: {hour}:{minute:02d}{ampm_lower}"
            )
        if ampm_lower == "pm" and hour != 12:
            hour += 12
        elif ampm_lower == "am" and hour == 12:
            hour = 0
    elif hour > 23:
        raise TimestampParseError(f"Invalid 24-hour clock time: {hour}:{minute:02d}")
    return hour, minute


def _resolve_date_token(token: str, *, now: datetime) -> datetime.date:
    lowered = token.lower()
    base = now.astimezone(UTC).date()
    if lowered == "today":
        return base
    if lowered == "yesterday":
        return base - timedelta(days=1)
    try:
        return datetime.fromisoformat(token).date()
    except ValueError as exc:
        raise TimestampParseError(f"Invalid date token: {token}") from exc


def _parse_timezone(token: str) -> tzinfo:
    raw = token.strip()
    compact = raw.upper().replace(" ", "")

    if compact in {"UTC", "GMT", "Z"}:
        return UTC

    offset_match = re.fullmatch(r"(?:GMT|UTC)?([+-]\d{1,2})(?::(\d{2}))?", compact)
    if offset_match:
        return _fixed_offset(
            int(offset_match.group(1)),
            int(offset_match.group(2) or 0),
        )

    try:
        return ZoneInfo(raw)
    except ZoneInfoNotFoundError as exc:
        raise TimestampParseError(f"Unknown timezone: {token}") from exc


def _fixed_offset(hours: int, minutes: int) -> timezone:
    if hours == 0:
        delta = timedelta(minutes=minutes)
    elif hours > 0:
        delta = timedelta(hours=hours, minutes=minutes)
    else:
        delta = timedelta(hours=hours, minutes=-minutes)
    return timezone(delta, name=f"UTC{hours:+d}:{minutes:02d}")
