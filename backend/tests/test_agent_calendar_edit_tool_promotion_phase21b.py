from __future__ import annotations

import unittest
from pathlib import Path

from app import qmeet_agent_shadow as shadow


ROOT = Path(__file__).resolve().parents[2]


class AgentCalendarEditToolPromotionPhase21BTests(unittest.TestCase):
    def _request(self, text: str) -> shadow.AgentShadowRequest:
        return shadow.AgentShadowRequest(
            userMessage=text,
            recentConversation=[],
            uiState={},
            clientContext={},
        )

    def test_calendar_contract_separates_source_day_from_one_change(self) -> None:
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
            ["targetDay", "query", "currentTime", "changeField", "changeValue"],
        )
        self.assertEqual(
            schema["properties"]["changeField"]["enum"],
            ["time", "title", "day"],
        )
        self.assertNotIn("eventId", schema["properties"])
        self.assertIn("targetDay identifies where the event exists before the edit", schema["constraint"])
        self.assertIn("exact/likely/ambiguous/none", calendar_contract["promotionConstraint"])

    def test_backend_edit_validator_accepts_time_title_or_day_change(self) -> None:
        base = {
            "targetDay": "today",
            "query": "business meeting",
            "currentTime": None,
        }
        self.assertTrue(
            shadow._is_valid_calendar_edit_arguments(
                dict(base, changeField="time", changeValue="4 PM")
            )
        )
        self.assertTrue(
            shadow._is_valid_calendar_edit_arguments(
                dict(base, changeField="title", changeValue="Executive Planning Meeting")
            )
        )
        self.assertTrue(
            shadow._is_valid_calendar_edit_arguments(
                dict(base, changeField="day", changeValue="tomorrow")
            )
        )
        self.assertFalse(
            shadow._is_valid_calendar_edit_arguments(
                dict(base, changeField="day", changeValue="today")
            )
        )
        self.assertFalse(
            shadow._is_valid_calendar_edit_arguments(
                dict(base, changeField="location", changeValue="Boardroom")
            )
        )
        self.assertFalse(
            shadow._is_valid_calendar_edit_arguments(
                dict(base, changeField="time", changeValue="4 PM", eventId="secret")
            )
        )

    def test_sparse_current_time_is_canonicalized_to_null(self) -> None:
        normalized = shadow._normalize_calendar_edit_argument_shape(
            {
                "targetDay": "today",
                "query": "business meeting",
                "changeField": "time",
                "changeValue": "4 PM",
            }
        )
        self.assertEqual(
            normalized,
            {
                "targetDay": "today",
                "query": "business meeting",
                "currentTime": None,
                "changeField": "time",
                "changeValue": "4 PM",
            },
        )
        self.assertTrue(shadow._is_valid_calendar_edit_arguments(normalized))

    def test_previous_day_key_contract_migrates_to_target_day(self) -> None:
        normalized = shadow._normalize_calendar_edit_argument_shape(
            {
                "day": "today",
                "query": "business meeting",
                "changeField": "time",
                "changeValue": "4 PM",
            }
        )
        self.assertEqual(
            normalized,
            {
                "targetDay": "today",
                "query": "business meeting",
                "currentTime": None,
                "changeField": "time",
                "changeValue": "4 PM",
            },
        )

    def test_legacy_six_field_day_move_is_migrated_without_resolving_state(self) -> None:
        normalized = shadow._normalize_calendar_edit_argument_shape(
            {
                "targetDay": "today",
                "targetTitle": "business meeting",
                "targetTime": None,
                "newDay": "tomorrow",
                "newTitle": None,
                "newTime": None,
            }
        )
        self.assertEqual(
            normalized,
            {
                "targetDay": "today",
                "query": "business meeting",
                "currentTime": None,
                "changeField": "day",
                "changeValue": "tomorrow",
            },
        )
        self.assertTrue(shadow._is_valid_calendar_edit_arguments(normalized))

    def test_legacy_multiple_change_stays_invalid(self) -> None:
        multiple = shadow._normalize_calendar_edit_argument_shape(
            {
                "targetDay": "today",
                "targetTitle": "business meeting",
                "targetTime": None,
                "newDay": "tomorrow",
                "newTitle": None,
                "newTime": "4 PM",
            }
        )
        self.assertIn("newDay", multiple)
        self.assertFalse(shadow._is_valid_calendar_edit_arguments(multiple))

    def test_calendar_ownership_floor_repairs_metadata_but_not_arguments(self) -> None:
        decision = shadow.AgentShadowDecision(
            turnOwner="other",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="other",
            proposedAction="edit-last-event",
            proposedArguments={
                "targetDay": "today",
                "query": "business meeting",
                "changeField": "day",
                "changeValue": "tomorrow",
            },
            responsePlan="Move the event.",
            confidence=0.9,
            reason="Right edit semantics, wrong metadata.",
        )
        result = shadow.apply_calendar_write_ownership_floor(
            self._request("move my business meeting today to tomorrow"),
            None,
            shadow.normalize_shadow_decision(decision),
        )
        self.assertEqual(result.turnOwner, "calendar")
        self.assertEqual(result.proposedCapability, "calendar")
        self.assertEqual(result.proposedAction, "edit-last-event")
        self.assertEqual(
            result.proposedArguments,
            {
                "targetDay": "today",
                "query": "business meeting",
                "currentTime": None,
                "changeField": "day",
                "changeValue": "tomorrow",
            },
        )
        self.assertIn("ownership metadata", result.reason)

    def test_ownership_floor_drops_current_time_inferred_only_from_history(self) -> None:
        decision = shadow.AgentShadowDecision(
            turnOwner="calendar",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="calendar",
            proposedAction="edit-last-event",
            proposedArguments={
                "targetDay": "today",
                "query": "business meeting",
                "currentTime": "4 PM",
                "changeField": "day",
                "changeValue": "tomorrow",
            },
            responsePlan="Move the event and preserve its time.",
            confidence=0.95,
            reason="Calendar edit using recent context.",
        )
        result = shadow.apply_calendar_write_ownership_floor(
            self._request("move my business meeting today to tomorrow, same time"),
            None,
            shadow.normalize_shadow_decision(decision),
        )
        self.assertIsNone(result.proposedArguments["currentTime"])
        self.assertEqual(result.proposedArguments["targetDay"], "today")
        self.assertEqual(result.proposedArguments["changeField"], "day")
        self.assertEqual(result.proposedArguments["changeValue"], "tomorrow")

    def test_explicit_current_time_can_still_narrow_target_lookup(self) -> None:
        decision = shadow.AgentShadowDecision(
            turnOwner="calendar",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="calendar",
            proposedAction="edit-last-event",
            proposedArguments={
                "targetDay": "today",
                "query": "business meeting",
                "currentTime": "4 PM",
                "changeField": "day",
                "changeValue": "tomorrow",
            },
            responsePlan="Move the event.",
            confidence=0.95,
            reason="Calendar edit with explicit current time.",
        )
        result = shadow.apply_calendar_write_ownership_floor(
            self._request("move my 4 PM business meeting today to tomorrow"),
            None,
            shadow.normalize_shadow_decision(decision),
        )
        self.assertEqual(result.proposedArguments["currentTime"], "4 PM")

    def test_prompt_makes_source_and_destination_day_unambiguous(self) -> None:
        prompt = shadow.AGENT_SHADOW_SYSTEM_PROMPT
        self.assertIn('"targetDay": "today" | "tomorrow"', prompt)
        self.assertIn('targetDay is always where the event exists now', prompt)
        self.assertIn('changeField="day", changeValue="tomorrow"', prompt)
        self.assertIn('"same time" means preserve the existing time', prompt)

    def test_frontend_edit_validator_supports_day_move_without_event_id(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("'targetDay'", source)
        self.assertIn("changeField === 'time'", source)
        self.assertIn("changeField === 'title'", source)
        self.assertIn("changeField === 'day'", source)
        self.assertIn("changes: { day: changeValue as PromotedCalendarCreateDay }", source)
        self.assertIn("changes.day &&", source)
        self.assertIn("!changes.time &&", source)
        self.assertIn("!changes.title &&", source)
        self.assertIn("PROMOTED_CALENDAR_CREATE_DAYS.has(changes.day)", source)
        self.assertNotIn("eventId:", source)

    def test_app_resolves_source_day_and_locks_both_identity_and_changes(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("resolveCalendarEventReference", source)
        self.assertIn("day: promotedCalendarEditTargetCriteria.day", source)
        self.assertIn("pendingCalendarEditTargetIdRef.current = targetEditEvent.id", source)
        self.assertIn("pendingCalendarEditChangesRef.current = resolvedCalendarEditChanges", source)
        self.assertIn("resolvedCalendarEditChanges", source)
        self.assertIn("calendarEdit: { ...resolvedCalendarEditChanges }", source)
        self.assertIn("updateCalendarEvent(confirmedCalendarEditTargetId, changes)", source)

    def test_day_only_move_preserves_resolved_event_time_before_confirmation(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("const resolvedCalendarEditChanges = commandMatch.calendarEdit", source)
        self.assertIn("commandMatch.calendarEdit.day &&", source)
        self.assertIn("!commandMatch.calendarEdit.time?.trim()", source)
        self.assertIn("{ time: targetEditEvent.time || 'All day' }", source)
        self.assertIn("describeCalendarEditPayload(\n          resolvedCalendarEditChanges", source)
        self.assertIn("buildCalendarEditFrontendCommand(\n          resolvedCalendarEditChanges", source)
        self.assertIn("pendingCalendarEditChangesRef.current = resolvedCalendarEditChanges", source)

    def test_explicit_calendar_mutation_keeps_longer_agent_wait(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("AGENT_FIRST_EXPLICIT_CALENDAR_WRITE_WAIT_MS = 7000", source)
        self.assertIn("timeoutMs: explicitCalendarWriteIntent", source)


if __name__ == "__main__":
    unittest.main()
