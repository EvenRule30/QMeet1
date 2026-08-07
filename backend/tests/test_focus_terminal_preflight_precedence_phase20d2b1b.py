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

    def test_direct_terminal_gate_precedes_all_task_routing_and_preflight(self) -> None:
        source = APP.read_text(encoding="utf-8")
        direct_terminal_index = source.index(
            "const directFocusTerminalCommandMatch ="
        )
        parse_index = source.index(
            "const parsedCommandMatch = forcedCommandMatch ?? parseCommand(trimmed);"
        )
        natural_completion_index = source.index(
            "const naturalTaskCompletionTarget ="
        )
        preflight_index = source.index(
            "const semanticLifecyclePreflightBeforeCommandRouting ="
        )
        destructive_index = source.index(
            "if (commandRoute !== 'confirmed' && isDestructiveLocalCommand"
        )

        self.assertLess(direct_terminal_index, parse_index)
        self.assertLess(parse_index, natural_completion_index)
        self.assertLess(natural_completion_index, preflight_index)
        self.assertLess(preflight_index, destructive_index)

    def test_preflight_result_is_cached_and_prevents_lifecycle_exact_execution(self) -> None:
        source = APP.read_text(encoding="utf-8")

        self.assertIn(
            "semanticLifecyclePreflightBeforeCommandRouting ??\n"
            "      await interpretSemanticFocusLifecycle(trimmed)",
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

        command_match_index = source.index(
            "const commandMatch = deferredSemanticFocusLifecycleMessage"
        )
        deferred_null_index = source.index("? null", command_match_index)
        task_refinement_index = source.index(
            "parsedCommandMatch?.command === 'mark-task-done'",
            deferred_null_index,
        )
        safe_fallback_index = source.index(
            "parsedCommandMatch ?? naturalTaskCompletionCommandMatch",
            task_refinement_index,
        )
        execution_index = source.index("if (commandMatch)", safe_fallback_index)

        # The lifecycle deferral branch must remain the first decision in
        # command selection. Phase 20O may refine a safe mark-task-done match
        # afterward, but no exact or natural task command may bypass deferral.
        self.assertLess(command_match_index, deferred_null_index)
        self.assertLess(deferred_null_index, task_refinement_index)
        self.assertLess(task_refinement_index, safe_fallback_index)
        self.assertLess(safe_fallback_index, execution_index)

        self.assertRegex(
            source,
            re.compile(
                r"const commandMatch\s*=\s*deferredSemanticFocusLifecycleMessage\s*"
                r"\? null\s*:"
            ),
        )

    def test_direct_focus_completion_cannot_fall_into_interpreter(self) -> None:
        source = APP.read_text(encoding="utf-8")
        semantic_index = source.index(
            "const semanticFocusLifecycle =\n"
            "      semanticLifecyclePreflightBeforeCommandRouting"
        )
        interpreter_index = source.index(
            "const interpretedCommand = await interpretCommandIntent(trimmed);"
        )

        self.assertLess(semantic_index, interpreter_index)
        self.assertIn("if (deferredSemanticFocusLifecycleMessage)", source)


if __name__ == "__main__":
    unittest.main()
