from __future__ import annotations

import unittest
from pathlib import Path

from app import qmeet_agent_shadow as shadow


ROOT = Path(__file__).resolve().parents[2]


class AgentCalendarEditToolPromotionPhase21BTests(unittest.TestCase):
    def test_calendar_contract_exposes_targeted_edit_schema_without_event_identity(self) -> None:
        calendar_contract = next(
            item
            for item in shadow.GLOBAL_CAPABILITY_CONTRACT
            if item.get("owner") == "calendar"
        )

        self.assertEqual(calendar_contract["promotedEditAction"], "edit-last-event")
        schema = calendar_contract["editArgumentSchema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            schema["required"],
            ["targetDay", "targetTitle", "targetTime", "newDay", "newTitle", "newTime"],
        )
        self.assertNotIn("eventId", schema["properties"])
        self.assertIn("zero/one/multiple target resolution", calendar_contract["promotionConstraint"])

    def test_backend_edit_validator_requires_one_target_and_one_change(self) -> None:
        valid = {
            "targetDay": "tomorrow",
            "targetTitle": "business meeting",
            "targetTime": None,
            "newDay": None,
            "newTitle": None,
            "newTime": "4 PM",
        }
        self.assertTrue(shadow._is_valid_calendar_edit_arguments(valid))

        no_target = dict(valid, targetTitle=None)
        self.assertFalse(shadow._is_valid_calendar_edit_arguments(no_target))

        no_change = dict(valid, newTime=None)
        self.assertFalse(shadow._is_valid_calendar_edit_arguments(no_change))

        day_only = dict(valid, newDay="today", newTime=None)
        self.assertFalse(shadow._is_valid_calendar_edit_arguments(day_only))

        with_event_id = dict(valid, eventId="google-secret-id")
        self.assertFalse(shadow._is_valid_calendar_edit_arguments(with_event_id))

    def test_calendar_edit_ownership_floor_cannot_fall_back_to_conversation(self) -> None:
        request = shadow.AgentShadowRequest(
            userMessage="move my business meeting tomorrow to 4 PM",
            recentConversation=[],
            uiState={},
        )
        model_decision = shadow.AgentShadowDecision(
            turnOwner="general_chat",
            focusRelevant=False,
            disposition="conversation",
            proposedCapability="none",
            proposedAction="conversation.respond",
            proposedArguments={},
            responsePlan="Answer conversationally.",
            confidence=0.88,
            reason="Incorrect model fallback for regression coverage.",
        )

        result = shadow.apply_calendar_write_ownership_floor(request, None, model_decision)

        self.assertEqual(result.turnOwner, "calendar")
        self.assertEqual(result.disposition, "tool")
        self.assertEqual(result.proposedAction, "edit-last-event")

    def test_today_named_edit_is_calendar_owned_before_target_resolution(self) -> None:
        request = shadow.AgentShadowRequest(
            userMessage="move my business meeting today to 4 PM",
            recentConversation=[],
            uiState={},
        )
        fallback = shadow._fallback_shadow_decision(request, None)

        self.assertEqual(fallback.turnOwner, "calendar")
        self.assertEqual(fallback.disposition, "tool")
        self.assertEqual(fallback.proposedAction, "edit-last-event")
        self.assertGreaterEqual(fallback.confidence, 0.95)

    def test_sparse_nullable_model_edit_arguments_are_canonicalized_before_ownership_floor(self) -> None:
        request = shadow.AgentShadowRequest(
            userMessage="move my business meeting today to 4 PM",
            recentConversation=[],
            uiState={},
        )
        sparse = shadow.AgentShadowDecision(
            turnOwner="calendar",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="calendar",
            proposedAction="edit-last-event",
            proposedArguments={
                "targetDay": "today",
                "targetTitle": "business meeting",
                "newTime": "4 PM",
            },
            responsePlan="Resolve one event, confirm, then update it.",
            confidence=0.96,
            reason="One targeted Calendar edit with omitted null fields.",
        )

        normalized = shadow.normalize_shadow_decision(sparse)
        self.assertEqual(
            normalized.proposedArguments,
            {
                "targetDay": "today",
                "targetTitle": "business meeting",
                "targetTime": None,
                "newDay": None,
                "newTitle": None,
                "newTime": "4 PM",
            },
        )
        result = shadow.apply_calendar_write_ownership_floor(request, None, normalized)
        self.assertTrue(shadow._is_executable_calendar_edit_tool_decision(result))
        self.assertEqual(result.proposedArguments, normalized.proposedArguments)

        rename_sparse = shadow.AgentShadowDecision(
            turnOwner="calendar",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="calendar",
            proposedAction="edit-last-event",
            proposedArguments={
                "targetDay": "today",
                "targetTitle": "business meeting",
                "newTitle": "executive planning meeting",
            },
            responsePlan="Resolve one event, confirm, then rename it.",
            confidence=0.96,
            reason="One targeted Calendar rename with omitted null fields.",
        )
        rename_normalized = shadow.normalize_shadow_decision(rename_sparse)
        self.assertTrue(
            shadow._is_valid_calendar_edit_arguments(rename_normalized.proposedArguments)
        )
        self.assertEqual(
            rename_normalized.proposedArguments["newTitle"],
            "executive planning meeting",
        )
        self.assertIsNone(rename_normalized.proposedArguments["newTime"])

    def test_edit_argument_shape_normalizer_does_not_repair_unknown_or_missing_required_fields(self) -> None:
        with_unknown = shadow._normalize_calendar_edit_argument_shape(
            {
                "targetDay": "today",
                "targetTitle": "business meeting",
                "newTime": "4 PM",
                "eventId": "must-not-be-accepted",
            }
        )
        self.assertIn("eventId", with_unknown)
        self.assertFalse(shadow._is_valid_calendar_edit_arguments(with_unknown))

        missing_target_day = shadow._normalize_calendar_edit_argument_shape(
            {"targetTitle": "business meeting", "newTime": "4 PM"}
        )
        self.assertNotIn("targetDay", missing_target_day)
        self.assertFalse(shadow._is_valid_calendar_edit_arguments(missing_target_day))

    def test_valid_model_edit_proposal_survives_ownership_floor(self) -> None:
        request = shadow.AgentShadowRequest(
            userMessage="move my business meeting tomorrow to 4 PM",
            recentConversation=[],
            uiState={},
        )
        decision = shadow.AgentShadowDecision(
            turnOwner="calendar",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="calendar",
            proposedAction="edit-last-event",
            proposedArguments={
                "targetDay": "tomorrow",
                "targetTitle": "business meeting",
                "targetTime": None,
                "newDay": None,
                "newTitle": None,
                "newTime": "4 PM",
            },
            responsePlan="Resolve one event, confirm, then update it.",
            confidence=0.96,
            reason="One targeted Calendar edit.",
        )

        result = shadow.apply_calendar_write_ownership_floor(request, None, decision)

        self.assertEqual(result.proposedArguments, decision.proposedArguments)
        self.assertTrue(shadow._is_executable_calendar_edit_tool_decision(result))

    def test_frontend_validator_separates_target_criteria_from_changes(self) -> None:
        source = (ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("resolvePromotedCalendarEditToolCommand", source)
        self.assertIn("isPromotedCalendarEditToolDecision", source)
        self.assertIn("'targetDay'", source)
        self.assertIn("'targetTitle'", source)
        self.assertIn("'targetTime'", source)
        self.assertIn("'newDay'", source)
        self.assertIn("'newTitle'", source)
        self.assertIn("'newTime'", source)
        self.assertIn("calendarEditRoundTripsThroughCanonicalParser", source)
        self.assertIn("parseCommand(buildCalendarEditFrontendCommand(changes))", source)
        self.assertIn("command: 'edit-last-event'", source)
        self.assertNotIn("eventId: validated", source)

    def test_explicit_calendar_write_waits_for_agent_beyond_default_budget(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("const AGENT_FIRST_EXPLICIT_CALENDAR_WRITE_WAIT_MS = 7000;", source)
        self.assertIn(
            "timeoutMs: explicitCalendarWriteIntent\n"
            "              ? AGENT_FIRST_EXPLICIT_CALENDAR_WRITE_WAIT_MS\n"
            "              : undefined,",
            source,
        )
        observer = (
            ROOT / "src" / "app" / "lib" / "agentShadowObserver.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("const AGENT_FIRST_SINGLE_INTENT_WAIT_MS = 2500;", observer)

    def test_app_resolves_zero_one_many_before_edit_confirmation(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

        promoted_index = source.index("'Agent-promoted Calendar edit'")
        edit_confirmation_index = source.index(
            "if (commandRoute !== 'confirmed' && commandMatch.command === 'edit-last-event')"
        )
        self.assertLess(promoted_index, edit_confirmation_index)
        self.assertIn("getCalendarEventsForDeleteCriteria(", source[edit_confirmation_index:])
        self.assertIn("calendarEventMatchesDeleteCriteria(", source[edit_confirmation_index:])
        self.assertIn("if (matchingEvents.length > 1)", source[edit_confirmation_index:])
        self.assertIn("matchingEvents[0] ?? null", source[edit_confirmation_index:])
        self.assertIn("No calendar change was made.", source[edit_confirmation_index:])

    def test_edit_confirmation_locks_resolved_event_identity(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("pendingCalendarEditTargetIdRef.current = targetEditEvent.id", source)
        self.assertIn("const resolvedCalendarEditTargetId", source)
        self.assertIn("'Confirmed Calendar edit target missing'", source)
        self.assertIn(
            "updateCalendarEvent(confirmedCalendarEditTargetId, changes)",
            source,
        )
        self.assertIn(
            "Exactly one canonical Calendar event was resolved and its identity is locked across confirmation.",
            source,
        )


if __name__ == "__main__":
    unittest.main()
