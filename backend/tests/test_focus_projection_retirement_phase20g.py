from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.routers import memory as memory_router


REPO_ROOT = Path(__file__).resolve().parents[2]
CALENDAR_SOURCE = REPO_ROOT / "src" / "app" / "hooks" / "useCalendarController.ts"
MEMORY_ROUTER_SOURCE = REPO_ROOT / "backend" / "app" / "routers" / "memory.py"
MEMORY_WRAPPER_SOURCE = REPO_ROOT / "src" / "app" / "commandHandlers" / "memory.ts"


class _Request(SimpleNamespace):
    model_fields_set: set[str]


class FocusProjectionRetirementPhase20GTests(unittest.TestCase):
    maxDiff = None

    def test_calendar_hook_has_no_browser_owned_focus_prep_writer(self):
        source = CALENDAR_SOURCE.read_text(encoding="utf-8")
        for marker in (
            "replaceActiveSession",
            "replaceMemoryTasks",
            "qmeet-calendar-focus-prep-command",
            "prepareFocusFromNextCalendarEvent",
            "createCalendarFocusSession",
            "applyCalendarFocusSession",
            "ACTIVE_SESSION_STORAGE_KEY",
            "MEMORY_TASKS_STORAGE_KEY",
        ):
            self.assertNotIn(marker, source)
        self.assertIn("export function useCalendarController", source)
        self.assertIn("handleResetGoogleCalendarAuth", source)

    def test_memory_router_declares_projection_read_only_and_retires_direct_writes(self):
        source = MEMORY_ROUTER_SOURCE.read_text(encoding="utf-8")
        self.assertIn("FOCUS_PROJECTION_READ_ONLY = True", source)
        self.assertIn("def _preserve_focus_projection()", source)
        self.assertIn("status_code=409", source)
        self.assertGreaterEqual(source.count("_retired_focus_projection_write()"), 8)
        for mutation in (
            "**replace_active_session(",
            "**update_active_session(",
            "**clear_active_session(",
            "**replace_recent_focus_sessions(",
            "**clear_recent_focus_sessions(",
            "**delete_recent_focus_session(",
        ):
            self.assertNotIn(mutation, source)

    def test_generic_context_write_preserves_backend_focus_projection(self):
        request = _Request(
            tasks=[],
            recentActions=[],
            notes=[],
            activeSession={"id": "browser-owned"},
            recentFocusSessions=[{"id": "browser-history"}],
            visualContext=None,
            model_fields_set={
                "tasks",
                "recentActions",
                "notes",
                "activeSession",
                "recentFocusSessions",
            },
        )
        captured: dict[str, object] = {}

        def fake_replace_memory_context(**kwargs):
            captured.update(kwargs)
            return kwargs

        with (
            patch.object(
                memory_router,
                "get_memory_context",
                return_value={
                    "activeSession": {"id": "backend-focus"},
                    "recentFocusSessions": [{"id": "backend-history"}],
                },
            ),
            patch.object(
                memory_router,
                "replace_memory_context",
                side_effect=fake_replace_memory_context,
            ),
            patch.object(memory_router, "MemoryContextResponse", side_effect=lambda **kw: kw),
        ):
            asyncio.run(memory_router.memory_replace_context(request))

        self.assertEqual(captured["active_session"], {"id": "backend-focus"})
        self.assertEqual(
            captured["recent_focus_sessions"],
            [{"id": "backend-history"}],
        )
        self.assertNotEqual(captured["active_session"], request.activeSession)

    def test_memory_import_preserves_backend_focus_projection(self):
        request = _Request(
            tasks=[],
            recentActions=[],
            notes=[],
            activeSession={"id": "imported-browser-focus"},
            recentFocusSessions=[{"id": "imported-browser-history"}],
            visualContext=None,
            model_fields_set=set(),
        )
        captured: dict[str, object] = {}

        def fake_import_memory_context(**kwargs):
            captured.update(kwargs)
            return kwargs

        with (
            patch.object(
                memory_router,
                "get_memory_context",
                return_value={
                    "activeSession": {"id": "backend-focus"},
                    "recentFocusSessions": [{"id": "backend-history"}],
                },
            ),
            patch.object(
                memory_router,
                "import_memory_context",
                side_effect=fake_import_memory_context,
            ),
            patch.object(memory_router, "MemoryContextResponse", side_effect=lambda **kw: kw),
        ):
            asyncio.run(memory_router.memory_import_context(request))

        self.assertEqual(captured["active_session"], {"id": "backend-focus"})
        self.assertEqual(
            captured["recent_focus_sessions"],
            [{"id": "backend-history"}],
        )

    def test_direct_legacy_projection_write_routes_return_conflict(self):
        async_calls = (
            memory_router.memory_clear_context,
            lambda: memory_router.memory_replace_active_session(_Request()),
            lambda: memory_router.memory_update_active_session(_Request()),
            memory_router.memory_clear_active_session,
            lambda: memory_router.memory_replace_recent_focus_sessions(_Request()),
            memory_router.memory_clear_recent_focus_sessions,
            lambda: memory_router.memory_delete_recent_focus_session("focus-old"),
        )
        for call in async_calls:
            with self.subTest(call=call), self.assertRaises(HTTPException) as raised:
                asyncio.run(call())
            self.assertEqual(raised.exception.status_code, 409)
            self.assertIn("verified native operations", str(raised.exception.detail))

    def test_wrapper_declares_phase20i_and_keeps_native_handlers_before_quarantine(self):
        source = MEMORY_WRAPPER_SOURCE.read_text(encoding="utf-8")
        self.assertIn(
            "NATIVE_FOCUS_LIFECYCLE_OWNERSHIP_VERSION = 'phase20i'",
            source,
        )
        calendar_handler = source.index(
            "if (commandMatch.command === 'prepare-calendar-focus')"
        )
        context_executor = source.index("addNativeFocusContextVerified")
        quarantine = source.index(
            "RETIRED_LEGACY_FOCUS_OWNERSHIP_COMMANDS.has(commandMatch.command)"
        )
        fallback = source.rindex("return handleMemoryCommandCore(commandMatch, deps)")
        self.assertLess(calendar_handler, quarantine)
        self.assertLess(context_executor, quarantine)
        self.assertLess(quarantine, fallback)
        self.assertIn(
            "confirmationContent: result.message",
            source[calendar_handler:quarantine],
        )


if __name__ == "__main__":
    unittest.main()
