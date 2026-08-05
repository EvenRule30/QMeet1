from __future__ import annotations

import unittest
from pathlib import Path


class NativeFocusTasksInstallContractPhase20E2BTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.backend_root = Path(__file__).resolve().parents[1]
        cls.tasks = (
            cls.backend_root / "app" / "focus" / "tasks.py"
        ).read_text(encoding="utf-8")
        cls.router = (
            cls.backend_root / "app" / "routers" / "focus_lifecycle.py"
        ).read_text(encoding="utf-8")
        repository_root = cls.backend_root.parent
        cls.memory = (
            repository_root / "src" / "app" / "commandHandlers" / "memory.ts"
        ).read_text(encoding="utf-8")
        cls.client = (
            repository_root / "src" / "app" / "lib" / "nativeFocusTasks.ts"
        ).read_text(encoding="utf-8")

    def test_backend_exposes_verified_task_receipt(self) -> None:
        self.assertIn("class NativeFocusTasksRequest", self.tasks)
        self.assertIn("def link_focus_tasks_verified", self.tasks)
        self.assertIn("activeFocusMatches", self.tasks)
        self.assertIn("tasksPersisted", self.tasks)
        self.assertIn("relationshipPersisted", self.tasks)
        self.assertIn("sourceTurnUnique", self.tasks)
        self.assertIn('"tasksByFocusId"', self.tasks)
        self.assertIn('@router.post("/tasks"', self.router)
        self.assertIn('"link_focus_tasks"', self.router)
        self.assertIn('"taskHealth"', self.router)

    def test_frontend_requires_all_canonical_proofs(self) -> None:
        self.assertIn("/api/focus/lifecycle/tasks", self.client)
        self.assertIn("verification?.activeFocusMatches === true", self.client)
        self.assertIn("verification?.tasksPersisted === true", self.client)
        self.assertIn("verification?.relationshipPersisted === true", self.client)
        self.assertIn("verification?.sourceTurnUnique === true", self.client)
        self.assertIn("receiptTasksAppearInMemory", self.client)
        self.assertIn("applyVerifiedFocusTaskProjection", self.client)

    def test_memory_wrapper_owns_focus_tasks_before_legacy_fallback(self) -> None:
        native_position = self.memory.index(
            "if (commandMatch.command === 'focus-to-tasks')"
        )
        fallback_position = self.memory.index(
            "return handleMemoryCommandCore(commandMatch, deps);"
        )
        self.assertLess(native_position, fallback_position)
        self.assertIn("createNativeFocusTasksVerified", self.memory)
        self.assertIn("applyVerifiedFocusTaskProjection", self.memory)
        self.assertIn("'focus-to-tasks',", self.memory)
        self.assertIn("'create-meeting-follow-up-tasks',", self.memory)

    def test_native_task_handlers_do_not_stage_browser_owned_tasks(self) -> None:
        start = self.memory.index("if (commandMatch.command === 'focus-to-tasks')")
        end = self.memory.index("if (commandMatch.command === 'save-focus-summary')")
        handlers = self.memory[start:end]
        self.assertIn("if (commandMatch.command === 'create-meeting-follow-up-tasks')", handlers)
        self.assertNotIn("deps.saveMemoryTask", handlers)
        self.assertNotIn("patchActiveSessionInBackend", handlers)
        self.assertGreaterEqual(handlers.count("createNativeFocusTasksVerified"), 2)
        self.assertGreaterEqual(handlers.count("result.message"), 2)

    def test_legacy_focus_task_success_is_quarantined(self) -> None:
        native_position = self.memory.index(
            "if (commandMatch.command === 'focus-to-tasks')"
        )
        quarantine_position = self.memory.index(
            "RETIRED_LEGACY_FOCUS_OWNERSHIP_COMMANDS.has(commandMatch.command)"
        )
        fallback_position = self.memory.index(
            "return handleMemoryCommandCore(commandMatch, deps);"
        )
        self.assertLess(native_position, quarantine_position)
        self.assertLess(quarantine_position, fallback_position)
        self.assertIn(
            "I could not verify that the exact tasks",
            self.client,
        )

    def test_task_generation_preserves_legacy_user_facing_shapes(self) -> None:
        self.assertIn("buildNativeFocusTaskTitles", self.client)
        self.assertIn("buildNativeMeetingFollowUpTaskTitles", self.client)
        self.assertIn("Capture decisions and outcomes from", self.client)
        self.assertIn("Confirm owners and deadlines for action items from", self.client)
        self.assertIn("case 'planning':", self.client)
        self.assertIn("case 'research':", self.client)
        self.assertIn("case 'meeting':", self.client)
        self.assertIn("case 'personal':", self.client)
        self.assertIn("case 'java-hello-world':", self.client)


if __name__ == "__main__":
    unittest.main()
