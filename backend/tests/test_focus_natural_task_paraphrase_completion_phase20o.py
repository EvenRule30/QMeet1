from __future__ import annotations

import unittest
from pathlib import Path


class FocusNaturalTaskParaphraseCompletionPhase20OTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.app_source = (root / "src/app/App.tsx").read_text(encoding="utf-8")
        cls.natural_source = (
            root / "src/app/lib/naturalTaskCompletion.ts"
        ).read_text(encoding="utf-8")
        cls.preview_source = (
            root / "src/app/lib/taskCompletionPreview.ts"
        ).read_text(encoding="utf-8")

    def test_natural_completion_can_refine_generic_mark_task_done_parse(self) -> None:
        self.assertIn(
            "!parsedCommandMatch || parsedCommandMatch.command === 'mark-task-done'",
            self.app_source,
        )
        self.assertIn(
            "parsedCommandMatch?.command === 'mark-task-done'",
            self.app_source,
        )
        self.assertIn(
            "? naturalTaskCompletionCommandMatch",
            self.app_source,
        )
        self.assertIn(
            ": parsedCommandMatch ?? naturalTaskCompletionCommandMatch;",
            self.app_source,
        )

    def test_audience_completion_vocabulary_is_supported(self) -> None:
        for expected in (
            "tailored",
            "adapted",
            "customized",
            "adjusted",
            "tailored: 'tailor'",
            "adapted: 'tailor'",
        ):
            self.assertIn(expected, self.natural_source)

    def test_did_normalizes_to_do_for_generated_first_step_task(self) -> None:
        self.assertIn("did: 'do'", self.natural_source)
        self.assertIn("reviewed: 'review'", self.natural_source)

    def test_exact_resolved_task_title_wins_before_numeric_index_parsing(self) -> None:
        exact_index = self.preview_source.index("const exactTitleMatch =")
        parse_index = self.preview_source.index("const spec = parseTaskCompletionSpec(payload);")
        self.assertLess(exact_index, parse_index)
        self.assertIn(
            "normalizeTaskLookup(task.title) === normalizedPayload",
            self.preview_source,
        )
        self.assertIn("if (exactTitleMatch) return [exactTitleMatch];", self.preview_source)

    def test_existing_numeric_and_ordinal_reference_support_remains(self) -> None:
        for expected in (
            "kind: 'indexes'",
            "candidateTasks[index - 1]",
            "kind: 'first'",
            "kind: 'last'",
            "kind: 'all'",
        ):
            self.assertIn(expected, self.preview_source)

    def test_terminal_gate_still_precedes_parser_and_natural_refinement(self) -> None:
        terminal_index = self.app_source.index("const directFocusTerminalCommandMatch =")
        parser_index = self.app_source.index("const parsedCommandMatch =")
        natural_index = self.app_source.index("const naturalTaskCompletionTarget =")
        self.assertLess(terminal_index, parser_index)
        self.assertLess(parser_index, natural_index)


if __name__ == "__main__":
    unittest.main()
