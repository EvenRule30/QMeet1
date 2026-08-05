from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_PATH = REPO_ROOT / "src" / "app" / "App.tsx"
BRIDGE_PATH = REPO_ROOT / "src" / "app" / "lib" / "semanticFocusLifecycle.ts"


class FocusTerminalSafetyGateTests(unittest.TestCase):
    def test_bridge_exposes_direct_terminal_gate(self) -> None:
        bridge = BRIDGE_PATH.read_text(encoding="utf-8")
        helper_match = re.search(
            r"export function getDirectFocusTerminalCommandMatch\([\s\S]+?\n}\n\nfunction looksLikeFocusTerminalLanguage",
            bridge,
        )
        self.assertIsNotNone(helper_match)
        helper = helper_match.group(0) if helper_match else ""
        self.assertIn("command: 'end-focus-session'", helper)
        self.assertIn("disposition === 'completed'", helper)
        self.assertIn("forceEnd:", helper)
        self.assertIn("summary|recap|note", helper)
        self.assertIn("don't|do not|never|cancel", helper)

    def test_app_routes_direct_terminal_match_as_forced_verified_command(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        gate_position = app.index("const directFocusTerminalCommandMatch =")
        recursive_position = app.index(
            "directFocusTerminalCommandMatch,",
            gate_position,
        )
        parse_position = app.index(
            "const parsedCommandMatch = forcedCommandMatch ?? parseCommand(trimmed);"
        )
        self.assertLess(gate_position, recursive_position)
        self.assertLess(recursive_position, parse_position)
        self.assertIn("'apply verified focus terminal transition'", app)

    def test_general_task_parser_remains_after_terminal_gate(self) -> None:
        app = APP_PATH.read_text(encoding="utf-8")
        gate_position = app.index("const directFocusTerminalCommandMatch =")
        destructive_position = app.index(
            "isDestructiveLocalCommand(commandMatch.command)",
        )
        fuzzy_position = app.index(
            "const interpretedCommand = await interpretCommandIntent(trimmed);"
        )
        self.assertLess(gate_position, destructive_position)
        self.assertLess(gate_position, fuzzy_position)


if __name__ == "__main__":
    unittest.main()
