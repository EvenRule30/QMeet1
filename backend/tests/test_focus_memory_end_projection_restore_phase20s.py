from __future__ import annotations

import unittest
from pathlib import Path


class FocusMemoryEndProjectionRestorePhase20STests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.app_source = (root / "src/app/App.tsx").read_text(encoding="utf-8")

    def test_bridge_can_restore_verified_projection_before_end_routing(self) -> None:
        self.assertIn(
            "import { applyVerifiedFocusProjection } from './lib/nativeFocusLifecycle';",
            self.app_source,
        )
        self.assertIn("if (activeSession) {", self.app_source)
        self.assertIn("applyVerifiedFocusProjection(activeSession);", self.app_source)

    def test_projection_restore_happens_before_visible_end_route(self) -> None:
        handler_index = self.app_source.index(
            "const handleLegacyFocusEndRequest = (event: Event) =>"
        )
        restore_index = self.app_source.index(
            "applyVerifiedFocusProjection(activeSession);",
            handler_index,
        )
        close_index = self.app_source.index("setActivePanel('none');", restore_index)
        route_index = self.app_source.index(
            "void handleSend('end focus anyway', 'End focus');",
            close_index,
        )
        self.assertLess(restore_index, close_index)
        self.assertLess(close_index, route_index)

    def test_bridge_keeps_active_session_in_effect_dependencies(self) -> None:
        self.assertIn("}, [activeSession, handleSend]);", self.app_source)

    def test_memory_button_uses_explicit_force_end_intent(self) -> None:
        handler_index = self.app_source.index(
            "const handleLegacyFocusEndRequest = (event: Event) =>"
        )
        handler_end = self.app_source.index("};", handler_index)
        handler_block = self.app_source[handler_index:handler_end]
        self.assertIn("end focus anyway", handler_block.casefold())
        self.assertIn("void handleSend", handler_block)

    def test_button_force_end_is_scoped_to_legacy_memory_end_bridge(self) -> None:
        self.assertIn(
            "void handleSend('end focus anyway', 'End focus');",
            self.app_source,
        )
        self.assertIn(
            "const directFocusTerminalCommandMatch =",
            self.app_source,
        )
        self.assertIn("getDirectFocusTerminalCommandMatch(trimmed)", self.app_source)


if __name__ == "__main__":
    unittest.main()
