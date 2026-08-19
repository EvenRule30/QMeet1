from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest

from app import qmeet_agent_shadow as shadow
from app.calendar_read_date_interpreter import (
    apply_calendar_absolute_edit_delete_ownership_floor,
)

ROOT = Path(__file__).resolve().parents[2]


class AgentCalendarAbsoluteEditCoveragePhase21F5Tests(unittest.TestCase):
    def _decision(
        self,
        arguments: dict,
        *,
        action: str = "edit-last-event",
    ) -> shadow.AgentShadowDecision:
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

    def test_farther_date_time_edit_resolves_source_and_new_time(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "move my meeting next Saturday from 3 PM to 4 PM",
            self._decision(
                {
                    "targetDay": "tomorrow",
                    "query": "meeting",
                    "currentTime": "2 PM",
                    "changeField": "time",
                    "changeValue": "5 PM",
                }
            ),
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(result.proposedAction, "edit-last-event")
        self.assertEqual(
            result.proposedArguments,
            {
                "targetDate": "2026-08-29",
                "query": "meeting",
                "currentTime": "3 PM",
                "changeField": "time",
                "changeValue": "4 PM",
            },
        )
        self.assertNotIn("eventId", result.proposedArguments)

    def test_farther_date_time_edit_can_leave_source_time_unspecified(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "move my meeting next Saturday to 4 PM",
            self._decision(
                {
                    "targetDay": "tomorrow",
                    "query": "meeting",
                    "currentTime": None,
                    "changeField": "time",
                    "changeValue": "4 PM",
                }
            ),
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(result.proposedArguments["targetDate"], "2026-08-29")
        self.assertIsNone(result.proposedArguments["currentTime"])
        self.assertEqual(result.proposedArguments["changeField"], "time")
        self.assertEqual(result.proposedArguments["changeValue"], "4 PM")

    def test_farther_date_rename_resolves_title_without_event_identity(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "rename my meeting next Saturday to Project Review",
            self._decision(
                {
                    "targetDay": "tomorrow",
                    "query": "meeting",
                    "currentTime": None,
                    "changeField": "title",
                    "changeValue": "Wrong Model Title",
                }
            ),
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(
            result.proposedArguments,
            {
                "targetDate": "2026-08-29",
                "query": "meeting",
                "currentTime": None,
                "changeField": "title",
                "changeValue": "Project Review",
            },
        )
        self.assertNotIn("eventId", result.proposedArguments)

    def test_rename_strips_duplicate_source_time_from_model_query(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "rename my 4 PM meeting August 29 to Project Review",
            self._decision(
                {
                    "targetDay": "tomorrow",
                    "query": "4 PM meeting",
                    "currentTime": "4 PM",
                    "changeField": "title",
                    "changeValue": "Project Review",
                }
            ),
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(result.proposedArguments["targetDate"], "2026-08-29")
        self.assertEqual(result.proposedArguments["query"], "meeting")
        self.assertEqual(result.proposedArguments["currentTime"], "4 PM")
        self.assertEqual(result.proposedArguments["changeField"], "title")
        self.assertEqual(result.proposedArguments["changeValue"], "Project Review")

    def test_custom_title_words_survive_time_selector_cleanup(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "rename my 4 PM planning meeting August 29 to Project Review",
            self._decision(
                {
                    "targetDay": "tomorrow",
                    "query": "4 PM planning meeting",
                    "currentTime": "4 PM",
                    "changeField": "title",
                    "changeValue": "Project Review",
                }
            ),
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(result.proposedArguments["query"], "planning meeting")
        self.assertEqual(result.proposedArguments["currentTime"], "4 PM")

    def test_rename_strips_duplicate_source_date_from_model_query(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "rename my 4 PM Project Review August 29 to Final Project Review",
            self._decision(
                {
                    "targetDay": "tomorrow",
                    "query": "Project Review August 29",
                    "currentTime": "4 PM",
                    "changeField": "title",
                    "changeValue": "Final Project Review",
                }
            ),
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(
            result.proposedArguments,
            {
                "targetDate": "2026-08-29",
                "query": "Project Review",
                "currentTime": "4 PM",
                "changeField": "title",
                "changeValue": "Final Project Review",
            },
        )
        self.assertNotIn("eventId", result.proposedArguments)

    def test_source_date_cleanup_preserves_date_like_title_words_not_used_as_selector(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "rename my 4 PM Friday Review August 29 to Final Friday Review",
            self._decision(
                {
                    "targetDay": "tomorrow",
                    "query": "4 PM Friday Review August 29",
                    "currentTime": "4 PM",
                    "changeField": "title",
                    "changeValue": "Final Friday Review",
                }
            ),
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(result.proposedArguments["query"], "Friday Review")
        self.assertEqual(result.proposedArguments["targetDate"], "2026-08-29")

    def test_farther_date_rename_preserves_explicit_source_time(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "rename my 3 PM meeting next Saturday to Project Review",
            self._decision(
                {
                    "targetDay": "tomorrow",
                    "query": "meeting",
                    "currentTime": None,
                    "changeField": "title",
                    "changeValue": "Project Review",
                }
            ),
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(result.proposedArguments["currentTime"], "3 PM")

    def test_legacy_tomorrow_source_can_move_to_absolute_destination(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "move my 4 PM meeting tomorrow to August 29",
            self._decision(
                {
                    "targetDay": "tomorrow",
                    "query": "4 PM meeting",
                    "currentTime": "4 PM",
                    "changeField": "day",
                    "changeValue": "tomorrow",
                }
            ),
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(
            result.proposedArguments,
            {
                "targetDay": "tomorrow",
                "query": "meeting",
                "currentTime": "4 PM",
                "changeField": "date",
                "changeValue": "2026-08-29",
            },
        )
        self.assertNotIn("targetDate", result.proposedArguments)
        self.assertNotIn("eventId", result.proposedArguments)

    def test_legacy_today_source_can_move_to_absolute_destination(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "move my meeting today to August 29",
            self._decision(
                {
                    "targetDay": "today",
                    "query": "meeting",
                    "currentTime": None,
                    "changeField": "day",
                    "changeValue": "tomorrow",
                }
            ),
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(result.proposedArguments["targetDay"], "today")
        self.assertEqual(result.proposedArguments["changeField"], "date")
        self.assertEqual(result.proposedArguments["changeValue"], "2026-08-29")

    def test_existing_farther_date_day_move_still_resolves(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "move my 3 PM meeting next Friday to Saturday",
            self._decision(
                {
                    "targetDay": "tomorrow",
                    "query": "meeting",
                    "currentTime": "3 PM",
                    "changeField": "day",
                    "changeValue": "tomorrow",
                }
            ),
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(result.proposedArguments["targetDate"], "2026-08-28")
        self.assertEqual(result.proposedArguments["changeField"], "date")
        self.assertEqual(result.proposedArguments["changeValue"], "2026-08-29")

    def test_multi_day_edit_source_is_poisoned_instead_of_model_day(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "rename my meeting next week to Project Review",
            self._decision(
                {
                    "targetDay": "tomorrow",
                    "query": "meeting",
                    "currentTime": None,
                    "changeField": "title",
                    "changeValue": "Project Review",
                }
            ),
            reference_date=date(2026, 8, 19),
        )

        self.assertEqual(result.turnOwner, "calendar")
        self.assertEqual(result.proposedAction, "edit-last-event")
        self.assertEqual(
            result.proposedArguments,
            {
                "startDate": "2026-08-24",
                "endDate": "2026-08-30",
            },
        )
        self.assertNotIn("targetDay", result.proposedArguments)
        self.assertNotIn("targetDate", result.proposedArguments)

    def test_multi_day_delete_source_is_poisoned_instead_of_model_day(self) -> None:
        result = apply_calendar_absolute_edit_delete_ownership_floor(
            "delete my meeting next week",
            self._decision(
                {
                    "day": "tomorrow",
                    "title": "meeting",
                    "time": None,
                },
                action="delete-calendar-event",
            ),
            reference_date=date(2026, 8, 19),
        )

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

    def test_frontend_already_accepts_absolute_source_time_and_title_changes(self) -> None:
        source = (
            ROOT / "src/app/lib/agentToolPromotion.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("'targetDate'", source)
        self.assertIn("changeField === 'time'", source)
        self.assertIn("changes: { time: newTime }", source)
        self.assertIn("changeField === 'title'", source)
        self.assertIn("changes: { title: newTitle }", source)

    def test_app_still_fails_closed_when_claimed_edit_arguments_are_invalid(self) -> None:
        source = (ROOT / "src/app/App.tsx").read_text(encoding="utf-8")

        self.assertIn("const promotedCalendarEditCandidate", source)
        self.assertIn("if (promotedCalendarEditCandidate && !promotedCalendarEditTool)", source)
        self.assertIn("No calendar change was made.", source)
        self.assertIn("pendingCalendarEditTargetIdRef.current = null", source)

    def test_confirmed_edit_still_requires_locked_identity_and_change(self) -> None:
        source = (ROOT / "src/app/App.tsx").read_text(encoding="utf-8")

        self.assertIn("pendingCalendarEditTargetIdRef.current = targetEditEvent.id", source)
        self.assertIn("pendingCalendarEditChangesRef.current = resolvedCalendarEditChanges", source)
        self.assertIn("!resolvedCalendarEditTargetId || !resolvedCalendarEditChanges", source)


if __name__ == "__main__":
    unittest.main()
