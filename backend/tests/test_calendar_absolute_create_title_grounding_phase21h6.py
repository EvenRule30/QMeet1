from __future__ import annotations

import unittest
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from app.calendar_read_date_interpreter import (
    apply_calendar_absolute_create_ownership_floor,
)


@dataclass(frozen=True)
class _Decision:
    turnOwner: str = "calendar"
    focusRelevant: bool = False
    disposition: str = "tool"
    proposedCapability: str = "calendar"
    proposedAction: str = "add-calendar-event"
    proposedArguments: dict[str, Any] | None = None
    responsePlan: str = ""
    confidence: float = 0.9
    reason: str = "model proposal"

    def model_copy(self, *, update: dict[str, Any]):
        return replace(self, **update)


class CalendarAbsoluteCreateTitleGroundingPhase21H6Tests(unittest.TestCase):
    def _repair(self, user_message: str, proposed_title: str):
        decision = _Decision(
            proposedArguments={
                "date": "2026-08-25",
                "title": proposed_title,
                "time": "2 PM",
            }
        )
        return apply_calendar_absolute_create_ownership_floor(
            user_message,
            decision,
            reference_date=date(2026, 8, 21),
        )

    def test_called_title_outranks_poisoned_model_title(self):
        repaired = self._repair(
            "create a calendar event on August 25 at 2 PM called QMeet Regression Meeting",
            "Calendar Event On",
        )

        self.assertEqual(
            repaired.proposedArguments,
            {
                "date": "2026-08-25",
                "title": "QMeet Regression Meeting",
                "time": "2 PM",
            },
        )

    def test_named_title_outranks_model_title(self):
        repaired = self._repair(
            "create a calendar event on August 25 at 2 PM named Product Review",
            "Calendar Event On",
        )
        self.assertEqual(repaired.proposedArguments["title"], "Product Review")

    def test_titled_title_outranks_model_title(self):
        repaired = self._repair(
            "create a calendar event on August 25 at 2 PM titled Release Check",
            "Calendar Event On",
        )
        self.assertEqual(repaired.proposedArguments["title"], "Release Check")

    def test_wrapped_explicit_title_is_unwrapped(self):
        repaired = self._repair(
            'create a calendar event on August 25 at 2 PM called "QMeet Regression Meeting"',
            "Calendar Event On",
        )
        self.assertEqual(
            repaired.proposedArguments["title"],
            "QMeet Regression Meeting",
        )

    def test_model_semantic_title_is_preserved_without_explicit_naming_marker(self):
        repaired = self._repair(
            "schedule a dentist appointment August 25 at 2 PM",
            "Dentist Appointment",
        )
        self.assertEqual(repaired.proposedArguments["title"], "Dentist Appointment")

    def test_explicit_title_does_not_change_absolute_date_or_time(self):
        repaired = self._repair(
            "create a calendar event on August 25 at 2 PM called QMeet Regression Meeting",
            "Calendar Event On",
        )
        self.assertEqual(repaired.proposedArguments["date"], "2026-08-25")
        self.assertEqual(repaired.proposedArguments["time"], "2 PM")
        self.assertEqual(repaired.proposedAction, "add-calendar-event")
        self.assertEqual(repaired.turnOwner, "calendar")


if __name__ == "__main__":
    unittest.main()
