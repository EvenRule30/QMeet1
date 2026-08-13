from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import agent
from app.tool_continuation import ToolContinuationRequest, stream_tool_continuation


class _FakeStream:
    def __init__(self, events):
        self._events = list(events)

    def __aiter__(self):
        self._iterator = iter(self._events)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeResponses:
    def __init__(self, events):
        self._events = events

    async def create(self, **_kwargs):
        return _FakeStream(self._events)


class _FakeClient:
    def __init__(self, events):
        self.responses = _FakeResponses(events)


class ToolContinuationStreamIntegrityPhase21BTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        agent.reset_conversation()

    def tearDown(self) -> None:
        agent.reset_conversation()

    def _request(self) -> ToolContinuationRequest:
        return ToolContinuationRequest(
            userMessage="search for Framework Laptop reviews",
            capability="search",
            action="run-search",
            toolResult="Search complete. 4 sources added.",
            toolContext='{"summary":"Verified Framework review summary."}',
            verified=True,
            success=True,
            verificationSource="phase21b-stream-integrity-test",
            recentConversation=[],
            uiContext={"activePanel": "search", "command": "run-search"},
        )

    async def _collect_with_events(self, events):
        config = SimpleNamespace(
            provider="openai",
            model="test-model",
            max_output_tokens=500,
        )
        with (
            patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False),
            patch("app.tool_continuation.get_agent_config", return_value=config),
            patch(
                "app.tool_continuation.AsyncOpenAI",
                return_value=_FakeClient(events),
            ),
        ):
            return [chunk async for chunk in stream_tool_continuation(self._request())]

    async def test_response_incomplete_is_not_accepted_as_finished_reply(self) -> None:
        events = [
            SimpleNamespace(
                type="response.output_text.delta",
                delta="The Framework Laptop is well-regarded, but its",
            ),
            SimpleNamespace(
                type="response.incomplete",
                response=SimpleNamespace(
                    incomplete_details=SimpleNamespace(reason="max_output_tokens")
                ),
            ),
        ]

        with self.assertRaises(agent.AgentUserFacingError) as caught:
            await self._collect_with_events(events)

        self.assertIn("stopped before completing", str(caught.exception))
        self.assertEqual(agent.MESSAGE_HISTORY, [])

    async def test_stream_ending_without_completed_event_is_rejected(self) -> None:
        events = [
            SimpleNamespace(
                type="response.output_text.delta",
                delta="Partial continuation text",
            )
        ]

        with self.assertRaises(agent.AgentUserFacingError) as caught:
            await self._collect_with_events(events)

        self.assertIn("stream ended before", str(caught.exception))
        self.assertEqual(agent.MESSAGE_HISTORY, [])

    async def test_completed_stream_is_still_recorded_normally(self) -> None:
        events = [
            SimpleNamespace(
                type="response.output_text.delta",
                delta="Complete Framework review summary.",
            ),
            SimpleNamespace(type="response.completed"),
        ]

        chunks = await self._collect_with_events(events)

        self.assertEqual("".join(chunks), "Complete Framework review summary.")
        self.assertEqual(agent.MESSAGE_HISTORY[-1]["role"], "assistant")
        self.assertEqual(
            agent.MESSAGE_HISTORY[-1]["content"],
            "Complete Framework review summary.",
        )

    def test_frontend_removes_partial_continuation_after_stream_error(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = (root / "src/app/lib/toolContinuation.ts").read_text(
            encoding="utf-8"
        )

        self.assertIn("function removeContinuationMessage(", source)
        self.assertIn(
            "previous.filter((message) => message.id !== messageId)",
            source,
        )
        self.assertIn("if (visibleChunkSeen) {", source)
        self.assertIn(
            "removeContinuationMessage(options.setMessages, messageId);",
            source,
        )

    def test_backend_requires_response_completed_terminal_event(self) -> None:
        root = Path(__file__).resolve().parents[2]
        source = (root / "backend/app/tool_continuation.py").read_text(
            encoding="utf-8"
        )

        self.assertIn('elif event.type == "response.incomplete":', source)
        self.assertIn('elif event.type == "error":', source)
        self.assertIn("completed = False", source)
        self.assertIn("completed = True", source)
        self.assertIn("if not completed:", source)


if __name__ == "__main__":
    unittest.main()
