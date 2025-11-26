"""
Utility for resolving date ranges from intent payloads.

Supported inputs:
- Named ranges defined in tenant config (e.g., "last_12_months").
- Absolute dates: {"custom": {"start": "2024-01-01", "end": "2024-03-31"}}
- Relative periods: {"custom": {"period": "2024-Q1"}} or {"custom": {"month": "2024-03"}}
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, Tuple
import calendar


class DateResolutionError(ValueError):
    """Raise when date ranges cannot be interpreted."""


def resolve_date_range(intent: Dict, config: Dict) -> Tuple[str, str]:
    """
    Return (start_date_iso, end_date_iso) for the intent.
    """
    custom = intent.get("custom_date")
    if custom:
        return _resolve_custom_range(custom)

    date_range = intent.get("date_range")
    if not date_range:
        raise DateResolutionError("No date range specified.")

    # Special calendar-month handling independent of config days
    today = date.today()
    if date_range in {"last_month", "previous_month"}:
        year = today.year if today.month != 1 else today.year - 1
        month = today.month - 1 or 12
        start = date(year, month, 1)
        end = date(year, month, calendar.monthrange(year, month)[1])
        return start.isoformat(), end.isoformat()
    if date_range in {"this_month", "current_month"}:
        start = date(today.year, today.month, 1)
        end = date(today.year, today.month, calendar.monthrange(today.year, today.month)[1])
        return start.isoformat(), end.isoformat()

    config_ranges = config.get("date_ranges", {})
    days = config_ranges.get(date_range)
    if days is None:
        raise DateResolutionError(f"Unsupported date range: {date_range}")

    end = today
    start = end - timedelta(days=int(days))
    return start.isoformat(), end.isoformat()


def _resolve_custom_range(custom: Dict) -> Tuple[str, str]:
    if "start" in custom and "end" in custom:
        return _validate_dates(custom["start"], custom["end"])

    if "period" in custom:
        return _resolve_iso_period(custom["period"])

    if "month" in custom:
        return _resolve_month(custom["month"])

    raise DateResolutionError(f"Unsupported custom date payload: {custom}")


def _validate_dates(start_str: str, end_str: str) -> Tuple[str, str]:
    try:
        start = date.fromisoformat(start_str)
        end = date.fromisoformat(end_str)
    except ValueError as exc:
        raise DateResolutionError(f"Invalid date format: {start_str}, {end_str}") from exc

    if start > end:
        raise DateResolutionError("Start date must be before end date.")

    return start.isoformat(), end.isoformat()


def _resolve_iso_period(period: str) -> Tuple[str, str]:
    if "-" not in period:
        raise DateResolutionError("Period must be like '2024-Q1'.")
    year_str, token = period.split("-", 1)
    year = int(year_str)

    token_upper = token.upper()
    if token_upper.startswith("Q"):
        quarter = int(token_upper[1])
        if quarter not in {1, 2, 3, 4}:
            raise DateResolutionError(f"Invalid quarter: {token}")
        month = (quarter - 1) * 3 + 1
        start = date(year, month, 1)
        end = _end_of_month(_add_months(start, 2))
        return start.isoformat(), end.isoformat()

    if token_upper == "FY":
        start = date(year, 1, 1)
        end = date(year, 12, 31)
        return start.isoformat(), end.isoformat()

    raise DateResolutionError(f"Unsupported period token: {token}")


def _resolve_month(month_token: str) -> Tuple[str, str]:
    try:
        dt = datetime.strptime(month_token, "%Y-%m")
    except ValueError as exc:
        raise DateResolutionError("Month must be 'YYYY-MM'.") from exc

    start = date(dt.year, dt.month, 1)
    end = _end_of_month(start)
    return start.isoformat(), end.isoformat()


def _end_of_month(start: date) -> date:
    next_month = _add_months(start, 1)
    return next_month - timedelta(days=1)


def _add_months(source: date, months: int) -> date:
    month = source.month - 1 + months
    year = source.year + month // 12
    month = month % 12 + 1
    day = min(source.day, [31, 29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


__all__ = ["resolve_date_range", "DateResolutionError"]
