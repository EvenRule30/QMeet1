from __future__ import annotations

import unittest
from pathlib import Path

from app import qmeet_agent_shadow as shadow


ROOT = Path(__file__).resolve().parents[2]


class AgentCalendarDeleteToolPromotionPhase21BTests(unittest.TestCase):
    def _request(self, text: str) -> shadow.AgentShadowRequest:
        return shadow.AgentShadowRequest(
            userMessage=text,
            recentConversation=[],
            uiState={},
            clientContext={},
        )

    def test_calendar_contract_exposes_targeted_delete_schema(self) -> None:
        calendar_contract = next(
            item
            for item in shadow.GLOBAL_CAPABILITY_CONTRACT
            if item.get("owner") == "calendar"
        )
        self.assertEqual(
            calendar_contract["promotedDeleteAction"],
            "delete-calendar-event",
        )
        schema = calendar_contract["deleteArgumentSchema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["required"], ["day", "title", "time"])
        self.assertEqual(
            schema["properties"]["day"]["enum"],
            ["today", "tomorrow"],
        )
        self.assertIn(
            "zero/one/multiple target resolution",
            calendar_contract["promotionConstraint"],
        )

    def test_delete_argument_validator_requires_day_and_one_selector(self) -> None:
        self.assertTrue(
            shadow._is_valid_calendar_delete_arguments(
                {"day": "tomorrow", "title": "meeting", "time": None}
            )
        )
        self.assertTrue(
            shadow._is_valid_calendar_delete_arguments(
                {"day": "tomorrow", "title": None, "time": "2 PM"}
            )
        )
        self.assertFalse(
            shadow._is_valid_calendar_delete_arguments(
                {"day": "tomorrow", "title": None, "time": None}
            )
        )
        self.assertFalse(
            shadow._is_valid_calendar_delete_arguments(
                {"day": None, "title": "meeting", "time": None}
            )
        )
        self.assertFalse(
            shadow._is_valid_calendar_delete_arguments(
                {
                    "day": "tomorrow",
                    "title": "meeting",
                    "time": None,
                    "eventId": "model-must-not-pick-this",
                }
            )
        )

    def test_valid_agent_delete_survives_calendar_ownership_floor(self) -> None:
        decision = shadow.AgentShadowDecision(
            turnOwner="calendar",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="calendar",
            proposedAction="delete-calendar-event",
            proposedArguments={
                "day": "tomorrow",
                "title": "meeting",
                "time": None,
            },
            responsePlan="Resolve canonical Calendar candidates, then confirm one target.",
            confidence=0.94,
            reason="Targeted Calendar deletion.",
        )
        result = shadow.apply_calendar_write_ownership_floor(
            self._request("delete tomorrow's meeting"),
            None,
            shadow.normalize_shadow_decision(decision),
        )
        self.assertEqual(result.turnOwner, "calendar")
        self.assertEqual(result.proposedAction, "delete-calendar-event")
        self.assertEqual(
            result.proposedArguments,
            {"day": "tomorrow", "title": "meeting", "time": None},
        )

    def test_frontend_delete_validator_builds_criteria_only(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("resolvePromotedCalendarDeleteToolCommand", source)
        self.assertIn("isPromotedCalendarDeleteToolDecision", source)
        self.assertIn(
            "hasExactlyKeys(argumentsValue, ['day', 'title', 'time'])",
            source,
        )
        self.assertIn("calendarDeleteRoundTripsThroughCanonicalParser", source)
        self.assertIn("command: 'delete-calendar-event'", source)
        self.assertIn("calendarDelete:", source)
        self.assertNotIn("eventId:", source)
        self.assertNotIn("googleEventId:", source)

    def test_app_resolves_zero_one_or_many_before_confirmation(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("getCalendarEventsForDeleteCriteria(commandMatch.calendarDelete)", source)
        self.assertIn("calendarEventMatchesDeleteCriteria(event, commandMatch.calendarDelete)", source)
        self.assertIn("targetedDeleteMatches.length === 1", source)
        self.assertIn("targetedDeleteMatches.length > 1", source)
        self.assertIn("Delete command had multiple targets", source)
        self.assertIn("Please specify the time or more of the title", source)
        self.assertIn("No calendar change was made.", source)

    def test_confirmation_is_bound_to_resolved_event_identity(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("pendingCalendarDeleteTargetIdRef", source)
        self.assertIn("? targetDeleteEvent.id", source)
        self.assertIn("resolvedCalendarDeleteTargetId", source)
        self.assertIn("confirmedCalendarDeleteTargetId", source)
        self.assertIn("deleteCalendarEvent(confirmedCalendarDeleteTargetId)", source)
        self.assertIn("Confirmed Calendar delete target missing", source)
        self.assertIn("refused to re-resolve a different event", source)

    def test_legacy_targeted_delete_must_use_same_candidate_resolver(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("parsedInterpreterDestructiveCommand", source)
        self.assertIn(
            "parsedInterpreterDestructiveCommand?.command === 'delete-calendar-event'",
            source,
        )
        self.assertIn(
            "Fuzzy Calendar delete needs deterministic target resolution",
            source,
        )


if __name__ == "__main__":
    unittest.main()
