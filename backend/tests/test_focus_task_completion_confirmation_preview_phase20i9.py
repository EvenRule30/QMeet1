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


class FocusTaskCompletionConfirmationPreviewPhase20I9Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.app_source = (root / "src/app/App.tsx").read_text(encoding="utf-8")
        cls.preview_source = (
            root / "src/app/lib/taskCompletionPreview.ts"
        ).read_text(encoding="utf-8")

    def test_task_completion_preview_is_built_before_confirmation(self) -> None:
        preview = self.app_source.index("const taskCompletionPreviewTargets =")
        description = self.app_source.index(
            "const taskCompletionPreviewDescription =",
            preview,
        )
        pending = self.app_source.index(
            "pendingTaskCompletionTargetsRef.current = isTaskCompletionCommand",
            description,
        )
        self.assertLess(preview, description)
        self.assertLess(description, pending)
        self.assertIn(
            "describeTaskCompletionPreviewTargets(taskCompletionPreviewTargets)",
            self.app_source,
        )

    def test_confirmation_prompt_describes_the_resolved_targets(self) -> None:
        self.assertIn(
            "I understood that as: ${taskCompletionPreviewDescription}.",
            self.app_source,
        )
        self.assertIn("This changes local task data.", self.app_source)

    def test_confirmed_command_keeps_the_existing_execution_path(self) -> None:
        assert_confirmed_task_identity_path(self, self.app_source)

    def test_preview_helper_does_not_mutate_tasks(self) -> None:
        self.assertIn("resolveTaskCompletionPreviewTargets", self.preview_source)
        self.assertNotIn("completedAt =", self.preview_source)


if __name__ == "__main__":
    unittest.main()
