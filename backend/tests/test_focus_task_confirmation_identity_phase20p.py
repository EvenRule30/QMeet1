from __future__ import annotations

import unittest
from pathlib import Path


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
        self.assertIn(
            "const resolvedTaskTargets = pendingTaskCompletionTargetsRef.current;",
            self.app_source,
        )
        self.assertIn(
            "commandToRun.action === 'mark-task-done'",
            self.app_source,
        )
        self.assertIn(
            "confirmedTaskCommandMatch,\n              resolvedTaskTargets",
            self.app_source,
        )
        self.assertIn(
            "const parsedCommandMatch = forcedCommandMatch ?? parseCommand(trimmed);",
            self.app_source,
        )

    def test_confirmed_identity_must_still_be_open_and_match_title(self) -> None:
        self.assertIn("task.id === target.id", self.app_source)
        self.assertIn("!task.completedAt", self.app_source)
        self.assertIn("task.title.trim() === target.title.trim()", self.app_source)
        self.assertIn("Confirmed task identity changed", self.app_source)
        self.assertIn(
            "refused to re-resolve a different task",
            self.app_source,
        )

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
        self.assertIn("MEMORY_TASKS_STATE_EVENT", self.execution_source)

    def test_task_preview_uses_reconciled_focus_projection(self) -> None:
        preview_index = self.app_source.index("const taskCompletionPreviewTargets =")
        pending_index = self.app_source.index(
            "pendingTaskCompletionTargetsRef.current = isTaskCompletionCommand",
            preview_index,
        )
        preview_block = self.app_source[preview_index:pending_index]
        self.assertIn("routingActiveSession", preview_block)
        self.assertNotIn("memoryTasks,\n              activeSession", preview_block)


if __name__ == "__main__":
    unittest.main()
