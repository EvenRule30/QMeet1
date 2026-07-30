from __future__ import annotations

import asyncio
import json
import os
import unittest
from unittest.mock import patch

from app.focus.native_read_middleware import (
    FocusNativeReadRouteMiddleware,
    NATIVE_WRITE_CONFIRMATION_SCOPE,
    NATIVE_WRITE_ROUTE_SCOPE,
    native_command_route_payload,
    native_read_route_mode,
    native_read_route_payload,
    native_read_routes_enabled,
    native_write_route_mode,
    native_write_route_payload,
    native_write_routes_enabled,
    protected_command_route_payload,
    protected_command_routes_enabled,
)


class NativeReadRoutePayloadTests(unittest.TestCase):
    def test_current_focus_read_uses_existing_frontend_contract(self):
        payload = native_read_route_payload(
            "Could you tell me what my current focus is?"
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["intent"], "command")
        self.assertEqual(payload["action"], "read_focus_session")
        self.assertEqual(payload["frontendCommand"], "what am I focused on")
        self.assertEqual(payload["payload"], {"mode": "current"})
        self.assertEqual(payload["confidence"], 0.99)

    def test_focus_recap_preserves_timeframe(self):
        payload = native_read_route_payload(
            "Could you recap what I worked on today?"
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["action"], "recap_focus_activity")
        self.assertEqual(
            payload["payload"],
            {"mode": "recap", "timeframe": "today"},
        )

    def test_notes_tasks_and_visual_reads_are_supported(self):
        cases = [
            (
                "Could you summarize my notes?",
                "read_notes",
                {"surface": "notes"},
            ),
            (
                "Could you show me my open tasks?",
                "read_memory",
                {"surface": "tasks"},
            ),
            (
                "Could you show me my recent visual observations?",
                "read_visual_history",
                {"mode": "history"},
            ),
        ]

        for message, action, expected_payload in cases:
            with self.subTest(message=message):
                payload = native_read_route_payload(message)
                self.assertIsNotNone(payload)
                assert payload is not None
                self.assertEqual(payload["action"], action)
                self.assertEqual(payload["payload"], expected_payload)

    def test_tools_mutations_and_chat_remain_out_of_read_scope(self):
        messages = [
            "Read my calendar for today.",
            "Search for the latest Raspberry Pi kiosk guidance.",
            "Add a note that Phase 20C passed.",
            "Remember to test the native write route.",
            "Delete my last note.",
            "Mark the first task done.",
            "Start a coding focus for Phase 20C.",
            "How should I spend the next ten minutes?",
        ]

        for message in messages:
            with self.subTest(message=message):
                self.assertIsNone(native_read_route_payload(message))


class NativeMemoryWritePayloadTests(unittest.TestCase):
    def test_write_scope_lists_additive_and_confirmation_gated_actions(self):
        self.assertEqual(
            NATIVE_WRITE_ROUTE_SCOPE,
            (
                "save_note",
                "remember_task",
                "delete_last_note",
                "clear_notes",
                "delete_last_task",
                "clear_done_tasks",
                "mark_task_done",
            ),
        )
        self.assertEqual(
            NATIVE_WRITE_CONFIRMATION_SCOPE,
            (
                "delete_last_note",
                "clear_notes",
                "delete_last_task",
                "clear_done_tasks",
                "mark_task_done",
            ),
        )

    def test_save_note_uses_immediate_existing_frontend_contract(self):
        payload = native_write_route_payload(
            "Add a note that Phase 20C passed."
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["intent"], "command")
        self.assertEqual(payload["action"], "save_note")
        self.assertEqual(
            payload["frontendCommand"],
            "note that Phase 20C passed",
        )
        self.assertEqual(
            payload["payload"],
            {
                "operation": "save_note",
                "requiresConfirmation": False,
                "value": "Phase 20C passed",
            },
        )

    def test_create_task_uses_immediate_existing_frontend_contract(self):
        payload = native_write_route_payload(
            "Remember to verify the Phase 20C headers."
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["action"], "remember_task")
        self.assertEqual(
            payload["frontendCommand"],
            "remember to verify the Phase 20C headers",
        )
        self.assertEqual(
            payload["payload"],
            {
                "operation": "save_task",
                "requiresConfirmation": False,
                "value": "verify the Phase 20C headers",
            },
        )

    def test_destructive_memory_writes_preserve_confirmation_contract(self):
        cases = [
            (
                "Delete my last note.",
                "delete_last_note",
                "delete last note",
                "delete_last_note",
                "",
            ),
            (
                "Clear all my notes.",
                "clear_notes",
                "clear notes",
                "clear_notes",
                "",
            ),
            (
                "Delete my last task.",
                "delete_last_task",
                "delete last task",
                "delete_last_task",
                "",
            ),
            (
                "Clear completed tasks.",
                "clear_done_tasks",
                "clear completed tasks",
                "clear_done_tasks",
                "",
            ),
            (
                "Mark my first task complete.",
                "mark_task_done",
                "mark task my first done",
                "complete_task",
                "my first",
            ),
        ]

        for message, action, command, operation, value in cases:
            with self.subTest(message=message):
                payload = native_write_route_payload(message)
                self.assertIsNotNone(payload)
                assert payload is not None
                self.assertEqual(payload["action"], action)
                self.assertEqual(payload["frontendCommand"], command)
                self.assertEqual(payload["payload"]["operation"], operation)
                self.assertTrue(payload["payload"]["requiresConfirmation"])
                if value:
                    self.assertEqual(payload["payload"]["value"], value)
                else:
                    self.assertNotIn("value", payload["payload"])

    def test_external_and_broader_focus_writes_remain_excluded(self):
        messages = [
            "Schedule a meeting tomorrow at 3 PM called Review.",
            "Clear my visual context.",
            "Delete my last visual observation.",
            "Start a coding focus for Phase 20C.",
            "End my current focus.",
            "Search the web for Phase 20C news.",
        ]

        for message in messages:
            with self.subTest(message=message):
                self.assertIsNone(native_write_route_payload(message))


class ProtectedCommandPayloadTests(unittest.TestCase):
    def test_clear_all_my_notes_remains_a_safety_fallback(self):
        payload = protected_command_route_payload("Clear all my notes.")

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["action"], "clear_notes")
        self.assertEqual(payload["frontendCommand"], "clear notes")
        self.assertTrue(payload["payload"]["requiresConfirmation"])

    def test_start_new_focus_uses_canonical_frontend_command(self):
        payload = protected_command_route_payload(
            "Start a new focus for Phase 20C documentation."
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["action"], "start_focus_session")
        self.assertEqual(
            payload["frontendCommand"],
            "start focus for Phase 20C documentation",
        )
        self.assertEqual(
            payload["payload"],
            {
                "operation": "start_focus",
                "mode": "general",
                "title": "Phase 20C documentation",
            },
        )

    def test_questions_and_unrelated_chat_remain_excluded(self):
        messages = [
            "How do I start a new focus?",
            "Should I clear all my notes?",
            "Tell me why a new focus would help.",
            "What notes do I have?",
        ]

        for message in messages:
            with self.subTest(message=message):
                self.assertIsNone(protected_command_route_payload(message))


class NativeRouteModeTests(unittest.TestCase):
    def test_modes_default_to_shadow(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(native_read_route_mode(), "shadow")
            self.assertEqual(native_write_route_mode(), "shadow")

    def test_guarded_read_mode_requires_active_planner(self):
        with patch.dict(
            os.environ,
            {"QMEET_FOCUS_NATIVE_READ_MODE": "guarded"},
            clear=True,
        ), patch(
            "app.focus.native_read_middleware.focus_mode",
            return_value="active",
        ):
            self.assertTrue(native_read_routes_enabled())

        with patch.dict(
            os.environ,
            {"QMEET_FOCUS_NATIVE_READ_MODE": "guarded"},
            clear=True,
        ), patch(
            "app.focus.native_read_middleware.focus_mode",
            return_value="shadow",
        ):
            self.assertFalse(native_read_routes_enabled())

    def test_guarded_write_mode_requires_active_planner(self):
        for value in ("guarded", "active", "on", "enabled", "true", "1"):
            with self.subTest(value=value):
                with patch.dict(
                    os.environ,
                    {"QMEET_FOCUS_NATIVE_WRITE_MODE": value},
                    clear=True,
                ), patch(
                    "app.focus.native_read_middleware.focus_mode",
                    return_value="active",
                ):
                    self.assertEqual(native_write_route_mode(), "guarded")
                    self.assertTrue(native_write_routes_enabled())

        with patch.dict(
            os.environ,
            {"QMEET_FOCUS_NATIVE_WRITE_MODE": "guarded"},
            clear=True,
        ), patch(
            "app.focus.native_read_middleware.focus_mode",
            return_value="shadow",
        ):
            self.assertFalse(native_write_routes_enabled())

    def test_protected_commands_follow_active_guarded_route_mode(self):
        with patch.dict(
            os.environ,
            {"QMEET_FOCUS_ROUTE_MODE": "guarded"},
            clear=True,
        ), patch(
            "app.focus.native_read_middleware.focus_mode",
            return_value="active",
        ):
            self.assertTrue(protected_command_routes_enabled())

        with patch.dict(
            os.environ,
            {"QMEET_FOCUS_ROUTE_MODE": "shadow"},
            clear=True,
        ), patch(
            "app.focus.native_read_middleware.focus_mode",
            return_value="active",
        ):
            self.assertFalse(protected_command_routes_enabled())

    def test_read_and_write_rollouts_are_independent(self):
        with patch.dict(
            os.environ,
            {
                "QMEET_FOCUS_NATIVE_READ_MODE": "guarded",
                "QMEET_FOCUS_NATIVE_WRITE_MODE": "shadow",
                "QMEET_FOCUS_ROUTE_MODE": "shadow",
            },
            clear=True,
        ), patch(
            "app.focus.native_read_middleware.focus_mode",
            return_value="active",
        ):
            payload, source = native_command_route_payload(
                "Show me my open tasks."
            )
            self.assertIsNotNone(payload)
            self.assertEqual(source, "focus-native-read")

            payload, source = native_command_route_payload(
                "Delete my last note."
            )
            self.assertIsNone(payload)
            self.assertEqual(source, "")


class NativeRouteMiddlewareTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _scope() -> dict:
        return {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/command/interpret",
            "raw_path": b"/api/command/interpret",
            "query_string": b"",
            "headers": [(b"content-type", b"application/json")],
            "client": ("test", 1),
            "server": ("test", 80),
        }

    @staticmethod
    def _receive_for(body: bytes):
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": False,
                }
            await asyncio.sleep(0)
            return {"type": "http.disconnect"}

        return receive

    async def _run(self, message: str, environment: dict[str, str]):
        downstream_called = False

        async def downstream(scope, receive, send):
            nonlocal downstream_called
            downstream_called = True
            request = await receive()
            response = json.dumps(
                {
                    "intent": "chat",
                    "action": "none",
                    "bodySeen": bool(request.get("body")),
                }
            ).encode()
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(response)).encode()),
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": response,
                    "more_body": False,
                }
            )

        messages = []

        async def send(message_event):
            messages.append(message_event)

        body = json.dumps({"message": message}).encode("utf-8")
        middleware = FocusNativeReadRouteMiddleware(downstream)

        with patch.dict(os.environ, environment, clear=True), patch(
            "app.focus.native_read_middleware.focus_mode",
            return_value="active",
        ):
            await middleware(
                self._scope(),
                self._receive_for(body),
                send,
            )

        return downstream_called, messages

    async def test_guarded_destructive_write_bypasses_legacy_but_requires_confirmation(self):
        downstream_called, messages = await self._run(
            "Delete my last note.",
            {"QMEET_FOCUS_NATIVE_WRITE_MODE": "guarded"},
        )

        self.assertFalse(downstream_called)
        headers = dict(messages[0]["headers"])
        self.assertEqual(
            headers[b"x-qmeet-command-source"],
            b"focus-native-write",
        )
        response = json.loads(messages[1]["body"].decode("utf-8"))
        self.assertEqual(response["action"], "delete_last_note")
        self.assertTrue(response["payload"]["requiresConfirmation"])

    async def test_guarded_clear_all_my_notes_uses_native_write_alias(self):
        downstream_called, messages = await self._run(
            "Clear all my notes.",
            {
                "QMEET_FOCUS_NATIVE_WRITE_MODE": "guarded",
                "QMEET_FOCUS_ROUTE_MODE": "guarded",
            },
        )

        self.assertFalse(downstream_called)
        headers = dict(messages[0]["headers"])
        self.assertEqual(
            headers[b"x-qmeet-command-source"],
            b"focus-native-write",
        )
        response = json.loads(messages[1]["body"].decode("utf-8"))
        self.assertEqual(response["frontendCommand"], "clear notes")
        self.assertTrue(response["payload"]["requiresConfirmation"])

    async def test_write_shadow_keeps_clear_notes_safety_recovery(self):
        downstream_called, messages = await self._run(
            "Clear all my notes.",
            {
                "QMEET_FOCUS_NATIVE_WRITE_MODE": "shadow",
                "QMEET_FOCUS_ROUTE_MODE": "guarded",
            },
        )

        self.assertFalse(downstream_called)
        headers = dict(messages[0]["headers"])
        self.assertEqual(
            headers[b"x-qmeet-command-source"],
            b"focus-protected-command",
        )

    async def test_guarded_additive_write_stays_immediate(self):
        downstream_called, messages = await self._run(
            "Add a note that Phase 20C passed.",
            {"QMEET_FOCUS_NATIVE_WRITE_MODE": "guarded"},
        )

        self.assertFalse(downstream_called)
        response = json.loads(messages[1]["body"].decode("utf-8"))
        self.assertEqual(response["action"], "save_note")
        self.assertFalse(response["payload"]["requiresConfirmation"])

    async def test_external_write_replays_body_to_downstream_app(self):
        downstream_called, messages = await self._run(
            "Schedule a meeting tomorrow at 3 PM called Review.",
            {"QMEET_FOCUS_NATIVE_WRITE_MODE": "guarded"},
        )

        self.assertTrue(downstream_called)
        response = json.loads(messages[1]["body"].decode("utf-8"))
        self.assertTrue(response["bodySeen"])

    async def test_start_new_focus_stays_on_protected_canonical_path(self):
        downstream_called, messages = await self._run(
            "Start a new focus for Phase 20C documentation.",
            {"QMEET_FOCUS_ROUTE_MODE": "guarded"},
        )

        self.assertFalse(downstream_called)
        headers = dict(messages[0]["headers"])
        self.assertEqual(
            headers[b"x-qmeet-command-source"],
            b"focus-protected-command",
        )
        response = json.loads(messages[1]["body"].decode("utf-8"))
        self.assertEqual(response["action"], "start_focus_session")

    async def test_shadow_write_mode_preserves_downstream_for_standard_mutation(self):
        downstream_called, messages = await self._run(
            "Delete my last note.",
            {
                "QMEET_FOCUS_NATIVE_WRITE_MODE": "shadow",
                "QMEET_FOCUS_ROUTE_MODE": "shadow",
            },
        )

        self.assertTrue(downstream_called)
        response = json.loads(messages[1]["body"].decode("utf-8"))
        self.assertTrue(response["bodySeen"])


class NativeMiddlewareOrderingTests(unittest.TestCase):
    def test_focus_guard_remains_outside_native_router(self):
        from app.main import app

        names = [item.cls.__name__ for item in app.user_middleware]
        self.assertIn("FocusShadowMiddleware", names)
        self.assertIn("FocusNativeReadRouteMiddleware", names)
        self.assertLess(
            names.index("FocusShadowMiddleware"),
            names.index("FocusNativeReadRouteMiddleware"),
        )


if __name__ == "__main__":
    unittest.main()
