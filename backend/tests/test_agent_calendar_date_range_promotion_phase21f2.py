from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest

from app.calendar_read_date_interpreter import (
    apply_calendar_range_read_ownership_floor,
    looks_like_calendar_read_request,
    resolve_calendar_read_window,
)
from app.qmeet_agent_shadow import AgentShadowDecision


ROOT = Path(__file__).resolve().parents[2]
REFERENCE_DATE = date(2026, 8, 19)


class AgentCalendarDateRangePromotionPhase21F2Tests(unittest.TestCase):
    def assert_window(
        self,
        message: str,
        start_date: str,
        end_date: str,
    ) -> None:
        window = resolve_calendar_read_window(
            message,
            reference_date=REFERENCE_DATE,
        )
        self.assertIsNotNone(window)
        assert window is not None
        self.assertEqual(window.start_date.isoformat(), start_date)
        self.assertEqual(window.end_date.isoformat(), end_date)

    def test_relative_weekday_and_weekend_language_resolves_deterministically(self) -> None:
        cases = (
            (
                "what's on my calendar this Friday?",
                "2026-08-21",
                "2026-08-21",
            ),
            (
                "what's on my calendar next Friday?",
                "2026-08-28",
                "2026-08-28",
            ),
            (
                "what's on my calendar this weekend?",
                "2026-08-22",
                "2026-08-23",
            ),
            (
                "what's on my calendar next weekend?",
                "2026-08-29",
                "2026-08-30",
            ),
            (
                "what's on my calendar next week?",
                "2026-08-24",
                "2026-08-30",
            ),
        )
        for message, start_date, end_date in cases:
            with self.subTest(message=message):
                self.assert_window(message, start_date, end_date)

    def test_explicit_month_dates_and_ranges_resolve_to_absolute_keys(self) -> None:
        cases = (
            (
                "show my calendar for August 27",
                "2026-08-27",
                "2026-08-27",
            ),
            (
                "show my calendar August 27 to 29",
                "2026-08-27",
                "2026-08-29",
            ),
            (
                "show my calendar August 27 through September 2",
                "2026-08-27",
                "2026-09-02",
            ),
            (
                "show my calendar 2026-08-27 to 2026-08-29",
                "2026-08-27",
                "2026-08-29",
            ),
        )
        for message, start_date, end_date in cases:
            with self.subTest(message=message):
                self.assert_window(message, start_date, end_date)

    def test_explicit_month_date_outranks_incidental_weekday_label(self) -> None:
        self.assert_window(
            "show my calendar Friday August 28",
            "2026-08-28",
            "2026-08-28",
        )

    def test_today_and_tomorrow_remain_on_legacy_calendar_view_contract(self) -> None:
        for message in (
            "what's on my calendar today?",
            "what's on my calendar tomorrow?",
        ):
            with self.subTest(message=message):
                self.assertIsNone(
                    resolve_calendar_read_window(
                        message,
                        reference_date=REFERENCE_DATE,
                    )
                )

    def test_calendar_write_language_is_not_reclassified_as_range_read(self) -> None:
        message = "schedule a meeting next Friday"
        self.assertIsNotNone(
            resolve_calendar_read_window(
                message,
                reference_date=REFERENCE_DATE,
            )
        )
        self.assertFalse(looks_like_calendar_read_request(message))

        decision = AgentShadowDecision(
            turnOwner="calendar",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="calendar",
            proposedAction="add-calendar-event",
            proposedArguments={
                "day": "tomorrow",
                "title": "Meeting",
                "time": None,
            },
            responsePlan="Create the event through Calendar.",
            confidence=0.95,
            reason="Calendar write.",
        )
        repaired = apply_calendar_range_read_ownership_floor(
            message,
            decision,
            reference_date=REFERENCE_DATE,
        )
        self.assertIs(repaired, decision)

    def test_range_floor_repairs_calendar_read_arguments_without_executing_state(self) -> None:
        decision = AgentShadowDecision(
            turnOwner="calendar",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="calendar",
            proposedAction="read-calendar",
            proposedArguments={"view": "all"},
            responsePlan="Read Calendar.",
            confidence=0.95,
            reason="Calendar read.",
        )
        repaired = apply_calendar_range_read_ownership_floor(
            "what's on my calendar next Friday?",
            decision,
            reference_date=REFERENCE_DATE,
        )

        self.assertEqual(repaired.turnOwner, "calendar")
        self.assertEqual(repaired.disposition, "tool")
        self.assertEqual(repaired.proposedCapability, "calendar")
        self.assertEqual(repaired.proposedAction, "read-calendar")
        self.assertEqual(
            repaired.proposedArguments,
            {
                "startDate": "2026-08-28",
                "endDate": "2026-08-28",
            },
        )
        self.assertGreaterEqual(repaired.confidence, 0.97)

    def test_unrelated_general_question_is_not_promoted_by_date_language_alone(self) -> None:
        decision = AgentShadowDecision(
            turnOwner="general_chat",
            focusRelevant=False,
            disposition="conversation",
            proposedCapability="none",
            proposedAction="conversation.respond",
            proposedArguments={},
            responsePlan="Answer normally.",
            confidence=0.95,
            reason="General question.",
        )
        repaired = apply_calendar_range_read_ownership_floor(
            "what day of the week is next Friday?",
            decision,
            reference_date=REFERENCE_DATE,
        )
        self.assertIs(repaired, decision)

    def test_frontend_promotion_accepts_legacy_or_strict_range_shape(self) -> None:
        promotion = (
            ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts"
        ).read_text(encoding="utf-8")
        range_helper = (
            ROOT / "src" / "app" / "lib" / "calendarReadRange.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("readValidatedCalendarReadView", promotion)
        self.assertIn("readValidatedCalendarReadRange", promotion)
        self.assertIn("view: 'range'", promotion)
        self.assertIn("encodeCalendarReadRangePayload(range)", promotion)
        self.assertIn("keys[0] !== 'view'", promotion)
        self.assertIn("MAX_CALENDAR_READ_RANGE_DAYS = 31", range_helper)
        self.assertIn("keys[0] !== 'endDate'", range_helper)
        self.assertIn("keys[1] !== 'startDate'", range_helper)

    def test_range_handler_uses_f1_endpoint_and_verified_continuation(self) -> None:
        handler = (
            ROOT / "src" / "app" / "commandHandlers" / "calendar.ts"
        ).read_text(encoding="utf-8")
        range_helper = (
            ROOT / "src" / "app" / "lib" / "calendarReadRange.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("decodeCalendarReadRangePayload(commandMatch.payload)", handler)
        self.assertIn("fetchCalendarEventsRange(calendarRange)", handler)
        self.assertIn("formatCalendarRangeReadout", handler)
        self.assertIn("continuationContext: verifiedCalendarReadout", handler)
        self.assertIn("/api/calendar/events/range", range_helper)
        self.assertNotIn("setActivePanel('calendar')", handler[
            handler.index("if (calendarRange)"):
            handler.index("const requestedCalendarView", handler.index("if (calendarRange)"))
        ])

    def test_agent_router_applies_range_floor_after_existing_device_ui_floor(self) -> None:
        router = (
            ROOT / "backend" / "app" / "routers" / "agent_shadow.py"
        ).read_text(encoding="utf-8")
        device_index = router.index("apply_device_ui_ownership_floor(")
        range_index = router.index("apply_calendar_range_read_ownership_floor(")
        self.assertLess(device_index, range_index)
        self.assertIn("response.model_copy(update={\"decision\": repaired_decision})", router)

    def test_f1_absolute_range_endpoint_remains_the_execution_boundary(self) -> None:
        router = (
            ROOT / "backend" / "app" / "routers" / "calendar.py"
        ).read_text(encoding="utf-8")
        service = (
            ROOT / "backend" / "app" / "calendar_range_service.py"
        ).read_text(encoding="utf-8")

        self.assertIn('@router.get("/events/range")', router)
        self.assertIn('alias="startDate"', router)
        self.assertIn('alias="endDate"', router)
        self.assertIn("list_calendar_events_range", service)
        self.assertIn("MAX_CALENDAR_RANGE_DAYS = 31", service)


if __name__ == "__main__":
    unittest.main()
