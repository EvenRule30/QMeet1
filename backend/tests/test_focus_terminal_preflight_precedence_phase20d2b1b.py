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

    def test_direct_terminal_gate_precedes_parse_inspection_and_agent(self) -> None:
        source = APP.read_text(encoding="utf-8")
        direct_terminal_index = source.index("const directFocusTerminalCommandMatch =")
        direct_gate_index = source.index("if (directFocusTerminalCommandMatch)")
        parse_index = source.index("const parsedCommandMatch = forcedCommandMatch ?? parseCommand(trimmed);")
        explicit_index = source.index("const explicitDeterministicRoute =")
        agent_first_index = source.index("const promotedSingleIntent =")
        preflight_index = source.index("const semanticLifecyclePreflightBeforeCommandRouting =")
        destructive_index = source.index("if (commandRoute !== 'confirmed' && isDestructiveLocalCommand")

        self.assertLess(direct_terminal_index, direct_gate_index)
        self.assertLess(direct_gate_index, parse_index)
        self.assertLess(parse_index, explicit_index)
        self.assertLess(explicit_index, agent_first_index)
        self.assertLess(agent_first_index, preflight_index)
        self.assertLess(preflight_index, destructive_index)

    def test_preflight_result_is_cached_and_blocks_exact_lifecycle_execution(self) -> None:
        source = APP.read_text(encoding="utf-8")
        self.assertRegex(
            source,
            re.compile(
                r"const semanticLifecyclePreflightBeforeCommandRouting\s*=\s*"
                r".*?\?\s*exactResumeLifecyclePreflight\s*\?\?\s*"
                r"await interpretSemanticFocusLifecycle\(trimmed\)\s*"
                r":\s*null;",
                re.DOTALL,
            ),
        )
        self.assertIn(
            "explicitDeterministicRoute?.kind === 'focus-mutation'",
            source,
        )
        self.assertRegex(
            source,
            re.compile(
                r"const commandMatch\s*=\s*deferredSemanticFocusLifecycleMessage\s*"
                r"\?\s*null\s*:\s*naturalTaskCompletionCommandMatch\s*&&\s*"
                r"parsedCommandMatch\?\.command\s*===\s*'mark-task-done'",
                re.DOTALL,
            ),
        )

    def test_direct_focus_completion_cannot_fall_into_agent_or_interpreter(self) -> None:
        source = APP.read_text(encoding="utf-8")
        direct_gate_index = source.index("if (directFocusTerminalCommandMatch)")
        agent_first_index = source.index("const promotedSingleIntent =")
        semantic_index = source.index("const semanticFocusLifecycle = promotedNonFocusToolOwner")
        interpreter_index = source.index("const interpretedCommand = await interpretCommandIntent(trimmed);")

        self.assertLess(direct_gate_index, agent_first_index)
        self.assertLess(agent_first_index, semantic_index)
        self.assertLess(semantic_index, interpreter_index)
        self.assertRegex(
            source,
            re.compile(
                r"if\s*\(directFocusTerminalCommandMatch\)\s*\{.*?"
                r"return handleSend\(\s*"
                r"'apply verified focus terminal transition',\s*"
                r"visibleUserText,\s*"
                r"'interpreter',\s*"
                r"directFocusTerminalCommandMatch,\s*"
                r"\);.*?\}",
                re.DOTALL,
            ),
        )


if __name__ == "__main__":
    unittest.main()
