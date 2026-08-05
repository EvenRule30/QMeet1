from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = REPO_ROOT / "src" / "app" / "App.tsx"
BRIDGE_PATH = REPO_ROOT / "src" / "app" / "lib" / "semanticFocusLifecycle.ts"


class FocusCompletionRoutePrecedenceTests(unittest.TestCase):
    def test_app_supplies_original_user_language_to_precedence_guard(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "shouldRouteExactFocusLifecycleThroughSemanticPreflight(\n"
            "        parsedCommandMatch,\n"
            "        trimmed,\n"
            "      )",
            app,
        )

    def test_task_completion_is_deferred_only_for_focus_terminal_language(self) -> None:
        bridge = BRIDGE_PATH.read_text(encoding="utf-8")
        helper_match = re.search(
            r"export function shouldRouteExactFocusLifecycleThroughSemanticPreflight\([\s\S]+?\n}\n",
            bridge,
        )
        self.assertIsNotNone(helper_match)
        helper = helper_match.group(0) if helper_match else ""

        self.assertIn("commandMatch?.command === 'mark-task-done'", helper)
        self.assertIn("looksLikeFocusTerminalLanguage(originalMessage)", helper)
        self.assertNotIn("commandMatch?.command === 'delete-last-task'", helper)
        self.assertNotIn("commandMatch?.command === 'clear-done-tasks'", helper)

    def test_terminal_guard_requires_both_focus_reference_and_terminal_language(self) -> None:
        bridge = BRIDGE_PATH.read_text(encoding="utf-8")
        detector_match = re.search(
            r"function looksLikeFocusTerminalLanguage\(message: string\): boolean \{[\s\S]+?\n}\n",
            bridge,
        )
        self.assertIsNotNone(detector_match)
        detector = detector_match.group(0) if detector_match else ""

        self.assertIn("const focusTarget", detector)
        self.assertIn("const directFocusTerminalPattern", detector)
        self.assertIn("return directFocusTerminalPattern.test(text);", detector)
        self.assertIn("focus(?:\\s+session)?|session|work", detector)
        self.assertRegex(detector, r"finish\|finished")
        self.assertRegex(detector, r"complete\|completed")
        self.assertRegex(detector, r"done")

    def test_verified_recursive_command_still_bypasses_preflight(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        self.assertIn("!forcedCommandMatch &&", app)


if __name__ == "__main__":
    unittest.main()
