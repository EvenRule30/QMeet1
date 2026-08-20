from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
MEMORY_OVERLAY = ROOT / "src" / "app" / "panels" / "MemoryOverlay.tsx"
MEMORY_CSS = ROOT / "src" / "app" / "panels" / "MemoryOverlay.css"


class MemoryPanelRemasterPhase21H4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MEMORY_OVERLAY.read_text(encoding="utf-8")
        cls.css = MEMORY_CSS.read_text(encoding="utf-8")

    def test_everyday_surface_prioritizes_focus_and_tasks(self):
        self.assertIn('className="memory-remaster-card memory-remaster-focus-card"', self.source)
        self.assertIn('className="memory-remaster-task-input-row"', self.source)
        self.assertIn('Open tasks', self.source)
        self.assertIn('Current Focus', self.source)

    def test_secondary_context_and_maintenance_are_collapsible(self):
        self.assertIn('<details className="memory-remaster-details">', self.source)
        self.assertIn('Recent Focus history', self.source)
        self.assertIn('Saved visual context', self.source)
        self.assertIn('Data & maintenance', self.source)
        self.assertIn('Export JSON', self.source)
        self.assertIn('Import JSON', self.source)

    def test_development_era_help_sections_are_removed(self):
        self.assertNotIn('Focus Nudges', self.source)
        self.assertNotIn('Supported Commands', self.source)
        self.assertNotIn('Backend Memory', self.source)
        self.assertNotIn('FastAPI with browser fallback', self.source)

    def test_existing_task_mutation_paths_are_preserved(self):
        self.assertIn('markMemoryTaskDoneById(task.id)', self.source)
        self.assertIn('deleteMemoryTask(task.id)', self.source)
        self.assertIn('reopenMemoryTask(task.id)', self.source)
        self.assertIn('clearCompletedTasks()', self.source)
        self.assertIn('onSaveMemoryTaskDraft', self.source)

    def test_focus_and_visual_safety_paths_remain_available(self):
        self.assertIn('dispatchActiveSessionCommand({ action: \'end\' })', self.source)
        self.assertIn('getRecentFocusSessions()', self.source)
        self.assertIn('getVisualContext()', self.source)
        self.assertIn('deleteVisualObservationById(observationId)', self.source)
        self.assertIn('clearVisualContext()', self.source)

    def test_remaster_uses_scoped_styles(self):
        self.assertIn("import './MemoryOverlay.css';", self.source)
        self.assertIn('.memory-remaster-overview', self.css)
        self.assertIn('.memory-remaster-details', self.css)
        self.assertIn('.memory-remaster-focus-card', self.css)


if __name__ == '__main__':
    unittest.main()
