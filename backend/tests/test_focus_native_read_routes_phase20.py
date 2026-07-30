from __future__ import annotations

import asyncio
import json
import os
import unittest
from unittest.mock import patch

from app.focus.native_read_middleware import (
    FocusNativeReadRouteMiddleware,
    native_read_route_mode,
    native_read_route_payload,
    native_read_routes_enabled,
)


class NativeReadRoutePayloadTests(unittest.TestCase):
    def test_current_focus_read_uses_existing_frontend_contract(self):
        payload = native_read_route_payload("Could you tell me what my current focus is?")

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["intent"], "command")
        self.assertEqual(payload["action"], "read_focus_session")
        self.assertEqual(payload["frontendCommand"], "what am I focused on")
        self.assertEqual(payload["payload"], {"mode": "current"})
        self.assertEqual(payload["confidence"], 0.99)

    def test_focus_recap_preserves_timeframe(self):
        payload = native_read_route_payload("Could you recap what I worked on today?")

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["action"], "recap_focus_activity")
        self.assertEqual(
            payload["payload"],
            {"mode": "recap", "timeframe": "today"},
        )

    def test_notes_tasks_and_visual_reads_are_supported(self):
        cases = [
            ("Could you summarize my notes?", "read_notes", {"surface": "notes"}),
            ("Could you show me my open tasks?", "read_memory", {"surface": "tasks"}),
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

    def test_tools_mutations_and_chat_remain_out_of_scope(self):
        messages = [
            "Read my calendar for today.",
            "Search for the latest Raspberry Pi kiosk guidance.",
            "Delete my last note.",
            "Mark the first task done.",
            "Start a coding focus for Phase 20.",
            "How should I spend the next ten minutes?",
        ]

        for message in messages:
            with self.subTest(message=message):
                self.assertIsNone(native_read_route_payload(message))


class NativeReadRouteModeTests(unittest.TestCase):
    def test_mode_defaults_to_shadow(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(native_read_route_mode(), "shadow")

    def test_guarded_aliases_enable_only_with_active_planner(self):
        for value in ("guarded", "active", "on", "enabled", "true", "1"):
            with self.subTest(value=value):
                with patch.dict(
                    os.environ,
                    {"QMEET_FOCUS_NATIVE_READ_MODE": value},
                    clear=True,
                ), patch(
                    "app.focus.native_read_middleware.focus_mode",
                    return_value="active",
                ):
                    self.assertEqual(native_read_route_mode(), "guarded")
                    self.assertTrue(native_read_routes_enabled())

    def test_guarded_native_mode_does_not_enable_in_shadow_planner_mode(self):
        with patch.dict(
            os.environ,
            {"QMEET_FOCUS_NATIVE_READ_MODE": "guarded"},
            clear=True,
        ), patch(
            "app.focus.native_read_middleware.focus_mode",
            return_value="shadow",
        ):
            self.assertFalse(native_read_routes_enabled())


class NativeReadRouteMiddlewareTests(unittest.IsolatedAsyncioTestCase):
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

    async def test_guarded_read_bypasses_downstream_command_app(self):
        downstream_called = False

        async def downstream(scope, receive, send):
            nonlocal downstream_called
            downstream_called = True
            raise AssertionError("The legacy command app should be bypassed.")

        messages = []

        async def send(message):
            messages.append(message)

        body = json.dumps(
            {"message": "Could you show me my open tasks?"}
        ).encode("utf-8")
        middleware = FocusNativeReadRouteMiddleware(downstream)

        with patch.dict(
            os.environ,
            {"QMEET_FOCUS_NATIVE_READ_MODE": "guarded"},
            clear=True,
        ), patch(
            "app.focus.native_read_middleware.focus_mode",
            return_value="active",
        ):
            await middleware(
                self._scope(),
                self._receive_for(body),
                send,
            )

        self.assertFalse(downstream_called)
        self.assertEqual(messages[0]["status"], 200)
        headers = dict(messages[0]["headers"])
        self.assertEqual(
            headers[b"x-qmeet-command-source"],
            b"focus-native-read",
        )
        response = json.loads(messages[1]["body"].decode("utf-8"))
        self.assertEqual(response["action"], "read_memory")

    async def test_unrecognized_message_replays_body_to_legacy_app(self):
        downstream_body = b""

        async def downstream(scope, receive, send):
            nonlocal downstream_body
            request = await receive()
            downstream_body = request.get("body", b"")
            response = json.dumps({"intent": "chat", "action": "none"}).encode()
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

        async def send(message):
            messages.append(message)

        body = json.dumps(
            {"message": "How should I spend the next ten minutes?"}
        ).encode("utf-8")
        middleware = FocusNativeReadRouteMiddleware(downstream)

        with patch.dict(
            os.environ,
            {"QMEET_FOCUS_NATIVE_READ_MODE": "guarded"},
            clear=True,
        ), patch(
            "app.focus.native_read_middleware.focus_mode",
            return_value="active",
        ):
            await middleware(
                self._scope(),
                self._receive_for(body),
                send,
            )

        self.assertEqual(downstream_body, body)
        self.assertEqual(messages[0]["status"], 200)

    async def test_shadow_native_mode_preserves_legacy_path(self):
        downstream_called = False

        async def downstream(scope, receive, send):
            nonlocal downstream_called
            downstream_called = True
            request = await receive()
            self.assertTrue(request.get("body"))
            response = b"{}"
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-length", b"2")],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": response,
                    "more_body": False,
                }
            )

        middleware = FocusNativeReadRouteMiddleware(downstream)
        body = json.dumps({"message": "Show my open tasks."}).encode()

        with patch.dict(
            os.environ,
            {"QMEET_FOCUS_NATIVE_READ_MODE": "shadow"},
            clear=True,
        ), patch(
            "app.focus.native_read_middleware.focus_mode",
            return_value="active",
        ):
            await middleware(
                self._scope(),
                self._receive_for(body),
                lambda message: asyncio.sleep(0),
            )

        self.assertTrue(downstream_called)


class NativeReadMiddlewareOrderingTests(unittest.TestCase):
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
