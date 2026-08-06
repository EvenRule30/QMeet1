from __future__ import annotations

import re
import unittest
from pathlib import Path


class FocusNaturalTaskCompletionPhase20JTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.app_source = (root / "src/app/App.tsx").read_text(encoding="utf-8")
        cls.resolver_source = (
            root / "src/app/lib/naturalTaskCompletion.ts"
        ).read_text(encoding="utf-8")

    def test_natural_completion_runs_after_exact_parser_before_preflight(self) -> None:
        terminal_index = self.app_source.index(
            "const directFocusTerminalCommandMatch ="
        )
        parser_index = self.app_source.index(
            "const parsedCommandMatch = forcedCommandMatch ?? parseCommand(trimmed);"
        )
        natural_index = self.app_source.index(
            "const naturalTaskCompletionTarget ="
        )
        preflight_index = self.app_source.index(
            "const semanticLifecyclePreflightBeforeCommandRouting ="
        )

        self.assertLess(terminal_index, parser_index)
        self.assertLess(parser_index, natural_index)
        self.assertLess(natural_index, preflight_index)
        self.assertIn("!parsedCommandMatch", self.app_source[parser_index:preflight_index])

    def test_natural_match_claims_the_turn_as_non_lifecycle(self) -> None:
        claim_start = self.app_source.index(
            "const exactNonLifecycleCommandClaimed ="
        )
        preflight_start = self.app_source.index(
            "const semanticLifecyclePreflightBeforeCommandRouting ="
        )
        claim_source = self.app_source[claim_start:preflight_start]

        self.assertIn("Boolean(parsedCommandMatch)", claim_source)
        self.assertIn("Boolean(naturalTaskCompletionCommandMatch)", claim_source)
        self.assertIn("!exactNonLifecycleCommandClaimed", self.app_source)
        self.assertIn(
            ": parsedCommandMatch ?? naturalTaskCompletionCommandMatch;",
            self.app_source,
        )

    def test_synthetic_match_uses_exact_resolved_task_title(self) -> None:
        self.assertIn("command: 'mark-task-done'", self.app_source)
        self.assertIn("payload: naturalTaskCompletionTarget.title", self.app_source)
        self.assertIn(
            "resolveTaskCompletionPreviewTargets(",
            self.app_source,
        )
        self.assertIn(
            "return handleSend(commandToRun.frontendCommand, visibleUserText, 'confirmed');",
            self.app_source,
        )

    def test_resolver_only_considers_open_tasks_linked_to_active_focus(self) -> None:
        self.assertIn("if (!activeSession) return [];", self.resolver_source)
        self.assertIn(
            "tasks.filter((task) => !task.completedAt)",
            self.resolver_source,
        )
        self.assertIn("activeSession.linkedTaskIds", self.resolver_source)
        self.assertNotIn(
            "return tasks.filter((task) => !task.completedAt);",
            self.resolver_source,
        )

    def test_resolver_requires_completed_work_language(self) -> None:
        opening_match = re.search(
            r"const COMPLETION_OPENING = (?P<pattern>/.+?/i);",
            self.resolver_source,
        )
        self.assertIsNotNone(opening_match)
        assert opening_match is not None
        opening = opening_match.group("pattern")
        self.assertIn("^(?:i|we)", opening)
        for expected in (
            "checked",
            "confirmed",
            "found",
            "decided",
            "wrote",
            "finished",
            "completed",
        ):
            self.assertIn(expected, opening)
        self.assertNotIn("want", opening)
        self.assertNotIn("need", opening)
        self.assertIn(
            "if (!trimmed || !COMPLETION_OPENING.test(trimmed)) return null;",
            self.resolver_source,
        )

    def test_resolver_supports_generated_focus_task_language(self) -> None:
        for expected in (
            "checked: 'check'",
            "found: 'select'",
            "chose: 'select'",
            "constraints: 'constraint'",
            "cost: 'budget'",
            "availability: 'available'",
            "wrote: 'write'",
            "decided: 'decide'",
        ):
            self.assertIn(expected, self.resolver_source)
        self.assertIn(
            ".replace(/(\\d),(?=\\d{3}\\b)/g, '$1')",
            self.resolver_source,
        )

    def test_weak_or_ambiguous_matches_are_not_claimed(self) -> None:
        self.assertIn("candidate.matchedTokenCount >= 2", self.resolver_source)
        self.assertIn("candidate.matchedWeight >= 2", self.resolver_source)
        self.assertIn("candidate.score >= 0.5", self.resolver_source)
        self.assertIn("Math.abs(best.score - runnerUp.score) < 0.12", self.resolver_source)
        self.assertIn("return null;", self.resolver_source)

    def test_natural_completion_still_requires_confirmation(self) -> None:
        self.assertIn(
            "Natural Focus task completion needs safety confirmation",
            self.app_source,
        )
        self.assertIn(
            "Natural completed-work language matched one open task linked to the active Focus, so QMeet paused for confirmation.",
            self.app_source,
        )
        self.assertIn("setPendingInterpreterCommand({", self.app_source)


if __name__ == "__main__":
    unittest.main()
