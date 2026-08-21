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

_CREATE_LEAD_RE = re.compile(
    r"^\s*(?:(?:please\s+)?|(?:can|could|would|will)\s+you\s+(?:please\s+)?|"
    r"i\s+(?:want|need)\s+you\s+to\s+|i(?:'d|\s+would)\s+like\s+you\s+to\s+)"
    r"(?:add|create|schedule|book)\b",
    re.IGNORECASE,
)
_CREATE_TIME_RE = re.compile(
    r"\b(?:at|by)\s+((?:\d{1,2})(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?|am|pm)?|noon|midnight)\b",
    re.IGNORECASE,
)
_BROAD_CREATE_TITLE_RE = re.compile(
    r"^(?:(?:my|our|the)\s+)?(?:day|schedule|agenda|plans?)$",
    re.IGNORECASE,
)


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


def looks_like_calendar_create_request(user_message: str) -> bool:
    return bool(_CREATE_LEAD_RE.search(user_message or ""))


def _validated_create_time(value: Any) -> str | None | object:
    if value is None:
        return None
    if not isinstance(value, str):
        return _INVALID_CREATE_VALUE
    cleaned = re.sub(r"\s+", " ", value.strip())
    if not cleaned or len(cleaned) > 32 or re.search(r"[\x00-\x1f\x7f]", cleaned):
        return _INVALID_CREATE_VALUE
    normalized = cleaned.casefold().replace(".", "")
    if normalized in {"noon", "midnight"}:
        return cleaned
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", normalized)
    if not match:
        return _INVALID_CREATE_VALUE
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    meridiem = match.group(3)
    if minute > 59:
        return _INVALID_CREATE_VALUE
    if meridiem and not 1 <= hour <= 12:
        return _INVALID_CREATE_VALUE
    if not meridiem and not 0 <= hour <= 23:
        return _INVALID_CREATE_VALUE
    return cleaned


def _validated_create_title(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"\s+", " ", value.strip()).strip(" ,.;:")
    if (
        not cleaned
        or len(cleaned) > 240
        or re.search(r"[\x00-\x1f\x7f]", cleaned)
        or _BROAD_CREATE_TITLE_RE.fullmatch(cleaned)
    ):
        return None
    return cleaned


def _explicit_create_title(user_message: str) -> str | None:
    """Return a Calendar title only when the user explicitly names it.

    Explicit ``called``, ``named``, and ``titled`` clauses are user-grounded
    execution data and therefore outrank a model-proposed title. Ordinary
    Calendar creates still preserve the model's semantic title when the user
    did not provide one of these explicit naming markers.
    """
    text = re.sub(r"\s+", " ", user_message.strip())
    match = re.search(
        r"\b(?:called|named|titled)\s+(.+?)\s*$",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return None

    title = match.group(1).strip()
    title = re.sub(r"^[\"'`]+|[\"'`]+$", "", title).strip()
    return _validated_create_title(title)


def _fallback_create_title(user_message: str) -> str | None:
    """Conservatively extract one title before the explicit date phrase.

    The model remains the preferred semantic title source. This fallback exists
    only so an unmistakable one-event create does not fall back to conversation
    when the old today/tomorrow prompt shape is returned for a farther date.
    """

    text = re.sub(r"\s+", " ", user_message.strip())
    text = _CREATE_LEAD_RE.sub("", text, count=1).strip()
    text = re.sub(r"^(?:a|an|the)\s+", "", text, flags=re.IGNORECASE)

    date_patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        rf"\b(?:this|next)\s+{_WEEKDAY_PATTERN}\b",
        rf"\b{_MONTH_PATTERN}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?\b",
        rf"\b{_WEEKDAY_PATTERN}\b",
    ]
    date_match = None
    for pattern in date_patterns:
        candidate = re.search(pattern, text, flags=re.IGNORECASE)
        if candidate and (date_match is None or candidate.start() < date_match.start()):
            date_match = candidate
    if not date_match:
        return None

    title = text[: date_match.start()].strip(" ,.;:")
    title = re.sub(
        r"^(?:an?\s+)?(?:calendar\s+)?(?:event|appointment|reminder)\s+(?:called|named|titled|for|about)\s+",
        "",
        title,
        flags=re.IGNORECASE,
    )
    title = re.sub(r"^(?:a|an|the)\s+", "", title, flags=re.IGNORECASE)
    return _validated_create_title(title)


_INVALID_CREATE_VALUE = object()


def apply_calendar_absolute_create_ownership_floor(
    user_message: str,
    decision: Any,
    *,
    reference_date: date | None = None,
) -> Any:
    """Canonicalize one farther-date Calendar create to an absolute date.

    This does not execute Calendar state. The returned title/time/date proposal
    must still pass the frontend typed validator, the existing confirmation
    gate, confirmation-time command round-trip, and the canonical backend write.
    """

    if not looks_like_calendar_create_request(user_message):
        return decision

    window = resolve_calendar_read_window(
        user_message,
        reference_date=reference_date,
    )
    if window is None:
        return decision
    if window.day_count != 1:
        # A one-event Calendar create cannot safely choose one day from a
        # recognized multi-day expression such as "next week". Do not return
        # the model proposal unchanged here: it may contain a stale or invented
        # legacy today/tomorrow value from recent conversation. Keep Calendar
        # create ownership, but deliberately emit a non-executable range shape.
        # The existing frontend Calendar-create candidate guard will reject it
        # before legacy interpretation or confirmation can manufacture one day.
        return decision.model_copy(
            update={
                "turnOwner": "calendar",
                "focusRelevant": bool(getattr(decision, "focusRelevant", False)),
                "disposition": "tool",
                "proposedCapability": "calendar",
                "proposedAction": "add-calendar-event",
                "proposedArguments": {
                    "startDate": window.start_date.isoformat(),
                    "endDate": window.end_date.isoformat(),
                },
                "responsePlan": (
                    "Ask the user to choose one specific date before creating a single Calendar event."
                ),
                "confidence": max(
                    float(getattr(decision, "confidence", 0.0) or 0.0),
                    0.99,
                ),
                "reason": (
                    "Deterministic Calendar create range guard rejected a multi-day date expression for a one-event mutation. No single date may be inferred from the range."
                ),
            }
        )

    existing_arguments = getattr(decision, "proposedArguments", {}) or {}
    if not isinstance(existing_arguments, dict):
        existing_arguments = {}

    title = _explicit_create_title(user_message)
    if title is None:
        title = _validated_create_title(existing_arguments.get("title"))
    if title is None:
        title = _fallback_create_title(user_message)
    if title is None:
        return decision

    time_value = _validated_create_time(existing_arguments.get("time"))
    time_match = _CREATE_TIME_RE.search(user_message)
    if time_match and (time_value is None or time_value is _INVALID_CREATE_VALUE):
        time_value = _validated_create_time(time_match.group(1))
    elif time_value is _INVALID_CREATE_VALUE:
        time_value = None
    if time_value is _INVALID_CREATE_VALUE:
        return decision

    return decision.model_copy(
        update={
            "turnOwner": "calendar",
            "focusRelevant": bool(getattr(decision, "focusRelevant", False)),
            "disposition": "tool",
            "proposedCapability": "calendar",
            "proposedAction": "add-calendar-event",
            "proposedArguments": {
                "date": window.start_date.isoformat(),
                "title": title,
                "time": time_value,
            },
            "responsePlan": (
                "Preview one Calendar event on the exact canonical date, require confirmation, then continue only from the verified write receipt."
            ),
            "confidence": max(float(getattr(decision, "confidence", 0.0) or 0.0), 0.97),
            "reason": (
                "Deterministic Calendar create date floor resolved one explicit farther-date expression to an absolute date; execution remains gated by typed frontend validation and confirmation."
            ),
        }
    )



_EDIT_LEAD_RE = re.compile(
    r"^(?:please\s+)?(?:move|reschedule|change|edit|update|rename|retitle)\b",
    re.IGNORECASE,
)
_RENAME_LEAD_RE = re.compile(
    r"^(?:please\s+)?(?:rename|retitle)\b",
    re.IGNORECASE,
)
_EXPLICIT_TITLE_EDIT_RE = re.compile(
    r"\b(?:rename|retitle|change\s+(?:the\s+)?title(?:\s+of)?)\b",
    re.IGNORECASE,
)
_DELETE_LEAD_RE = re.compile(r"^(?:please\s+)?(?:delete|remove|cancel|erase)\b", re.IGNORECASE)
_LOOKUP_TIME_RE = re.compile(r"\b(\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)|noon|midnight)\b", re.IGNORECASE)


def _validated_lookup_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = re.sub(r"\s+", " ", value.strip()).strip(" ,.;:")
    return cleaned if cleaned and len(cleaned) <= 240 else None


def _fallback_event_query(user_message: str) -> str | None:
    text = re.sub(r"\s+", " ", user_message.strip())
    match = re.search(r"\b(?:meeting|appointment|event)\b", text, re.IGNORECASE)
    return match.group(0).casefold() if match else None


def _poison_multi_day_calendar_mutation(
    decision: Any,
    *,
    action: str,
    source_window: CalendarReadWindow,
) -> Any:
    """Keep a recognized multi-day mutation from collapsing to one model-picked day.

    The frontend already treats a claimed Calendar edit/delete whose typed
    arguments fail deterministic validation as terminal and non-mutating. Keep
    the owning action, but return a deliberately non-executable range shape so
    legacy/model fallback cannot silently choose one day from the range.
    """

    return decision.model_copy(update={
        "turnOwner": "calendar",
        "disposition": "tool",
        "proposedCapability": "calendar",
        "proposedAction": action,
        "proposedArguments": {
            "startDate": source_window.start_date.isoformat(),
            "endDate": source_window.end_date.isoformat(),
        },
        "responsePlan": "Refuse to choose one Calendar event date from a multi-day mutation request; ask the user for one specific day.",
        "confidence": max(float(getattr(decision, "confidence", 0.0) or 0.0), 0.99),
        "reason": "Deterministic Calendar mutation safety floor recognized a multi-day source range, so one event cannot be safely targeted without a specific day.",
    })


def _calendar_source_date_selector(source_clause: str) -> str | None:
    """Return the explicit source-date phrase that owns Calendar targeting.

    The query/title criterion must not duplicate a date selector that is already
    represented by targetDate/targetDay. Prefer the same specific date forms the
    Calendar window resolver recognizes before falling back to a bare weekday.
    """

    patterns = [
        r"\b\d{4}-\d{2}-\d{2}\b",
        rf"\b{_MONTH_PATTERN}\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+\d{{4}})?\b",
        rf"\b(?:this|next)\s+{_WEEKDAY_PATTERN}\b",
        r"\b(?:today|tomorrow)\b",
        rf"\b{_WEEKDAY_PATTERN}\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, source_clause, flags=re.IGNORECASE)
        if match:
            return match.group(0)
    return None


def _strip_calendar_query_selector(
    proposed_query: str,
    selector: str,
) -> str:
    pattern = re.escape(selector)
    pattern = pattern.replace(r"\ ", r"\s+")
    cleaned = re.sub(
        pattern,
        " ",
        proposed_query,
        count=1,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b(?:at|from|on|for)\b\s*$",
        " ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s+", " ", cleaned).strip(" ,.;:")


def _calendar_edit_query(
    source_clause: str,
    user_message: str,
    existing_arguments: dict[str, Any],
) -> str | None:
    """Return title/query criteria with temporal selectors kept separate.

    Agent proposals may redundantly include source selectors in the free-text
    query, for example query="4 PM Project Review August 29" while currentTime
    and targetDate already carry those selectors. Strip only selectors that are
    explicitly present in the user's source clause, preserving the event-title
    words used for authoritative Calendar identity resolution.
    """

    proposed_query = (
        _validated_lookup_text(existing_arguments.get("query"))
        or _validated_lookup_text(existing_arguments.get("title"))
    )
    if proposed_query:
        cleaned_query = proposed_query
        explicit_time = _LOOKUP_TIME_RE.search(source_clause)
        if explicit_time:
            cleaned_query = _strip_calendar_query_selector(
                cleaned_query,
                explicit_time.group(0),
            )

        source_date_selector = _calendar_source_date_selector(source_clause)
        if source_date_selector:
            cleaned_query = _strip_calendar_query_selector(
                cleaned_query,
                source_date_selector,
            )

        validated_cleaned_query = _validated_lookup_text(cleaned_query)
        if validated_cleaned_query:
            return validated_cleaned_query
        return _fallback_event_query(user_message)

    return _fallback_event_query(user_message)


def _calendar_edit_current_time(
    source_clause: str,
    existing_arguments: dict[str, Any],
) -> str | None:
    current_time = _validated_create_time(existing_arguments.get("currentTime"))
    explicit_time = _LOOKUP_TIME_RE.search(source_clause)
    if explicit_time:
        current_time = _validated_create_time(explicit_time.group(1))
    if current_time is _INVALID_CREATE_VALUE:
        return None
    return current_time


def _validated_title_change_value(value: str) -> str | None:
    cleaned = re.sub(
        r"^(?:called|named|titled)\s+",
        "",
        value.strip(),
        flags=re.IGNORECASE,
    )
    return _validated_lookup_text(cleaned)


def apply_calendar_absolute_edit_delete_ownership_floor(
    user_message: str,
    decision: Any,
    *,
    reference_date: date | None = None,
) -> Any:
    """Resolve farther-date targeted edit/delete semantics without event identity.

    Supported arbitrary-date edits:
    - day/date moves, e.g. "move my meeting next Friday to Saturday"
    - time changes, e.g. "move my meeting next Saturday from 3 PM to 4 PM"
    - title changes, e.g. "rename my meeting next Saturday to Project Review"

    This floor never resolves canonical event identity. It emits exact source-date
    lookup criteria plus one requested change; authoritative Calendar state still
    resolves zero/one/multiple events and locks one event id across confirmation.
    """

    text = re.sub(r"\s+", " ", user_message.strip())
    is_delete = bool(_DELETE_LEAD_RE.search(text))
    is_edit = bool(_EDIT_LEAD_RE.search(text))
    if not (is_delete or is_edit):
        return decision

    existing_arguments = getattr(decision, "proposedArguments", {}) or {}
    if not isinstance(existing_arguments, dict):
        existing_arguments = {}

    if is_edit:
        split = re.split(r"\s+to\s+", text, maxsplit=1, flags=re.IGNORECASE)
        if len(split) != 2:
            return decision

        source_clause, destination_clause = split[0], split[1].strip()

        # Calendar reads intentionally leave today/tomorrow to the legacy view
        # contract, so resolve_calendar_read_window() returns None for them.
        # Mutations need a slightly different bridge: preserve a legacy relative
        # source selector as targetDay while still resolving an arbitrary
        # destination to a canonical absolute date.
        legacy_source_match = _LEGACY_DAY_RE.search(source_clause)
        if legacy_source_match:
            legacy_source_day = legacy_source_match.group(0).casefold()
            source_date = reference_date or _calendar_reference_date()
            if legacy_source_day == "tomorrow":
                source_date += timedelta(days=1)
            source_window = _bounded_window(source_date, source_date)
            source_target_arguments: dict[str, str] = {
                "targetDay": legacy_source_day,
            }
        else:
            source_window = resolve_calendar_read_window(
                source_clause,
                reference_date=reference_date,
            )
            if source_window is None:
                return decision
            source_target_arguments = {
                "targetDate": source_window.start_date.isoformat(),
            }

        if source_window is None:
            return decision
        if source_window.day_count != 1:
            return _poison_multi_day_calendar_mutation(
                decision,
                action="edit-last-event",
                source_window=source_window,
            )

        query = _calendar_edit_query(source_clause, user_message, existing_arguments)
        if not query:
            return decision
        current_time = _calendar_edit_current_time(
            source_clause,
            existing_arguments,
        )

        # Explicit rename/retitle/title-change wording owns the suffix as a title,
        # even when the requested title happens to contain a weekday or time token.
        if _RENAME_LEAD_RE.search(text) or _EXPLICIT_TITLE_EDIT_RE.search(text):
            new_title = _validated_title_change_value(destination_clause)
            if not new_title:
                return decision
            return decision.model_copy(update={
                "turnOwner": "calendar",
                "disposition": "tool",
                "proposedCapability": "calendar",
                "proposedAction": "edit-last-event",
                "proposedArguments": {
                    **source_target_arguments,
                    "query": query,
                    "currentTime": current_time,
                    "changeField": "title",
                    "changeValue": new_title,
                },
                "responsePlan": "Resolve one real Calendar event on the exact source date, preview the title change, require confirmation, then update only the locked event identity.",
                "confidence": max(float(getattr(decision, "confidence", 0.0) or 0.0), 0.98),
                "reason": "Deterministic Calendar absolute-date edit floor resolved one source date and one requested title change without resolving event identity.",
            })

        destination_window = resolve_calendar_read_window(
            destination_clause,
            reference_date=source_window.start_date,
        )
        if destination_window is not None:
            if destination_window.day_count != 1:
                return decision
            if destination_window.start_date == source_window.start_date:
                return decision
            return decision.model_copy(update={
                "turnOwner": "calendar",
                "disposition": "tool",
                "proposedCapability": "calendar",
                "proposedAction": "edit-last-event",
                "proposedArguments": {
                    **source_target_arguments,
                    "query": query,
                    "currentTime": current_time,
                    "changeField": "date",
                    "changeValue": destination_window.start_date.isoformat(),
                },
                "responsePlan": "Resolve one real Calendar event on the source date, preview the absolute-date move, require confirmation, then update only the locked event identity.",
                "confidence": max(float(getattr(decision, "confidence", 0.0) or 0.0), 0.98),
                "reason": "Deterministic Calendar absolute-date edit floor resolved one source date and one destination date without resolving event identity.",
            })

        new_time_match = _LOOKUP_TIME_RE.search(destination_clause)
        if new_time_match:
            new_time = _validated_create_time(new_time_match.group(1))
            if new_time is _INVALID_CREATE_VALUE or new_time is None:
                return decision
            return decision.model_copy(update={
                "turnOwner": "calendar",
                "disposition": "tool",
                "proposedCapability": "calendar",
                "proposedAction": "edit-last-event",
                "proposedArguments": {
                    **source_target_arguments,
                    "query": query,
                    "currentTime": current_time,
                    "changeField": "time",
                    "changeValue": new_time,
                },
                "responsePlan": "Resolve one real Calendar event on the exact source date, preview the time change, require confirmation, then update only the locked event identity.",
                "confidence": max(float(getattr(decision, "confidence", 0.0) or 0.0), 0.98),
                "reason": "Deterministic Calendar absolute-date edit floor resolved one source date and one requested time change without resolving event identity.",
            })

        return decision

    source_window = resolve_calendar_read_window(
        text,
        reference_date=reference_date,
    )
    if source_window is None:
        return decision
    if source_window.day_count != 1:
        return _poison_multi_day_calendar_mutation(
            decision,
            action="delete-calendar-event",
            source_window=source_window,
        )

    title = (
        _validated_lookup_text(existing_arguments.get("title"))
        or _validated_lookup_text(existing_arguments.get("query"))
        or _fallback_event_query(user_message)
    )
    current_time = _validated_create_time(existing_arguments.get("time"))
    explicit_time = _LOOKUP_TIME_RE.search(text)
    if explicit_time:
        current_time = _validated_create_time(explicit_time.group(1))
    if current_time is _INVALID_CREATE_VALUE:
        current_time = None
    if not title and not current_time:
        return decision

    return decision.model_copy(update={
        "turnOwner": "calendar",
        "disposition": "tool",
        "proposedCapability": "calendar",
        "proposedAction": "delete-calendar-event",
        "proposedArguments": {
            "date": source_window.start_date.isoformat(),
            "title": title,
            "time": current_time,
        },
        "responsePlan": "Resolve one real Calendar event on the exact date, require confirmation, then delete only the locked event identity.",
        "confidence": max(float(getattr(decision, "confidence", 0.0) or 0.0), 0.98),
        "reason": "Deterministic Calendar absolute-date delete floor resolved one source date while leaving canonical event identity to authoritative Calendar state.",
    })

