from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest

from app import qmeet_agent_shadow as shadow
from app.calendar_read_date_interpreter import (
    apply_calendar_absolute_edit_delete_ownership_floor,
)
from app.main import app

ROOT = Path(__file__).resolve().parents[2]


class AgentCalendarAbsoluteEditDeletePhase21F4Tests(unittest.TestCase):
    def _decision(self, action: str, arguments: dict) -> shadow.AgentShadowDecision:
        return shadow.AgentShadowDecision(
            turnOwner="calendar",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="calendar",
            proposedAction=action,
            proposedArguments=arguments,
            responsePlan="Use Calendar.",
            confidence=0.95,
            reason="Calendar mutation.",
        )

    def test_move_resolves_source_and_destination_to_absolute_dates(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "move my 3 PM meeting next Friday to Saturday",
            self._decision(
                "edit-last-event",
                {
                    "targetDay": "tomorrow",
                    "query": "meeting",
                    "currentTime": "3 PM",
                    "changeField": "day",
                    "changeValue": "tomorrow",
                },
            ),
            reference_date=date(2026, 8, 19),
        )
        self.assertEqual(result.proposedAction, "edit-last-event")
        self.assertEqual(result.proposedArguments["targetDate"], "2026-08-28")
        self.assertEqual(result.proposedArguments["currentTime"], "3 PM")
        self.assertEqual(result.proposedArguments["changeField"], "date")
        self.assertEqual(result.proposedArguments["changeValue"], "2026-08-29")

    def test_delete_resolves_farther_source_date_without_event_identity(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "delete my 2 PM meeting next Friday",
            self._decision(
                "delete-calendar-event",
                {"day": "tomorrow", "title": "meeting", "time": "2 PM"},
            ),
            reference_date=date(2026, 8, 19),
        )
        self.assertEqual(result.proposedAction, "delete-calendar-event")
        self.assertEqual(
            result.proposedArguments,
            {"date": "2026-08-28", "title": "meeting", "time": "2 PM"},
        )
        self.assertNotIn("eventId", result.proposedArguments)

    def test_range_mutation_fails_closed_instead_of_choosing_one_source_date(self) -> None:
        original = self._decision(
            "delete-calendar-event",
            {"day": "tomorrow", "title": "meeting", "time": None},
        )
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "delete my meeting next week",
            original,
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(result.turnOwner, "calendar")
        self.assertEqual(result.proposedAction, "delete-calendar-event")
        self.assertEqual(
            result.proposedArguments,
            {
                "startDate": "2026-08-24",
                "endDate": "2026-08-30",
            },
        )
        self.assertNotIn("day", result.proposedArguments)
        self.assertNotIn("date", result.proposedArguments)
        self.assertIn("multi-day source range", result.reason)

    def test_absolute_update_route_is_registered(self) -> None:
        paths = app.openapi().get("paths", {})
        self.assertIn("/api/calendar/events/{event_id}/absolute", paths)
        self.assertIn("patch", paths["/api/calendar/events/{event_id}/absolute"])

    def test_frontend_promotion_accepts_absolute_source_and_destination(self) -> None:
        source = (ROOT / "src/app/lib/agentToolPromotion.ts").read_text(encoding="utf-8")
        self.assertIn("targetDate", source)
        self.assertIn("changeField === 'date'", source)
        self.assertIn("isCanonicalCalendarDateKey(changeValue)", source)
        self.assertIn("day: CalendarCommandDay", source)

    def test_controller_reads_exact_source_date_and_caches_identity(self) -> None:
        source = (ROOT / "src/app/hooks/useCalendarController.ts").read_text(encoding="utf-8")
        self.assertIn("fetchCalendarEventsRange", source)
        self.assertIn("startDate: criteria.day", source)
        self.assertIn("endDate: criteria.day", source)
        self.assertIn("setGoogleCalendarEvents", source)
        self.assertIn("updateCalendarEventOnAbsoluteDate", source)

    def test_absolute_edit_does_not_reapply_iso_date_through_legacy_resolver(self) -> None:
        source = (ROOT / "src/app/App.tsx").read_text(encoding="utf-8")
        start = source.index(
            "const resolution = resolveCalendarEventReference(sourceEvents, {"
        )
        end = source.index("});", start) + 3
        block = source[start:end]

        self.assertIn("promotedCalendarEditTargetCriteria.day === 'today'", block)
        self.assertIn("promotedCalendarEditTargetCriteria.day === 'tomorrow'", block)
        self.assertIn("? promotedCalendarEditTargetCriteria.day", block)
        self.assertIn(": undefined", block)
        self.assertIn("query: promotedCalendarEditTargetCriteria.query", block)
        self.assertIn("time: promotedCalendarEditTargetCriteria.time", block)

    def test_absolute_delete_does_not_reapply_iso_date_through_legacy_resolver(self) -> None:
        source = (ROOT / "src/app/App.tsx").read_text(encoding="utf-8")
        start = source.index(
            "? resolveCalendarEventReference(targetedDeleteSourceEvents, {"
        )
        end = source.index("})", start) + 2
        block = source[start:end]

        self.assertIn("commandMatch.calendarDelete?.day === 'today'", block)
        self.assertIn("commandMatch.calendarDelete?.day === 'tomorrow'", block)
        self.assertIn("? commandMatch.calendarDelete.day", block)
        self.assertIn("? undefined", block)
        self.assertIn(": calendarView", block)

    def test_reference_resolver_allows_pre_scoped_absolute_date_candidates(self) -> None:
        source = (
            ROOT / "src/app/lib/calendarEventResolver.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("day?: CalendarView", source)
        self.assertIn(
            "(!criteria.day || isEventForCalendarView(event, criteria.day))",
            source,
        )
        self.assertIn(
            "eventMatchesRequestedTime(event, criteria.time)",
            source,
        )

    def test_app_never_sets_today_tomorrow_panel_to_iso_date(self) -> None:
        source = (ROOT / "src/app/App.tsx").read_text(encoding="utf-8")
        self.assertIn("promotedCalendarEditTargetCriteria?.day === 'today'", source)
        self.assertIn("promotedCalendarEditTargetCriteria?.day === 'tomorrow'", source)
        self.assertIn("commandMatch.calendarDelete?.day === 'today'", source)
        self.assertIn("commandMatch.calendarDelete?.day === 'tomorrow'", source)

    def test_confirmed_edit_and_delete_still_lock_canonical_event_ids(self) -> None:
        source = (ROOT / "src/app/App.tsx").read_text(encoding="utf-8")
        self.assertIn("pendingCalendarEditTargetIdRef.current = targetEditEvent.id", source)
        self.assertIn("pendingCalendarDeleteTargetIdRef.current", source)
        self.assertIn("resolvedCalendarEditTargetId", source)
        self.assertIn("resolvedCalendarDeleteTargetId", source)


if __name__ == "__main__":
    unittest.main()
