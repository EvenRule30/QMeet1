from __future__ import annotations

import unittest
from pathlib import Path


class FocusScopedTaskReadPhase20ITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[2]
        cls.read_surface = (cls.root / "src/app/lib/memoryReadSurface.ts").read_text(encoding="utf-8")
        cls.wrapper = (cls.root / "src/app/commandHandlers/memory.ts").read_text(encoding="utf-8")
        cls.tasks = (cls.root / "src/app/lib/nativeFocusTasks.ts").read_text(encoding="utf-8")
        cls.readiness = (cls.root / "backend/app/focus/readiness.py").read_text(encoding="utf-8")
        cls.panel = (cls.root / "src/app/components/FocusResponseHealth.tsx").read_text(encoding="utf-8")

    def test_task_readout_filters_to_active_focus_relationship(self) -> None:
        self.assertIn("formatFocusTaskReadout", self.read_surface)
        self.assertIn("new Set(activeSession.linkedTaskIds)", self.read_surface)
        self.assertIn("linkedIds.has(task.id)", self.read_surface)
        self.assertNotIn("Latest note:", self.read_surface)
        self.assertNotIn("Latest calendar item:", self.read_surface)

    def test_read_memory_is_intercepted_before_memory_core(self) -> None:
        scoped_index = self.wrapper.index("formatFocusTaskReadout(activeSession, tasks)")
        fallback_index = self.wrapper.rindex("return handleMemoryCommandCore(commandMatch, deps)")
        self.assertLess(scoped_index, fallback_index)

    def test_task_generation_uses_canonical_context(self) -> None:
        self.assertIn("buildContextAwareNativeFocusTaskTitles", self.tasks)
        self.assertIn("readNativeFocusContext(activeSession.id)", self.tasks)
        self.assertIn("buildNativeFocusContextTaskTitles(context)", self.tasks)
        self.assertIn("await buildContextAwareNativeFocusTaskTitles(activeSession)", self.wrapper)

    def test_summary_includes_canonical_context(self) -> None:
        self.assertIn("appendNativeFocusContextToSummary", self.wrapper)
        self.assertIn("readNativeFocusContext(activeSession.id)", self.wrapper)

    def test_readiness_labels_distinguish_planner_and_exact_routes(self) -> None:
        self.assertIn("guarded planner route decision", self.readiness)
        self.assertIn("exact local-route observation", self.readiness)
        self.assertIn("Guarded Planner Routes", self.panel)
        self.assertIn("Planner-routed current-session decisions", self.panel)


if __name__ == "__main__":
    unittest.main()
