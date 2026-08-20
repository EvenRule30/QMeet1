from __future__ import annotations

import unittest
from pathlib import Path


def assert_confirmed_task_identity_path(testcase: unittest.TestCase, source: str) -> None:
    capture = source.index(
        "const resolvedTaskTargets = pendingTaskCompletionTargetsRef.current;"
    )
    synthetic = source.index(
        "const confirmedTaskCommandMatch: CommandMatch | undefined =",
        capture,
    )
    wrapper = source.index(
        "const executeConfirmedPendingCommand = async (",
        synthetic,
    )
    confirmed_call = source.index(
        "await handleSend(",
        wrapper,
    )
    call_end = source.index(");", confirmed_call)
    call_block = source[confirmed_call:call_end]

    testcase.assertLess(capture, synthetic)
    testcase.assertLess(synthetic, wrapper)
    testcase.assertIn("confirmedCommandMatch", call_block)
    testcase.assertIn("resolvedTaskTargets", call_block)
    testcase.assertIn("'confirmed'", call_block)

    synthetic_block = source[synthetic:wrapper]
    testcase.assertIn(
        "commandToRun.action === 'mark-task-done'",
        synthetic_block,
    )
    testcase.assertIn(
        "resolvedTaskTargets.length > 0",
        synthetic_block,
    )
    testcase.assertIn(
        ".map((task) => task.title)",
        synthetic_block,
    )

    testcase.assertIn(
        "return executeConfirmedPendingCommand(confirmedTaskCommandMatch);",
        source,
    )


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
            "I couldn't find an open task matching",
            self.preview_source,
        )
        self.assertIn(
            "No task was changed.",
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
        self.assertIn("Task completion command had no target", self.app_source)
        self.assertIn("No matching open task to complete", self.app_source)
        self.assertIn(
            "Task completion reference did not resolve to an open task, so no confirmation was created.",
            self.app_source,
        )

    def test_resolved_targets_still_receive_exact_confirmation(self) -> None:
        self.assertIn("taskCompletionPreviewDescription", self.app_source)
        self.assertIn(
            "I understood that as: ${taskCompletionPreviewDescription}.",
            self.app_source,
        )
        self.assertIn("This changes local task data.", self.app_source)

    def test_confirmed_execution_path_is_unchanged(self) -> None:
        self.assertIn(
            "? `mark task ${taskCompletionTarget} done`",
            self.app_source,
        )
        assert_confirmed_task_identity_path(self, self.app_source)

    def test_phase20i8_routing_order_remains_intact(self) -> None:
        terminal_index = self.app_source.index("const directFocusTerminalCommandMatch =")
        parse_index = self.app_source.index("const parsedCommandMatch =")
        preflight_index = self.app_source.index(
            "const semanticLifecyclePreflightBeforeCommandRouting ="
        )
        self.assertLess(terminal_index, parse_index)
        self.assertLess(parse_index, preflight_index)
        self.assertIn("!exactNonLifecycleCommandClaimed", self.app_source)


if __name__ == "__main__":
    unittest.main()
