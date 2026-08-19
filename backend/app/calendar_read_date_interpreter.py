from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from app.calendar_range_service import MAX_CALENDAR_RANGE_DAYS
from app.calendar_service import (
    CalendarIntegrationError,
    _get_timezone,
    get_calendar_config,
)


_MONTHS = {
    name.casefold(): index
    for index, name in enumerate(calendar.month_name)
    if name
}
_MONTHS.update(
    {
        name.casefold(): index
        for index, name in enumerate(calendar.month_abbr)
        if name
    }
)
_WEEKDAYS = {
    name.casefold(): index
    for index, name in enumerate(calendar.day_name)
}
_WEEKDAYS.update(
    {
        name.casefold(): index
        for index, name in enumerate(calendar.day_abbr)
    }
)

_MONTH_PATTERN = "(?:" + "|".join(
    sorted((re.escape(name) for name in _MONTHS), key=len, reverse=True)
) + ")"
_WEEKDAY_PATTERN = "(?:" + "|".join(
    sorted((re.escape(name) for name in _WEEKDAYS), key=len, reverse=True)
) + ")"

_READ_SIGNAL_RE = re.compile(
    r"\b(?:calendar|agenda|appointments?|events?|meetings?|schedule)\b"
    r"|\b(?:am\s+i|are\s+we|will\s+i\s+be)\s+(?:free|available|busy|booked)\b"
    r"|\b(?:do\s+i|do\s+we)\s+have\s+(?:anything|something|plans?|meetings?|events?)\b",
    re.IGNORECASE,
)
_WRITE_LEAD_RE = re.compile(
    r"^\s*(?:(?:please\s+)?|(?:can|could|would|will)\s+you\s+(?:please\s+)?|"
    r"i\s+(?:want|need)\s+you\s+to\s+|i(?:'d|\s+would)\s+like\s+you\s+to\s+)"
    r"(?:add|create|schedule|book|put|move|reschedule|edit|change|update|delete|remove|cancel)\b",
    re.IGNORECASE,
)
_LEGACY_DAY_RE = re.compile(r"\b(?:today|tomorrow)\b", re.IGNORECASE)


@dataclass(frozen=True)
class CalendarReadWindow:
    start_date: date
    end_date: date

    @property
    def day_count(self) -> int:
        return (self.end_date - self.start_date).days + 1

    def as_arguments(self) -> dict[str, str]:
        return {
            "startDate": self.start_date.isoformat(),
            "endDate": self.end_date.isoformat(),
        }


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().casefold())


def _calendar_reference_date() -> date:
    """Use the same timezone basis as canonical Calendar state when possible."""

    try:
        config = get_calendar_config()
        return datetime.now(_get_timezone(config)).date()
    except CalendarIntegrationError:
        return date.today()


def _bounded_window(start_date: date, end_date: date) -> CalendarReadWindow | None:
    if end_date < start_date:
        return None
    window = CalendarReadWindow(start_date=start_date, end_date=end_date)
    if window.day_count > MAX_CALENDAR_RANGE_DAYS:
        return None
    return window


def _monday_for(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _resolve_weekday(
    reference_date: date,
    weekday_index: int,
    qualifier: str | None,
) -> date:
    if qualifier == "next":
        next_monday = _monday_for(reference_date) + timedelta(days=7)
        return next_monday + timedelta(days=weekday_index)

    current_monday = _monday_for(reference_date)
    candidate = current_monday + timedelta(days=weekday_index)
    if qualifier == "this":
        return candidate if candidate >= reference_date else candidate + timedelta(days=7)

    days_ahead = (weekday_index - reference_date.weekday()) % 7
    return reference_date + timedelta(days=days_ahead)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_month_day(
    month_token: str,
    day_token: str,
    year_token: str | None,
    reference_date: date,
) -> date | None:
    month = _MONTHS.get(month_token.casefold())
    if month is None:
        return None
    day = int(re.sub(r"(?:st|nd|rd|th)$", "", day_token.casefold()))
    year = int(year_token) if year_token else reference_date.year
    return _safe_date(year, month, day)


def _month_bounds(reference_date: date, *, offset: int) -> CalendarReadWindow | None:
    absolute_month = reference_date.year * 12 + (reference_date.month - 1) + offset
    year, zero_based_month = divmod(absolute_month, 12)
    month = zero_based_month + 1
    last_day = calendar.monthrange(year, month)[1]
    return _bounded_window(date(year, month, 1), date(year, month, last_day))


def resolve_calendar_read_window(
    user_message: str,
    *,
    reference_date: date | None = None,
) -> CalendarReadWindow | None:
    """Resolve clear non-legacy Calendar date language to one absolute window.

    Today/tomorrow intentionally return None so the established legacy view
    contract remains authoritative for those reads. This resolver performs date
    interpretation only; it never reads or mutates Calendar state.
    """

    text = _normalize(user_message)
    if not text:
        return None
    if _LEGACY_DAY_RE.search(text):
        return None

    today = reference_date or _calendar_reference_date()

    iso_range = re.search(
        r"\b(\d{4}-\d{2}-\d{2})\s+(?:to|through|thru|until|-)\s+"
        r"(\d{4}-\d{2}-\d{2})\b",
        text,
    )
    if iso_range:
        try:
            start = date.fromisoformat(iso_range.group(1))
            end = date.fromisoformat(iso_range.group(2))
        except ValueError:
            return None
        return _bounded_window(start, end)

    iso_single = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso_single:
        try:
            target = date.fromisoformat(iso_single.group(1))
        except ValueError:
            return None
        return _bounded_window(target, target)

    if re.search(r"\bthis\s+weekend\b", text):
        saturday = _monday_for(today) + timedelta(days=5)
        if saturday < today:
            saturday += timedelta(days=7)
        return _bounded_window(saturday, saturday + timedelta(days=1))

    if re.search(r"\bnext\s+weekend\b", text):
        saturday = _monday_for(today) + timedelta(days=12)
        return _bounded_window(saturday, saturday + timedelta(days=1))

    if re.search(r"\bthis\s+week\b", text):
        monday = _monday_for(today)
        return _bounded_window(monday, monday + timedelta(days=6))

    if re.search(r"\bnext\s+week\b", text):
        monday = _monday_for(today) + timedelta(days=7)
        return _bounded_window(monday, monday + timedelta(days=6))

    if re.search(r"\bthis\s+month\b", text):
        return _month_bounds(today, offset=0)

    if re.search(r"\bnext\s+month\b", text):
        return _month_bounds(today, offset=1)

    next_days = re.search(r"\bnext\s+(\d{1,2})\s+days?\b", text)
    if next_days:
        day_count = int(next_days.group(1))
        if day_count < 1 or day_count > MAX_CALENDAR_RANGE_DAYS:
            return None
        return _bounded_window(today, today + timedelta(days=day_count - 1))

    cross_month_range = re.search(
        rf"\b({_MONTH_PATTERN})\s+(\d{{1,2}}(?:st|nd|rd|th)?)"
        rf"(?:,?\s+(\d{{4}}))?\s+(?:to|through|thru|until|-)\s+"
        rf"({_MONTH_PATTERN})\s+(\d{{1,2}}(?:st|nd|rd|th)?)(?:,?\s+(\d{{4}}))?\b",
        text,
        flags=re.IGNORECASE,
    )
    if cross_month_range:
        start = _parse_month_day(
            cross_month_range.group(1),
            cross_month_range.group(2),
            cross_month_range.group(3),
            today,
        )
        end_year = cross_month_range.group(6) or cross_month_range.group(3)
        end = _parse_month_day(
            cross_month_range.group(4),
            cross_month_range.group(5),
            end_year,
            today,
        )
        if start and end:
            return _bounded_window(start, end)
        return None

    same_month_range = re.search(
        rf"\b({_MONTH_PATTERN})\s+(\d{{1,2}}(?:st|nd|rd|th)?)\s+"
        rf"(?:to|through|thru|until|-)\s+(\d{{1,2}}(?:st|nd|rd|th)?)(?:,?\s+(\d{{4}}))?\b",
        text,
        flags=re.IGNORECASE,
    )
    if same_month_range:
        year_token = same_month_range.group(4)
        start = _parse_month_day(
            same_month_range.group(1),
            same_month_range.group(2),
            year_token,
            today,
        )
        end = _parse_month_day(
            same_month_range.group(1),
            same_month_range.group(3),
            year_token,
            today,
        )
        if start and end:
            return _bounded_window(start, end)
        return None

    month_day = re.search(
        rf"\b({_MONTH_PATTERN})\s+(\d{{1,2}}(?:st|nd|rd|th)?)(?:,?\s+(\d{{4}}))?\b",
        text,
        flags=re.IGNORECASE,
    )
    if month_day:
        target = _parse_month_day(
            month_day.group(1),
            month_day.group(2),
            month_day.group(3),
            today,
        )
        return _bounded_window(target, target) if target else None

    weekday = re.search(
        rf"\b(?:(this|next)\s+)?({_WEEKDAY_PATTERN})\b",
        text,
        flags=re.IGNORECASE,
    )
    if weekday:
        qualifier = weekday.group(1).casefold() if weekday.group(1) else None
        weekday_index = _WEEKDAYS.get(weekday.group(2).casefold())
        if weekday_index is not None:
            target = _resolve_weekday(today, weekday_index, qualifier)
            return _bounded_window(target, target)

    return None


def looks_like_calendar_read_request(user_message: str) -> bool:
    text = user_message.strip()
    if not text or _WRITE_LEAD_RE.search(text):
        return False
    return bool(_READ_SIGNAL_RE.search(text))


def apply_calendar_range_read_ownership_floor(
    user_message: str,
    decision: Any,
    *,
    reference_date: date | None = None,
) -> Any:
    """Upgrade clear arbitrary-date Calendar reads to the canonical range shape.

    This only repairs ownership/arguments. It does not access Calendar state.
    Writes remain outside Phase 21F2 and are never rewritten into reads.
    """

    window = resolve_calendar_read_window(
        user_message,
        reference_date=reference_date,
    )
    if window is None or not looks_like_calendar_read_request(user_message):
        return decision

    proposed_action = str(getattr(decision, "proposedAction", "") or "")
    if proposed_action in {
        "add-calendar-event",
        "edit-last-event",
        "delete-calendar-event",
        "delete-last-event",
        "clear-calendar",
    }:
        return decision

    existing_calendar_read = (
        getattr(decision, "turnOwner", None) == "calendar"
        and getattr(decision, "disposition", None) == "tool"
        and getattr(decision, "proposedAction", None) == "read-calendar"
    )
    focus_relevant = (
        bool(getattr(decision, "focusRelevant", False))
        if existing_calendar_read
        else False
    )
    confidence = max(float(getattr(decision, "confidence", 0.0) or 0.0), 0.97)

    return decision.model_copy(
        update={
            "turnOwner": "calendar",
            "focusRelevant": focus_relevant,
            "disposition": "tool",
            "proposedCapability": "calendar",
            "proposedAction": "read-calendar",
            "proposedArguments": window.as_arguments(),
            "responsePlan": (
                "Read the exact canonical Calendar date window, then summarize only the verified schedule result."
            ),
            "confidence": confidence,
            "reason": (
                "Deterministic Calendar range-read ownership floor resolved explicit date language to absolute startDate/endDate keys; Calendar state access remains authoritative downstream."
            ),
        }
    )
