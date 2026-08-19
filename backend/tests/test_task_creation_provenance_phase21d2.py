from __future__ import annotations

import unittest
from pathlib import Path


class TaskCreationProvenancePhase21D2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[2]
        cls.calendar_service = (
            cls.root / "backend/app/calendar_service.py"
        ).read_text(encoding="utf-8")
        cls.focus_context_client = (
            cls.root / "src/app/lib/nativeFocusContext.ts"
        ).read_text(encoding="utf-8")
        cls.focus_tasks_client = (
            cls.root / "src/app/lib/nativeFocusTasks.ts"
        ).read_text(encoding="utf-8")
        cls.focus_tasks_backend = (
            cls.root / "backend/app/focus/tasks.py"
        ).read_text(encoding="utf-8")
        cls.memory_router = (
            cls.root / "backend/app/routers/memory.py"
        ).read_text(encoding="utf-8")
        cls.commands = (
            cls.root / "src/app/commands.ts"
        ).read_text(encoding="utf-8")
        cls.agent_promotion = (
            cls.root / "src/app/lib/agentToolPromotion.ts"
        ).read_text(encoding="utf-8")

    def test_calendar_read_status_has_the_historical_contamination_source_shape(self) -> None:
        self.assertIn('f"Loaded {len(events)} Google Calendar "', self.calendar_service)
        self.assertIn("f\"event{'s' if len(events) != 1 else ''}.\"", self.calendar_service)

    def test_focus_to_tasks_is_the_context_aware_writer_path(self) -> None:
        self.assertIn(
            "const contextTitles = buildNativeFocusContextTaskTitles(context);",
            self.focus_tasks_client,
        )
        self.assertIn(
            "`${QMEET_API_BASE_URL}/api/focus/lifecycle/tasks`",
            self.focus_tasks_client,
        )
        self.assertIn("taskTitles,", self.focus_tasks_client)

    def test_verified_focus_task_backend_materializes_requested_titles_in_global_memory(self) -> None:
        self.assertIn("def _select_or_create_tasks(", self.focus_tasks_backend)
        self.assertIn('"id": memory_store._new_task_id()', self.focus_tasks_backend)
        self.assertIn('"title": title', self.focus_tasks_backend)
        self.assertIn(
            "memory_store._write_payload_unlocked(",
            self.focus_tasks_backend,
        )
        self.assertIn("next_memory_tasks", self.focus_tasks_backend)

    def test_ordinary_global_task_create_is_a_separate_writer(self) -> None:
        self.assertIn('@router.post("/tasks", response_model=MemoryTasksResponse)', self.memory_router)
        self.assertIn("create_memory_task(req.title)", self.memory_router)

    def test_focus_task_generation_requires_explicit_focus_to_tasks_language(self) -> None:
        self.assertIn("'focus-to-tasks'", self.commands)
        self.assertIn("(?:turn|convert|make|create)", self.commands)
        self.assertNotIn("focus-to-tasks", self.agent_promotion)

    def test_known_facts_are_not_actionable_task_inputs(self) -> None:
        self.assertIn("knownFacts: string[]", self.focus_context_client)
        self.assertIn(
            "section('Known details', context.knownFacts)",
            self.focus_context_client,
        )
        self.assertNotIn(
            "Use this known detail in the plan:",
            self.focus_context_client,
        )
        self.assertNotIn("context.knownFacts.map(", self.focus_context_client)


if __name__ == "__main__":
    unittest.main()
