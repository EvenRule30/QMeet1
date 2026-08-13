from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from app import qmeet_agent_shadow as shadow
from app.tool_continuation import (
    TOOL_CONTINUATION_PROMPT,
    ContinuationMessage,
    ToolContinuationRequest,
    build_tool_continuation_input,
)


ROOT = Path(__file__).resolve().parents[2]


class AgentCalendarReadToolPromotionPhase21BTests(unittest.TestCase):
    def _fallback_decision(self, text: str) -> shadow.AgentShadowDecision:
        request = shadow.AgentShadowRequest(
            userMessage=text,
            recentConversation=[],
            uiState={},
            clientContext={},
        )
        return shadow.normalize_shadow_decision(
            shadow._fallback_shadow_decision(request, None)
        )

    def test_natural_calendar_reads_normalize_to_one_read_only_contract(self) -> None:
        cases = {
            "what's on my calendar today?": "today",
            "do I have anything tomorrow?": "tomorrow",
            "what does my schedule look like?": "all",
            "am I free tomorrow?": "tomorrow",
        }

        for text, expected_view in cases.items():
            with self.subTest(text=text):
                decision = self._fallback_decision(text)
                self.assertEqual(decision.turnOwner, "calendar")
                self.assertFalse(decision.focusRelevant)
                self.assertEqual(decision.disposition, "tool")
                self.assertEqual(decision.proposedCapability, "calendar")
                self.assertEqual(decision.proposedAction, "read-calendar")
                self.assertEqual(decision.proposedArguments, {"view": expected_view})

    def test_calendar_write_language_is_not_reinterpreted_as_promoted_read(self) -> None:
        create_decision = self._fallback_decision(
            "schedule a dentist appointment tomorrow"
        )
        self.assertEqual(create_decision.turnOwner, "calendar")
        self.assertEqual(create_decision.disposition, "tool")
        self.assertEqual(create_decision.proposedAction, "add-calendar-event")
        self.assertNotEqual(create_decision.proposedAction, "read-calendar")

        write_phrasings = (
            "delete tomorrow's meeting",
            "I need you to delete tomorrow's meeting",
            "could you please move my meeting tomorrow",
        )
        for text in write_phrasings:
            with self.subTest(text=text):
                decision = self._fallback_decision(text)
                self.assertNotEqual(decision.proposedAction, "read-calendar")

    def test_calendar_capability_contract_exposes_only_promoted_read_schema(self) -> None:
        calendar_contract = next(
            item
            for item in shadow.GLOBAL_CAPABILITY_CONTRACT
            if item.get("owner") == "calendar"
        )
        self.assertEqual(calendar_contract["promotedReadAction"], "read-calendar")
        schema = calendar_contract["readArgumentSchema"]
        self.assertEqual(schema["type"], "object")
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["required"], ["view"])
        self.assertEqual(
            schema["properties"]["view"]["enum"],
            ["today", "tomorrow", "all"],
        )
        self.assertIn("writes remain", calendar_contract["promotionConstraint"])

    def test_frontend_calendar_promotion_is_exact_and_read_only(self) -> None:
        source = (ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts").read_text(
            encoding="utf-8"
        )

        required_fragments = (
            "decision.turnOwner !== 'calendar'",
            "decision.proposedCapability !== 'calendar'",
            "decision.proposedAction !== 'read-calendar'",
            "keys.length !== 1 || keys[0] !== 'view'",
            "'today'",
            "'tomorrow'",
            "'all'",
            "command: 'read-calendar'",
            "calendarView: view",
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, source)

        for forbidden_write in (
            "command: 'add-calendar-event'",
            "command: 'edit-last-event'",
            "command: 'delete-calendar-event'",
            "command: 'delete-last-event'",
            "command: 'clear-calendar'",
        ):
            with self.subTest(forbidden_write=forbidden_write):
                self.assertNotIn(forbidden_write, source)

    def test_app_promotes_calendar_read_after_explicit_route_and_search(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

        explicit_index = source.index("resolveExplicitDeterministicRouteBeforeAgent({")
        single_intent_index = source.index("await resolvePromotedSingleIntentDecision({")
        search_index = source.index("resolvePromotedSearchToolCommand(")
        calendar_index = source.index("resolvePromotedCalendarReadToolCommand(")
        generic_tool_index = source.index("const promotedNonFocusToolOwner =")

        self.assertLess(explicit_index, single_intent_index)
        self.assertLess(single_intent_index, search_index)
        self.assertLess(search_index, calendar_index)
        self.assertLess(calendar_index, generic_tool_index)
        self.assertIn("'Agent-promoted Calendar read'", source)
        self.assertIn("promotedCalendarReadTool.commandMatch", source)
        self.assertIn("visibleUserText,\n        'agent',", source)

    def test_calendar_handler_uses_verified_readout_for_tool_and_continuation(self) -> None:
        source = (
            ROOT / "src" / "app" / "commandHandlers" / "calendar.ts"
        ).read_text(encoding="utf-8")

        self.assertIn("consumeLatestCalendarFocusResponse();", source)
        self.assertIn(
            "const verifiedCalendarReadout = deps.getCalendarReadout(",
            source,
        )
        self.assertIn("confirmationContent: verifiedCalendarReadout", source)
        self.assertIn("continuationContext: verifiedCalendarReadout", source)
        self.assertNotIn(
            "guardedFocusResponse?.tool === 'calendar_read'",
            source,
        )

    def test_unrelated_calendar_read_continuation_excludes_stale_history(self) -> None:
        request = ToolContinuationRequest(
            userMessage="am I free tomorrow?",
            capability="calendar",
            action="read-calendar",
            toolResult="Tomorrow: No events.",
            toolContext="Tomorrow: No events.",
            verified=True,
            success=True,
            verificationSource="frontend-deterministic-command",
            recentConversation=[
                ContinuationMessage(
                    role="user",
                    content="Help me work on my diabetes presentation focus.",
                ),
                ContinuationMessage(
                    role="assistant",
                    content="STALE_FOCUS_PROSE_SHOULD_NOT_LEAK",
                ),
            ],
            uiContext={"activePanel": "calendar", "command": "read-calendar"},
        )

        with patch("app.tool_continuation.active_focus_snapshot", return_value=None):
            messages = build_tool_continuation_input(request)

        serialized = json.dumps(messages, ensure_ascii=False)
        final_context_message = messages[-1]["content"]
        self.assertNotIn("STALE_FOCUS_PROSE_SHOULD_NOT_LEAK", serialized)
        self.assertIn("Tomorrow: No events.", final_context_message)
        self.assertIn('"focusContextIncluded": false', final_context_message)

    def test_focus_connected_calendar_read_can_receive_advisory_focus_context(self) -> None:
        focus = {
            "focusId": "focus-framework",
            "title": "Framework Laptop repairability report",
            "objective": "Prepare a Framework Laptop repairability report",
            "deliverable": "repairability report",
            "subject": "Framework Laptop repairability",
            "requirements": [],
            "constraints": [],
            "preferences": [],
            "decisions": [],
            "knownFacts": [],
            "milestones": [],
            "completedMilestones": [],
            "nextAction": "Review the presentation schedule",
            "pendingQuestion": None,
            "status": "active",
        }
        request = ToolContinuationRequest(
            userMessage="what does my schedule look like for my Framework Laptop focus?",
            capability="calendar",
            action="read-calendar",
            toolResult="Today at 3:00 PM: review repairability slides.",
            toolContext="Today at 3:00 PM: review repairability slides.",
            verified=True,
            success=True,
            verificationSource="frontend-deterministic-command",
            recentConversation=[
                ContinuationMessage(
                    role="assistant",
                    content="RELEVANT_FOCUS_HISTORY_CAN_REMAIN",
                )
            ],
            uiContext={"activePanel": "calendar", "command": "read-calendar"},
        )

        with patch(
            "app.tool_continuation.active_focus_snapshot",
            return_value=focus,
        ):
            messages = build_tool_continuation_input(request)

        serialized = json.dumps(messages, ensure_ascii=False)
        final_context_message = messages[-1]["content"]
        self.assertIn("RELEVANT_FOCUS_HISTORY_CAN_REMAIN", serialized)
        self.assertIn('"focusContextIncluded": true', final_context_message)
        self.assertIn("Framework Laptop repairability report", final_context_message)
        self.assertIn("Today at 3:00 PM: review repairability slides.", final_context_message)

    def test_calendar_continuation_prompt_requires_verified_schedule_grounding(self) -> None:
        self.assertIn(
            "For Calendar reads, every claim about events, schedule contents, availability, or free/busy status",
            TOOL_CONTINUATION_PROMPT,
        )
        self.assertIn(
            "Never reconstruct Calendar state from model memory or stale recentConversation.",
            TOOL_CONTINUATION_PROMPT,
        )


if __name__ == "__main__":
    unittest.main()
