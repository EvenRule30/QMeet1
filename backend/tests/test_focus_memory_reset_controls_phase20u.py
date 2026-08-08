from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MEMORY_OVERLAY = ROOT / "src" / "app" / "panels" / "MemoryOverlay.tsx"
MEMORY_ROUTER = ROOT / "backend" / "app" / "routers" / "memory.py"


class FocusMemoryResetControlsPhase20UTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.overlay_source = MEMORY_OVERLAY.read_text(encoding="utf-8")
        cls.router_source = MEMORY_ROUTER.read_text(encoding="utf-8")
        cls.router_tree = ast.parse(cls.router_source)

    def _assert_retired_focus_route(
        self,
        route_path: str,
        handler_name: str,
    ) -> None:
        handler = next(
            (
                node
                for node in self.router_tree.body
                if isinstance(node, ast.AsyncFunctionDef)
                and node.name == handler_name
            ),
            None,
        )
        self.assertIsNotNone(
            handler,
            f"Expected retired Focus compatibility handler {handler_name}.",
        )
        assert isinstance(handler, ast.AsyncFunctionDef)

        route_decorators: list[ast.Call] = []
        for decorator in handler.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if not isinstance(decorator.func, ast.Attribute):
                continue
            if not isinstance(decorator.func.value, ast.Name):
                continue
            if decorator.func.value.id != "router":
                continue
            if decorator.func.attr not in {"get", "put", "post", "patch", "delete"}:
                continue
            route_decorators.append(decorator)

        self.assertTrue(
            any(
                decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and decorator.args[0].value == route_path
                for decorator in route_decorators
            ),
            f"Expected {handler_name} to own route {route_path}.",
        )

        self.assertTrue(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_retired_focus_projection_write"
                for node in ast.walk(handler)
            ),
            (
                f"Expected {handler_name} to preserve the Phase 20G "
                "retired Focus projection write quarantine."
            ),
        )

    def test_focus_history_is_presented_as_read_only(self) -> None:
        self.assertIn("Recent Focus Sessions", self.overlay_source)
        self.assertIn(
            "Focus history is read-only in Memory.",
            self.overlay_source,
        )
        self.assertRegex(
            self.overlay_source,
            re.compile(
                r"historical sessions\s+are retained for recall, resume, and audit continuity\."
            ),
        )

    def test_retired_focus_history_writes_are_not_exposed(self) -> None:
        self.assertNotIn("clearRecentFocusSessions", self.overlay_source)
        self.assertNotIn("deleteRecentFocusSessionById", self.overlay_source)
        self.assertNotIn("handleClearRecentFocusSessions", self.overlay_source)
        self.assertNotIn("handleDeleteRecentFocusSession", self.overlay_source)
        self.assertNotIn("Clear Recent Sessions", self.overlay_source)
        self.assertNotRegex(
            self.overlay_source,
            re.compile(
                r"Recent Focus Sessions[\s\S]*?onClick=\{\(\) => handleDeleteRecentFocusSession"
            ),
        )

    def test_broad_reset_controls_do_not_claim_to_clear_focus(self) -> None:
        self.assertNotIn(">\n                Clear All\n", self.overlay_source)
        self.assertNotIn(">\n                Clear Context\n", self.overlay_source)
        self.assertNotIn("onClick={onClearAllMemory}", self.overlay_source)
        self.assertNotIn("onClick={onResetRecentContextOnly}", self.overlay_source)
        self.assertIn(
            "Active Focus and Focus history are managed by the verified Focus",
            self.overlay_source,
        )
        self.assertIn(
            "lifecycle and are never cleared from this panel.",
            self.overlay_source,
        )

    def test_scoped_task_and_note_resets_are_disabled_during_focus(self) -> None:
        task_button = re.search(
            r'<button\s+className="panel-action-btn panel-action-btn-danger"'
            r"[\s\S]*?disabled=\{Boolean\(activeSession\)\}"
            r"[\s\S]*?onClick=\{onResetTasksOnly\}"
            r"[\s\S]*?>\s*Reset Tasks\s*</button>",
            self.overlay_source,
        )
        note_button = re.search(
            r'<button\s+className="panel-action-btn panel-action-btn-danger"'
            r"[\s\S]*?disabled=\{Boolean\(activeSession\)\}"
            r"[\s\S]*?onClick=\{onResetNotesOnly\}"
            r"[\s\S]*?>\s*Reset Notes\s*</button>",
            self.overlay_source,
        )
        self.assertIsNotNone(task_button)
        self.assertIsNotNone(note_button)
        self.assertIn(
            "Task and note resets are disabled while a Focus is active",
            self.overlay_source,
        )

    def test_focus_end_control_still_uses_phase20_ui_intent_bridge(self) -> None:
        self.assertIn("clearStoredActiveSession();", self.overlay_source)
        self.assertIn("dispatchActiveSessionState(null);", self.overlay_source)
        self.assertIn(
            "dispatchActiveSessionCommand({ action: 'end' });",
            self.overlay_source,
        )

    def test_backend_focus_projection_quarantine_remains_authoritative(self) -> None:
        self.assertIn("FOCUS_PROJECTION_READ_ONLY = True", self.router_source)
        self.assertIn("_RETIRED_FOCUS_WRITE_DETAIL", self.router_source)
        self.assertIn(
            '"This compatibility Focus projection write route is retired. "',
            self.router_source,
        )
        self._assert_retired_focus_route(
            "/sessions/recent/clear",
            "memory_clear_recent_focus_sessions",
        )
        self._assert_retired_focus_route(
            "/sessions/recent/{session_id}",
            "memory_delete_recent_focus_session",
        )
        self._assert_retired_focus_route(
            "/clear",
            "memory_clear_context",
        )


if __name__ == "__main__":
    unittest.main()
