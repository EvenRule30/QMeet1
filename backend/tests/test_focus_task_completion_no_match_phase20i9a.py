from __future__ import annotations

import unittest
from pathlib import Path


class FocusTaskCompletionNoMatchPhase20I9ATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.app_source = (root / "src/app/App.tsx").read_text(encoding="utf-8")
        cls.preview_source = (
            root / "src/app/lib/taskCompletionPreview.ts"
        ).read_text(encoding="utf-8")

    def test_unresolved_task_reference_has_a_specific_message(self) -> None:
        self.assertIn(
            "describeUnresolvedTaskCompletionRequest(taskCompletionTarget)",
            self.app_source,
        )
        self.assertIn(
            'I couldn\'t find an open task matching "${target}". No task was changed.',
            self.preview_source,
        )
        self.assertIn(
            "I couldn't find an open task to complete. No task was changed.",
            self.preview_source,
        )

    def test_unresolved_task_reference_returns_without_confirmation(self) -> None:
        branch = "if (isTaskCompletionCommand && !taskCompletionPreviewDescription)"
        branch_index = self.app_source.index(branch)
        return_index = self.app_source.index("return;", branch_index)
        pending_index = self.app_source.index(
            "setPendingInterpreterCommand({",
            return_index,
        )
        self.assertLess(branch_index, return_index)
        self.assertLess(return_index, pending_index)
        branch_source = self.app_source[branch_index:return_index]
        self.assertNotIn("setPendingInterpreterCommand({", branch_source)

    def test_no_match_records_that_no_open_task_was_resolved(self) -> None:
        self.assertIn(
            "setLastInputRoute('Task completion command had no target')",
            self.app_source,
        )
        self.assertIn(
            "setLastLocalCommand('No matching open task to complete')",
            self.app_source,
        )
        self.assertIn(
            "Task completion reference did not resolve to an open task, so no confirmation was created.",
            self.app_source,
        )

    def test_resolved_targets_still_receive_exact_confirmation(self) -> None:
        self.assertIn(
            "taskCompletionPreviewDescription",
            self.app_source,
        )
        self.assertIn(
            "I understood that as: ${taskCompletionPreviewDescription}.",
            self.app_source,
        )
        self.assertIn(
            "This changes local task data.",
            self.app_source,
        )

    def test_confirmed_execution_path_is_unchanged(self) -> None:
        self.assertIn(
            "? `mark task ${taskCompletionTarget} done`",
            self.app_source,
        )
        self.assertIn(
            "const resolvedTaskTargets = pendingTaskCompletionTargetsRef.current;",
            self.app_source,
        )
        self.assertIn(
            "const confirmedTaskCommandMatch: CommandMatch | undefined =",
            self.app_source,
        )
        self.assertIn(
            "confirmedTaskCommandMatch,\n              resolvedTaskTargets",
            self.app_source,
        )

    def test_phase20i8_routing_order_remains_intact(self) -> None:
        terminal_index = self.app_source.index(
            "const directFocusTerminalCommandMatch ="
        )
        parse_index = self.app_source.index("const parsedCommandMatch =")
        preflight_index = self.app_source.index(
            "const semanticLifecyclePreflightBeforeCommandRouting ="
        )
        self.assertLess(terminal_index, parse_index)
        self.assertLess(parse_index, preflight_index)
        self.assertIn("!exactNonLifecycleCommandClaimed", self.app_source)


if __name__ == "__main__":
    unittest.main()
