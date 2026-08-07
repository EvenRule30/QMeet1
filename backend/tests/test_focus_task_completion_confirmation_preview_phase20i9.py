from __future__ import annotations

import unittest
from pathlib import Path


class FocusTaskCompletionConfirmationPreviewPhase20I9Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.app_source = (root / "src/app/App.tsx").read_text(encoding="utf-8")
        cls.preview_source = (
            root / "src/app/lib/taskCompletionPreview.ts"
        ).read_text(encoding="utf-8")

    def test_app_resolves_task_targets_before_confirmation(self) -> None:
        self.assertIn(
            "resolveTaskCompletionPreviewTargets(",
            self.app_source,
        )
        self.assertIn("taskCompletionTarget,", self.app_source)
        self.assertIn("memoryTasks,", self.app_source)
        self.assertIn("routingActiveSession,", self.app_source)
        self.assertIn(
            "describeTaskCompletionPreviewTargets(taskCompletionPreviewTargets)",
            self.app_source,
        )

    def test_confirmation_names_the_resolved_task_targets(self) -> None:
        self.assertIn(
            "I understood that as: ${taskCompletionPreviewDescription}.",
            self.app_source,
        )
        self.assertIn(
            'return `mark "${tasks[0].title}" as done`;',
            self.preview_source,
        )
        self.assertIn(
            "This changes local task data.",
            self.app_source,
        )

    def test_confirmed_command_keeps_the_existing_execution_path(self) -> None:
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

    def test_preview_prefers_active_focus_linked_task_order(self) -> None:
        self.assertIn("activeSession.linkedTaskIds", self.preview_source)
        self.assertIn(
            ".map((taskId) => openTaskById.get(taskId))",
            self.preview_source,
        )
        self.assertIn(
            "if (linkedOpenTasks.length > 0) return linkedOpenTasks;",
            self.preview_source,
        )
        self.assertIn(
            "return tasks.filter((task) => !task.completedAt);",
            self.preview_source,
        )

    def test_preview_matches_existing_completion_reference_classes(self) -> None:
        for expected in (
            "kind: 'all'",
            "kind: 'first'",
            "kind: 'last'",
            "kind: 'indexes'",
            "kind: 'lookup'",
        ):
            self.assertIn(expected, self.preview_source)
        self.assertIn("candidateTasks.slice(0, Math.max(1, spec.count))", self.preview_source)
        self.assertIn("candidateTasks.slice(-Math.max(1, spec.count))", self.preview_source)
        self.assertIn("candidateTasks[index - 1]", self.preview_source)
        self.assertIn("title.includes(lookup) || lookup.includes(title)", self.preview_source)
        self.assertIn(".slice(0, 3)", self.preview_source)

    def test_completed_tasks_are_excluded_from_preview(self) -> None:
        self.assertIn(
            "tasks.filter((task) => !task.completedAt)",
            self.preview_source,
        )

    def test_phase20i8_terminal_and_exact_action_order_remains_intact(self) -> None:
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
