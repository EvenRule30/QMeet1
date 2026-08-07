from __future__ import annotations

import unittest
from pathlib import Path


class FocusMemoryEndNativeBridgePhase20RTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.app_source = (root / "src/app/App.tsx").read_text(encoding="utf-8")
        cls.memory_overlay_source = (
            root / "src/app/panels/MemoryOverlay.tsx"
        ).read_text(encoding="utf-8")
        cls.semantic_source = (
            root / "src/app/lib/semanticFocusLifecycle.ts"
        ).read_text(encoding="utf-8")
        cls.top_status_source = (
            root / "src/app/components/TopStatusBar.tsx"
        ).read_text(encoding="utf-8")

    def test_memory_focus_end_still_emits_legacy_ui_intent_signal(self) -> None:
        self.assertIn(
            "dispatchActiveSessionCommand({ action: 'end' });",
            self.memory_overlay_source,
        )

    def test_app_bridges_legacy_end_signal_to_verified_focus_lifecycle(self) -> None:
        self.assertIn(
            "window.addEventListener(\n"
            "      'qmeet-active-session-command',",
            self.app_source,
        )
        self.assertIn("detail?.action !== 'end'", self.app_source)
        self.assertIn(
            "void handleSend('end focus anyway', 'End focus');",
            self.app_source,
        )

    def test_memory_end_closes_overlay_before_routing_visible_focus_result(self) -> None:
        handler_index = self.app_source.index(
            "const handleLegacyFocusEndRequest = (event: Event) =>"
        )
        close_index = self.app_source.index("setActivePanel('none');", handler_index)
        route_index = self.app_source.index(
            "void handleSend('end focus anyway', 'End focus');",
            close_index,
        )
        self.assertLess(close_index, route_index)

    def test_memory_end_still_uses_direct_terminal_safety_gate(self) -> None:
        route_index = self.app_source.index(
            "void handleSend('end focus anyway', 'End focus');"
        )
        direct_gate_index = self.app_source.index(
            "const directFocusTerminalCommandMatch ="
        )
        self.assertGreater(route_index, direct_gate_index)
        self.assertIn("getDirectFocusTerminalCommandMatch(trimmed)", self.app_source)

    def test_top_bar_end_is_labeled_as_chat_close_not_focus_end(self) -> None:
        self.assertIn('aria-label="Close conversation"', self.top_status_source)
        self.assertIn('Close chat', self.top_status_source)
        self.assertNotIn('aria-label="End conversation"', self.top_status_source)

    def test_end_anyway_contract_remains_available(self) -> None:
        self.assertIn("const forceEnd = /\\banyway\\b/i.test(message);", self.semantic_source)
        self.assertIn("focusSession: { forceEnd },", self.semantic_source)
        self.assertIn("command: 'end-focus-session'", self.semantic_source)


if __name__ == "__main__":
    unittest.main()
