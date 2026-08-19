from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import qmeet_orchestrator


ROOT = Path(__file__).resolve().parents[2]


class _FakeCompletions:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    async def create(self, **_: object) -> SimpleNamespace:
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=json.dumps(self._payload))
                )
            ]
        )


class _FakeAsyncOpenAI:
    payload: dict = {}

    def __init__(self, **_: object) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(self.payload))


class CalendarWriteHandoffPhase21BTests(unittest.TestCase):
    def _run_orchestrator(self, message: str, *, client_context: dict | None = None):
        return asyncio.run(
            qmeet_orchestrator.interpret_qmeet_orchestrator(
                message,
                ui_state={},
                client_context=client_context or {},
            )
        )

    def test_orchestrator_chat_without_local_fallback_defers_downstream(self) -> None:
        _FakeAsyncOpenAI.payload = {
            "intent": "chat",
            "action": "none",
            "confidence": 0.94,
            "frontendCommand": "",
            "payload": {},
            "reason": "Calendar creation is not in this orchestrator's action list.",
        }
        with patch.object(qmeet_orchestrator, "AsyncOpenAI", _FakeAsyncOpenAI), patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "phase21b-test-key",
            },
            clear=False,
        ):
            result = self._run_orchestrator(
                "schedule a Dungeons and Dragons session tomorrow"
            )

        self.assertIsNone(result)

    def test_orchestrator_still_returns_positive_command_decision(self) -> None:
        _FakeAsyncOpenAI.payload = {
            "intent": "command",
            "action": "open_calendar",
            "confidence": 0.95,
            "frontendCommand": "open calendar",
            "payload": {},
            "reason": "The user asked to open Calendar.",
        }
        with patch.object(qmeet_orchestrator, "AsyncOpenAI", _FakeAsyncOpenAI), patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "phase21b-test-key",
            },
            clear=False,
        ):
            result = self._run_orchestrator("bring up the calendar for me")

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["intent"], "command")
        self.assertEqual(result["frontendCommand"], "open calendar")

    def test_high_confidence_focus_chat_fallback_remains_terminal(self) -> None:
        class _FailIfCalled:
            def __init__(self, **_: object) -> None:
                raise AssertionError("model should not be called for protected Focus chat")

        client_context = {
            "memoryState": {
                "activeSession": {
                    "id": "focus-1",
                    "title": "Finish the project report",
                }
            }
        }
        with patch.object(qmeet_orchestrator, "AsyncOpenAI", _FailIfCalled), patch.dict(
            "os.environ",
            {
                "LLM_PROVIDER": "openai",
                "OPENAI_API_KEY": "phase21b-test-key",
            },
            clear=False,
        ):
            result = self._run_orchestrator(
                "what should I do next?",
                client_context=client_context,
            )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["intent"], "chat")
        self.assertGreaterEqual(result["confidence"], 0.85)

    def test_calendar_create_targeted_delete_and_targeted_edit_are_promoted_but_broad_writes_remain_deferred(self) -> None:
        source = (ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("resolvePromotedCalendarCreateToolCommand", source)
        self.assertIn("command: 'add-calendar-event'", source)
        self.assertIn("resolvePromotedCalendarDeleteToolCommand", source)
        self.assertIn("command: 'delete-calendar-event'", source)
        self.assertIn("resolvePromotedCalendarEditToolCommand", source)
        self.assertIn("command: 'edit-last-event'", source)
        self.assertIn("resolveDeferredCalendarWriteAction", source)
        self.assertIn("const DEFERRED_CALENDAR_WRITE_ACTIONS", source)
        self.assertIn("'delete-last-event'", source)
        self.assertIn("'clear-calendar'", source)
        self.assertNotIn("command: 'delete-last-event'", source)
        self.assertNotIn("command: 'clear-calendar'", source)

    def test_app_requires_legacy_interpreter_to_match_agent_calendar_write_action(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")

        self.assertIn("resolveDeferredCalendarWriteAction(promotedSingleIntent)", source)
        self.assertIn("parseVerifiedCalendarWriteAction", source)
        self.assertIn(
            "interpretedCalendarWriteAction !== deferredCalendarWriteAction",
            source,
        )
        self.assertIn("Calendar write not safely resolved", source)
        self.assertIn("Calendar unchanged", source)
        self.assertIn("No calendar change was made.", source)

    def test_shadow_calendar_writes_use_canonical_mutation_ids_only(self) -> None:
        source = (ROOT / "backend" / "app" / "qmeet_agent_shadow.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('return "add-calendar-event"', source)
        self.assertIn('return "edit-last-event"', source)
        self.assertIn('return "delete-calendar-event"', source)
        self.assertIn(
            "Calendar CREATE is promoted",
            source,
        )
        self.assertIn(
            "Calendar TARGETED EDIT is promoted",
            source,
        )
        self.assertIn(
            "Calendar delete-last and clear operations are NOT agent-executable yet",
            source,
        )
        self.assertNotIn('action="calendar.create_event"', source)

    def test_failed_calendar_write_interpretation_cannot_fall_into_normal_chat(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
        guard_index = source.index("if (deferredCalendarWriteAction) {")
        normal_chat_index = source.index("setTrackedInputRoute('Normal chat');")
        send_chat_index = source.rindex("await sendNormalChat(")

        self.assertLess(guard_index, normal_chat_index)
        self.assertLess(normal_chat_index, send_chat_index)
        self.assertIn(
            "The unified agent identified a Calendar write, but the legacy interpreter did not return one executable Calendar mutation.",
            source,
        )


if __name__ == "__main__":
    unittest.main()
