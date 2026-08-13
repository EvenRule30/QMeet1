from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from app import qmeet_agent_shadow as shadow
from app.tool_continuation import (
    ContinuationMessage,
    ToolContinuationRequest,
    build_tool_continuation_input,
)


ROOT = Path(__file__).resolve().parents[2]


class AgentCalendarCreateToolPromotionPhase21BTests(unittest.TestCase):
    def _request(self, text: str) -> shadow.AgentShadowRequest:
        return shadow.AgentShadowRequest(
            userMessage=text,
            recentConversation=[],
            uiState={},
            clientContext={},
        )

    def _fallback(self, text: str, focus: dict | None = None) -> shadow.AgentShadowDecision:
        return shadow.normalize_shadow_decision(
            shadow._fallback_shadow_decision(self._request(text), focus)
        )

    def test_no_time_create_has_typed_null_time_proposal(self) -> None:
        decision = self._fallback("schedule a Dungeons and Dragons session tomorrow")

        self.assertEqual(decision.turnOwner, "calendar")
        self.assertFalse(decision.focusRelevant)
        self.assertEqual(decision.disposition, "tool")
        self.assertEqual(decision.proposedCapability, "calendar")
        self.assertEqual(decision.proposedAction, "add-calendar-event")
        self.assertEqual(
            decision.proposedArguments,
            {
                "day": "tomorrow",
                "title": "a Dungeons and Dragons session",
                "time": None,
            },
        )

    def test_timed_cross_capability_create_keeps_calendar_owner_and_focus_context(self) -> None:
        focus = {
            "focusId": "focus-presentation",
            "title": "Executive presentation",
            "objective": "Present project goals to executives",
            "subject": "project presentation",
            "requirements": [],
            "knownFacts": [],
            "nextAction": "Practice the presentation",
            "status": "active",
        }
        decision = self._fallback(
            "add practice time for my presentation tomorrow at 2",
            focus,
        )

        self.assertEqual(decision.turnOwner, "calendar")
        self.assertTrue(decision.focusRelevant)
        self.assertEqual(decision.proposedAction, "add-calendar-event")
        self.assertEqual(decision.proposedArguments["day"], "tomorrow")
        self.assertEqual(decision.proposedArguments["time"], "2")
        self.assertIn("presentation", decision.proposedArguments["title"].casefold())

    def test_calendar_create_ownership_floor_overrides_conversation_without_executing(self) -> None:
        request = self._request("schedule a Dungeons and Dragons session tomorrow")
        model_conversation = shadow.AgentShadowDecision(
            turnOwner="general_chat",
            focusRelevant=False,
            disposition="conversation",
            proposedCapability="none",
            proposedAction="conversation.respond",
            proposedArguments={},
            responsePlan="Answer conversationally.",
            confidence=0.92,
            reason="Model incorrectly treated the request as chat.",
        )

        decision = shadow.apply_calendar_write_ownership_floor(
            request,
            None,
            shadow.normalize_shadow_decision(model_conversation),
        )

        self.assertEqual(decision.turnOwner, "calendar")
        self.assertEqual(decision.disposition, "tool")
        self.assertEqual(decision.proposedAction, "add-calendar-event")
        self.assertEqual(decision.proposedArguments["day"], "tomorrow")
        self.assertIsNone(decision.proposedArguments["time"])
        self.assertIn("ownership floor", decision.reason)

    def test_delete_write_ownership_floor_prevents_focus_or_chat_theft_but_stays_unpromoted(self) -> None:
        request = self._request("delete tomorrow's meeting")
        wrong_focus = shadow.AgentShadowDecision(
            turnOwner="focus",
            focusRelevant=True,
            disposition="conversation",
            proposedCapability="focus",
            proposedAction="focus.help",
            proposedArguments={},
            responsePlan="Continue Focus conversation.",
            confidence=0.9,
            reason="Incorrect Focus ownership.",
        )

        decision = shadow.apply_calendar_write_ownership_floor(
            request,
            None,
            shadow.normalize_shadow_decision(wrong_focus),
        )

        self.assertEqual(decision.turnOwner, "calendar")
        self.assertEqual(decision.disposition, "tool")
        self.assertEqual(decision.proposedAction, "delete-calendar-event")
        self.assertEqual(decision.proposedArguments, {"request": "delete tomorrow's meeting"})

        frontend_source = (
            ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts"
        ).read_text(encoding="utf-8")
        self.assertNotIn("command: 'delete-calendar-event'", frontend_source)

    def test_broad_schedule_planning_is_not_promoted_as_one_create(self) -> None:
        decision = self._fallback("schedule my day tomorrow")
        self.assertFalse(
            decision.turnOwner == "calendar"
            and decision.disposition == "tool"
            and decision.proposedAction == "add-calendar-event"
            and set(decision.proposedArguments) == {"day", "title", "time"}
        )

    def test_frontend_create_validator_is_strict_and_reenters_existing_confirmation_path(self) -> None:
        promotion_source = (
            ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts"
        ).read_text(encoding="utf-8")
        app_source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("hasExactlyKeys(argumentsValue, ['day', 'title', 'time'])", promotion_source)
        self.assertIn("PROMOTED_CALENDAR_CREATE_DAYS", promotion_source)
        self.assertIn("MAX_PROMOTED_CALENDAR_TITLE_LENGTH", promotion_source)
        self.assertIn("readValidatedCalendarCreateTime", promotion_source)
        self.assertIn("calendarCreateRoundTripsThroughCanonicalParser", promotion_source)
        self.assertIn("parseCommand(buildCalendarCreateFrontendCommand(options))", promotion_source)
        self.assertIn("command: 'add-calendar-event'", promotion_source)
        self.assertIn("time: validated.time ?? 'Later'", promotion_source)

        promoted_index = app_source.index("'Agent-promoted Calendar create'")
        confirmation_index = app_source.index(
            "commandMatch.command === 'add-calendar-event'",
            promoted_index,
        )
        self.assertLess(promoted_index, confirmation_index)
        self.assertIn("promotedCalendarCreateTool.commandMatch", app_source)
        self.assertIn("'agent'", app_source[promoted_index:confirmation_index])
        self.assertIn("Google Calendar event creation requires confirmation", app_source)

    def test_missing_time_confirmation_matches_all_day_execution_semantics(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("const isAllDay = targetTime.toLowerCase() === 'later';", source)
        self.assertIn("const frontendCommand = `add event ${targetView} at ${targetTime} called ${targetTitle}`;", source)
        self.assertIn("${isAllDay ? 'all day' : `at ${targetTime}`}", source)
        self.assertNotIn("event ${targetView} at ${targetTime}: ${targetTitle}", source)

    def test_unrelated_calendar_create_continuation_excludes_stale_focus_history(self) -> None:
        focus = {
            "focusId": "focus-business-meeting",
            "title": "business meeting tomorrow",
            "objective": "clarify project goals to the executives",
            "subject": "business meeting",
            "requirements": [],
            "constraints": [],
            "preferences": [],
            "decisions": [],
            "knownFacts": [],
            "milestones": [],
            "completedMilestones": [],
            "nextAction": "Prepare executive talking points",
            "pendingQuestion": None,
            "status": "active",
        }
        request = ToolContinuationRequest(
            userMessage="schedule a Dungeons and Dragons session tomorrow",
            capability="calendar",
            action="add-calendar-event",
            toolResult="Added Google Calendar event tomorrow at All day: a Dungeons and Dragons session.",
            toolContext="Added Google Calendar event tomorrow at All day: a Dungeons and Dragons session.",
            verified=True,
            success=True,
            verificationSource="frontend-deterministic-command",
            recentConversation=[
                ContinuationMessage(
                    role="assistant",
                    content="STALE_BUSINESS_FOCUS_SHOULD_NOT_LEAK",
                )
            ],
            uiContext={"activePanel": "calendar", "command": "add-calendar-event"},
        )

        with patch("app.tool_continuation.active_focus_snapshot", return_value=focus):
            messages = build_tool_continuation_input(request)

        serialized = json.dumps(messages, ensure_ascii=False)
        final_context = messages[-1]["content"]
        self.assertNotIn("STALE_BUSINESS_FOCUS_SHOULD_NOT_LEAK", serialized)
        self.assertNotIn("business meeting tomorrow", final_context)
        self.assertIn('"focusContextIncluded": false', final_context)
        self.assertIn("Dungeons and Dragons", final_context)

    def test_focus_connected_calendar_create_can_keep_advisory_focus_context(self) -> None:
        focus = {
            "focusId": "focus-presentation",
            "title": "Executive presentation",
            "objective": "Present project goals to executives",
            "subject": "presentation",
            "requirements": [],
            "constraints": [],
            "preferences": [],
            "decisions": [],
            "knownFacts": [],
            "milestones": [],
            "completedMilestones": [],
            "nextAction": "Practice",
            "pendingQuestion": None,
            "status": "active",
        }
        request = ToolContinuationRequest(
            userMessage="add practice time for my presentation tomorrow at 2",
            capability="calendar",
            action="add-calendar-event",
            toolResult="Added Google Calendar event tomorrow at 2: practice time for my presentation.",
            toolContext="Added Google Calendar event tomorrow at 2: practice time for my presentation.",
            verified=True,
            success=True,
            verificationSource="frontend-deterministic-command",
            recentConversation=[
                ContinuationMessage(
                    role="assistant",
                    content="RELEVANT_PRESENTATION_HISTORY_CAN_REMAIN",
                )
            ],
            uiContext={"activePanel": "calendar", "command": "add-calendar-event"},
        )

        with patch("app.tool_continuation.active_focus_snapshot", return_value=focus):
            messages = build_tool_continuation_input(request)

        serialized = json.dumps(messages, ensure_ascii=False)
        final_context = messages[-1]["content"]
        self.assertIn("RELEVANT_PRESENTATION_HISTORY_CAN_REMAIN", serialized)
        self.assertIn('"focusContextIncluded": true', final_context)
        self.assertIn("Executive presentation", final_context)


if __name__ == "__main__":
    unittest.main()
