from __future__ import annotations

import re
import unittest
from pathlib import Path


class FocusExactActionPrecedencePhase20I8Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.app_source = (root / "src/app/App.tsx").read_text(encoding="utf-8")
        cls.commands_source = (root / "src/app/commands.ts").read_text(
            encoding="utf-8"
        )
        cls.semantic_source = (
            root / "src/app/lib/semanticFocusLifecycle.ts"
        ).read_text(encoding="utf-8")
        cls.read_surface_source = (
            root / "src/app/lib/memoryReadSurface.ts"
        ).read_text(encoding="utf-8")

    def _semantic_helper_body(self) -> str:
        match = re.search(
            r"export function shouldRouteExactFocusLifecycleThroughSemanticPreflight\s*\(.*?\)\s*:\s*boolean\s*\{(?P<body>.*?)\n\}",
            self.semantic_source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(
            match,
            "the exact lifecycle classification helper must remain declared",
        )
        assert match is not None
        return match.group("body")

    def _routing_block(self) -> str:
        start = self.app_source.index(
            "const directFocusTerminalCommandMatch ="
        )
        end = self.app_source.index("if (commandMatch) {", start)
        return self.app_source[start:end]

    def test_exact_parser_runs_before_message_level_semantic_preflight(self) -> None:
        routing = self._routing_block()
        self.assertLess(
            routing.index("const parsedCommandMatch ="),
            routing.index("const semanticLifecyclePreflightBeforeCommandRouting ="),
        )
        self.assertLess(
            routing.index("const directFocusTerminalCommandMatch ="),
            routing.index("const parsedCommandMatch ="),
            "the direct terminal safety gate must remain first",
        )

    def test_exact_non_lifecycle_command_claim_blocks_generic_preflight(self) -> None:
        routing = self._routing_block()
        claim_start = routing.index("const exactNonLifecycleCommandClaimed =")
        preflight_start = routing.index(
            "const semanticLifecyclePreflightBeforeCommandRouting ="
        )
        claim = routing[claim_start:preflight_start]
        self.assertIn("!forcedCommandMatch", claim)
        self.assertIn("commandRoute === 'exact'", claim)
        self.assertIn("Boolean(parsedCommandMatch)", claim)
        self.assertIn("!Boolean(deferredExactFocusLifecycleMatch)", claim)

        preflight = routing[preflight_start:]
        self.assertIn("!exactNonLifecycleCommandClaimed", preflight)

        # Phase 21B explicit-command precedence adds one additional reason to
        # enter semantic Focus preflight: a deterministic explicit Focus
        # mutation such as "goal:" or "rename the focus". The Phase 20I8
        # invariant remains the same: an exact non-lifecycle command claim
        # blocks the entire generic preflight branch.
        self.assertRegex(
            preflight,
            r"Boolean\(deferredExactFocusLifecycleMatch\)\s*\|\|\s*"
            r"explicitDeterministicRoute\?\.kind\s*===\s*'focus-mutation'\s*\|\|\s*"
            r"shouldPreflightSemanticFocusLifecycleBeforeCommandRouting\(trimmed\)",
        )

    def test_focus_to_tasks_is_exact_and_not_a_lifecycle_mutation(self) -> None:
        self.assertIn("'focus-to-tasks'", self.commands_source)
        self.assertIn("(?:turn|convert|make|create)", self.commands_source)
        self.assertNotIn("'focus-to-tasks'", self._semantic_helper_body())

    def test_save_summary_is_exact_and_not_a_lifecycle_mutation(self) -> None:
        self.assertIn("'save-focus-summary'", self.commands_source)
        self.assertIn("const saveSummaryPatterns =", self.commands_source)
        self.assertNotIn("'save-focus-summary'", self._semantic_helper_body())

    def test_calendar_focus_prep_is_exact_and_not_a_lifecycle_mutation(self) -> None:
        self.assertIn("command: 'prepare-calendar-focus'", self.commands_source)
        self.assertNotIn("'prepare-calendar-focus'", self._semantic_helper_body())

    def test_exact_lifecycle_mutations_still_use_semantic_preflight(self) -> None:
        helper = self._semantic_helper_body()
        for command in (
            "start-focus-session",
            "update-focus-session",
            "resume-last-focus-session",
            "end-focus-session",
            "end-focus-with-summary",
        ):
            self.assertIn(f"commandMatch?.command === '{command}'", helper)
        self.assertIn(
            "Boolean(deferredExactFocusLifecycleMatch)", self._routing_block()
        )
        self.assertIn(
            "explicitDeterministicRoute?.kind === 'focus-mutation'",
            self._routing_block(),
        )

    def test_mark_task_done_retains_focus_terminal_precedence(self) -> None:
        helper = self._semantic_helper_body()
        self.assertIn("commandMatch?.command === 'mark-task-done'", helper)
        self.assertRegex(
            helper,
            r"looksLikeFocusTerminalLanguage\(\s*originalMessage\s*\)",
        )

    def test_general_focus_context_still_enters_phase20i_preflight(self) -> None:
        match = re.search(
            r"export function shouldPreflightSemanticFocusLifecycleBeforeCommandRouting\s*\(.*?\)\s*:\s*boolean\s*\{(?P<body>.*?)\n\}",
            self.semantic_source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertIn("looksLikeFocusContextStatement(message)", match.group("body"))
        self.assertIn(
            "shouldPreflightSemanticFocusLifecycleBeforeCommandRouting(trimmed)",
            self._routing_block(),
        )

    def test_unrelated_task_sentence_has_a_paragraph_break(self) -> None:
        self.assertIn(
            "? `\\n\\nYou also have ${unrelatedOpenCount} unrelated open task${",
            self.read_surface_source,
        )
        self.assertNotIn(
            "? ` You also have ${unrelatedOpenCount} unrelated open task${",
            self.read_surface_source,
        )


if __name__ == "__main__":
    unittest.main()
