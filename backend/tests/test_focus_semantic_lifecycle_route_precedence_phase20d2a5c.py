from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = REPO_ROOT / "src" / "app" / "App.tsx"
BRIDGE_PATH = REPO_ROOT / "src" / "app" / "lib" / "semanticFocusLifecycle.ts"


class SemanticLifecycleRoutePrecedenceTests(unittest.TestCase):
    def test_exact_focus_lifecycle_commands_are_deferred_to_semantic_preflight(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")

        self.assertIn(
            "shouldRouteExactFocusLifecycleThroughSemanticPreflight(parsedCommandMatch)",
            app,
        )
        self.assertIn(
            "const commandMatch = deferredExactFocusLifecycleMatch\n      ? null\n      : parsedCommandMatch;",
            app,
        )

        parse_position = app.index(
            "const parsedCommandMatch = forcedCommandMatch ?? parseCommand(trimmed);"
        )
        defer_position = app.index("const deferredExactFocusLifecycleMatch =")
        execute_position = app.index("if (commandMatch) {", defer_position)
        semantic_position = app.index(
            "const semanticFocusLifecycle = await interpretSemanticFocusLifecycle(trimmed);"
        )

        self.assertLess(parse_position, defer_position)
        self.assertLess(defer_position, execute_position)
        self.assertLess(execute_position, semantic_position)

    def test_only_start_and_update_are_deferred(self) -> None:
        bridge = BRIDGE_PATH.read_text(encoding="utf-8")
        helper_match = re.search(
            r"export function shouldRouteExactFocusLifecycleThroughSemanticPreflight\([\s\S]+?\n}\n",
            bridge,
        )
        self.assertIsNotNone(helper_match)
        helper = helper_match.group(0) if helper_match else ""

        self.assertIn("commandMatch?.command === 'start-focus-session'", helper)
        self.assertIn("commandMatch?.command === 'update-focus-session'", helper)
        self.assertNotIn("open-memory", helper)
        self.assertNotIn("show-status", helper)

    def test_semantic_mismatch_blocks_before_general_interpreter(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        mismatch_position = app.index("if (deferredExactFocusLifecycleMatch) {")
        interpreter_position = app.index(
            "const interpretedCommand = await interpretCommandIntent(trimmed);"
        )

        self.assertLess(mismatch_position, interpreter_position)
        self.assertIn(
            "I detected a possible Focus change, but I could not safely determine whether to update the current Focus or start a new one.",
            app,
        )

    def test_forced_verified_command_does_not_loop_back_into_preflight(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        self.assertIn("!forcedCommandMatch &&", app)
        self.assertIn(
            "semanticFocusLifecycle.commandMatch,",
            app,
        )


if __name__ == "__main__":
    unittest.main()
