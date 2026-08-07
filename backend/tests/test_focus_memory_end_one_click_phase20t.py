from __future__ import annotations

import unittest
from pathlib import Path


class FocusMemoryEndOneClickPhase20TTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.app_source = (root / "src/app/App.tsx").read_text(encoding="utf-8")
        cls.memory_source = (
            root / "src/app/commandHandlers/memory.ts"
        ).read_text(encoding="utf-8")
        cls.semantic_source = (
            root / "src/app/lib/semanticFocusLifecycle.ts"
        ).read_text(encoding="utf-8")

    def test_memory_end_button_routes_as_explicit_anyway_intent(self) -> None:
        self.assertIn(
            "void handleSend('end focus anyway', 'End focus');",
            self.app_source,
        )

    def test_chat_end_guard_remains_in_native_handler(self) -> None:
        self.assertIn("if (!forceEnd && shouldGuardNativeFocusEnd(activeSession))", self.memory_source)
        self.assertIn(
            'say "end Focus anyway" to end it without saving',
            self.memory_source,
        )

    def test_anyway_language_sets_force_end(self) -> None:
        self.assertIn("const forceEnd = /\\banyway\\b/i.test(message);", self.semantic_source)
        self.assertIn("focusSession: { forceEnd },", self.semantic_source)

    def test_button_end_still_routes_through_verified_native_end(self) -> None:
        self.assertIn("const directFocusTerminalCommandMatch =", self.app_source)
        self.assertIn("getDirectFocusTerminalCommandMatch(trimmed)", self.app_source)
        self.assertIn("endNativeFocusVerified({", self.memory_source)
        self.assertIn("applyVerifiedFocusProjection(null);", self.memory_source)

    def test_memory_end_bridge_still_restores_projection_first(self) -> None:
        handler_index = self.app_source.index(
            "const handleLegacyFocusEndRequest = (event: Event) =>"
        )
        restore_index = self.app_source.index(
            "applyVerifiedFocusProjection(activeSession);",
            handler_index,
        )
        route_index = self.app_source.index(
            "void handleSend('end focus anyway', 'End focus');",
            restore_index,
        )
        self.assertLess(restore_index, route_index)


if __name__ == "__main__":
    unittest.main()
