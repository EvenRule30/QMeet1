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


class FocusTaskConfirmationIdentityPhase20PTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.app_source = (root / "src/app/App.tsx").read_text(encoding="utf-8")
        cls.execution_source = (
            root / "src/app/lib/confirmedTaskCompletion.ts"
        ).read_text(encoding="utf-8")

    def test_preview_targets_are_saved_by_identity(self) -> None:
        self.assertIn(
            "const pendingTaskCompletionTargetsRef = useRef<ConfirmedTaskTarget[]>([]);",
            self.app_source,
        )
        self.assertIn(
            "pendingTaskCompletionTargetsRef.current = isTaskCompletionCommand",
            self.app_source,
        )
        self.assertIn("id: task.id", self.app_source)
        self.assertIn("title: task.title", self.app_source)

    def test_confirm_reuses_previewed_targets_without_reparsing_them(self) -> None:
        assert_confirmed_task_identity_path(self, self.app_source)
        capture = self.app_source.index(
            "const resolvedTaskTargets = pendingTaskCompletionTargetsRef.current;"
        )
        wrapper = self.app_source.index(
            "const executeConfirmedPendingCommand = async (",
            capture,
        )
        confirm_block = self.app_source[capture:wrapper]
        self.assertNotIn("resolveTaskCompletionPreviewTargets(", confirm_block)
        self.assertNotIn("resolveNaturalFocusTaskCompletionTarget(", confirm_block)

    def test_confirmed_identity_must_still_be_open_and_match_title(self) -> None:
        self.assertIn("task.id === target.id", self.app_source)
        self.assertIn("!task.completedAt", self.app_source)
        self.assertIn("task.title.trim() === target.title.trim()", self.app_source)
        self.assertIn("Confirmed task identity changed", self.app_source)
        self.assertIn("refused to re-resolve a different task", self.app_source)

    def test_focus_progress_uses_same_confirmed_identity(self) -> None:
        self.assertIn("const immutableConfirmedTaskTargets =", self.app_source)
        self.assertIn("? immutableConfirmedTaskTargets", self.app_source)
        self.assertIn(
            "routingActiveSession.linkedTaskIds.includes(task.id)",
            self.app_source,
        )

    def test_local_completion_is_atomic_by_task_id(self) -> None:
        self.assertIn(
            "new Map(targets.map((target) => [target.id, target]))",
            self.execution_source,
        )
        self.assertIn("const openTaskById = new Map", self.execution_source)
        self.assertIn(
            "const task = openTaskById.get(target.id);",
            self.execution_source,
        )
        self.assertIn(
            "const targetIds = new Set(resolvedTasks.map((task) => task.id));",
            self.execution_source,
        )
        self.assertIn(
            "if (!targetIds.has(task.id) || task.completedAt)",
            self.execution_source,
        )
        self.assertIn(
            "verifiedCompletedAtByTaskId.get(task.id)",
            self.execution_source,
        )

    def test_task_preview_uses_reconciled_focus_projection(self) -> None:
        preview_index = self.app_source.index("const taskCompletionPreviewTargets =")
        pending_index = self.app_source.index(
            "pendingTaskCompletionTargetsRef.current = isTaskCompletionCommand",
            preview_index,
        )
        preview_block = self.app_source[preview_index:pending_index]
        self.assertIn("routingActiveSession", preview_block)
        self.assertNotIn(
            "memoryTasks,\\n              activeSession",
            preview_block,
        )


if __name__ == "__main__":
    unittest.main()
