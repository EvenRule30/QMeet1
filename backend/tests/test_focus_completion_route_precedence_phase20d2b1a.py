from __future__ import annotations

import re
import unittest
from pathlib import Path


class FocusCompletionRoutePrecedenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.source = (root / "src/app/lib/semanticFocusLifecycle.ts").read_text(
            encoding="utf-8"
        )

    def _function_body(self, name: str) -> str:
        match = re.search(
            rf"(?:export\s+)?function\s+{re.escape(name)}\s*\(.*?\)\s*:\s*[^{{]+\{{(?P<body>.*?)\n\}}",
            self.source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match, f"{name} must remain declared")
        assert match is not None
        return match.group("body")

    def test_task_completion_is_deferred_only_for_focus_terminal_language(self) -> None:
        helper = self._function_body(
            "shouldRouteExactFocusLifecycleThroughSemanticPreflight"
        )
        self.assertIn("commandMatch?.command === 'mark-task-done'", helper)
        self.assertRegex(
            helper,
            r"looksLikeFocusTerminalLanguage\(\s*originalMessage\s*\)",
        )
        self.assertNotRegex(
            helper,
            r"commandMatch\?\.command === 'mark-task-done'\s*\|\|",
            "ordinary task completion must not be deferred unconditionally",
        )

    def test_terminal_guard_requires_both_focus_reference_and_terminal_language(self) -> None:
        detector = self._function_body("looksLikeFocusTerminalLanguage")
        self.assertIn("const focusTarget", detector)
        self.assertIn("const directFocusTerminalPattern", detector)
        self.assertIn("return directFocusTerminalPattern.test(text);", detector)
        self.assertIn(r"focus(?:\s+session)?|session|work", detector)
        self.assertRegex(detector, r"finish\|finished")
        self.assertRegex(detector, r"complete\|completed")
        self.assertIn("focusTarget && terminalLanguage", detector)


if __name__ == "__main__":
    unittest.main()
