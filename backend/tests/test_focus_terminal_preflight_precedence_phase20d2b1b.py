from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "app" / "App.tsx"
BRIDGE = ROOT / "src" / "app" / "lib" / "semanticFocusLifecycle.ts"


class FocusTerminalPreflightPrecedenceTests(unittest.TestCase):
    def test_direct_terminal_helper_is_exported(self) -> None:
        source = BRIDGE.read_text(encoding="utf-8")
        self.assertIn(
            "export function shouldPreflightSemanticFocusLifecycleBeforeCommandRouting",
            source,
        )
        self.assertIn("return looksLikeFocusTerminalLanguage(message);", source)

    def test_direct_terminal_gate_precedes_parser_and_generic_preflight(self) -> None:
        source = APP.read_text(encoding="utf-8")
        direct_terminal_index = source.index(
            "const directFocusTerminalCommandMatch ="
        )
        parse_index = source.index(
            "const parsedCommandMatch = forcedCommandMatch ?? parseCommand(trimmed);"
        )
        preflight_index = source.index(
            "const semanticLifecyclePreflightBeforeCommandRouting ="
        )
        destructive_index = source.index(
            "if (commandRoute !== 'confirmed' && isDestructiveLocalCommand"
        )

        self.assertLess(direct_terminal_index, parse_index)
        self.assertLess(parse_index, preflight_index)
        self.assertLess(preflight_index, destructive_index)

    def test_preflight_result_is_cached_and_prevents_exact_execution(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertIn(
            "semanticLifecyclePreflightBeforeCommandRouting ??\n      await interpretSemanticFocusLifecycle(trimmed)",
            source,
        )
        self.assertRegex(
            source,
            re.compile(
                r"const deferredSemanticFocusLifecycleMessage\s*=\s*"
                r"Boolean\(semanticLifecyclePreflightBeforeCommandRouting\)\s*\|\|\s*"
                r"Boolean\(deferredExactFocusLifecycleMatch\);"
            ),
        )
        self.assertIn(
            "const commandMatch = deferredSemanticFocusLifecycleMessage\n      ? null\n      : parsedCommandMatch;",
            source,
        )

    def test_direct_focus_completion_cannot_fall_into_interpreter(self) -> None:
        source = APP.read_text(encoding="utf-8")
        semantic_index = source.index(
            "const semanticFocusLifecycle =\n      semanticLifecyclePreflightBeforeCommandRouting"
        )
        interpreter_index = source.index(
            "const interpretedCommand = await interpretCommandIntent(trimmed);"
        )
        self.assertLess(semantic_index, interpreter_index)
        self.assertIn("if (deferredSemanticFocusLifecycleMessage)", source)


if __name__ == "__main__":
    unittest.main()
