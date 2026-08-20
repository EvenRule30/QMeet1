import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MEMORY_OVERLAY_PATH = REPO_ROOT / "src" / "app" / "panels" / "MemoryOverlay.tsx"


class FocusMemoryResetControlsPhase20UTests(unittest.TestCase):
    """Compatibility coverage for the Phase 21H4 Memory remaster.

    Phase 20U established the important ownership rule: broad Memory cleanup
    must never imply ownership of canonical Focus state. Phase 21H4 removes the
    old broad-reset UI entirely and keeps only scoped task/note maintenance.
    These tests preserve the safety contract without depending on the retired
    labels and DOM structure.
    """

    @classmethod
    def setUpClass(cls):
        cls.overlay_source = MEMORY_OVERLAY_PATH.read_text(encoding="utf-8")

    def test_focus_history_is_presented_as_read_only(self):
        source = self.overlay_source
        self.assertIn("Recent Focus history", source)
        self.assertIn("getRecentFocusSessions", source)

        start = source.index("<span>Recent Focus history</span>")
        end = source.index("<span>Saved visual context</span>", start)
        history_block = source[start:end]

        self.assertNotIn("onResetRecentContextOnly", history_block)
        self.assertNotIn("deleteRecentFocus", history_block)
        self.assertNotRegex(history_block, r">\s*(?:Reset|Delete|Clear)\s*<")

    def test_broad_reset_controls_do_not_claim_to_clear_focus(self):
        source = self.overlay_source

        # Phase 21H4 intentionally removes the broad Memory-reset controls from
        # the visible panel. Canonical Active Focus and Focus history therefore
        # cannot be cleared through a generic Memory maintenance button.
        self.assertNotIn("onClick={onClearAllMemory}", source)
        self.assertNotIn("onClick={onResetRecentContextOnly}", source)

        # Focus lifecycle remains routed through the dedicated Focus command
        # path rather than through any Memory reset callback.
        self.assertIn("dispatchActiveSessionCommand({ action: 'end' })", source)
        self.assertIn("Recent Focus history", source)

    def test_scoped_task_and_note_resets_are_disabled_during_focus(self):
        source = self.overlay_source

        task_button = re.search(
            r"<button\b(?=[^>]*disabled=\{Boolean\(activeSession\)\})"
            r"(?=[^>]*onClick=\{onResetTasksOnly\})[^>]*>"
            r"\s*Reset tasks\s*</button>",
            source,
            flags=re.DOTALL,
        )
        note_button = re.search(
            r"<button\b(?=[^>]*disabled=\{Boolean\(activeSession\)\})"
            r"(?=[^>]*onClick=\{onResetNotesOnly\})[^>]*>"
            r"\s*Reset notes\s*</button>",
            source,
            flags=re.DOTALL,
        )

        self.assertIsNotNone(task_button)
        self.assertIsNotNone(note_button)
        self.assertIn(
            "Task and note resets stay disabled while a Focus is active",
            source,
        )

    def test_memory_maintenance_is_secondary_to_focus_and_tasks(self):
        source = self.overlay_source

        focus_index = source.index("Current Focus")
        tasks_index = source.index('className="memory-remaster-section-label">Tasks')
        maintenance_index = source.index("<span>Data & maintenance</span>")

        self.assertLess(focus_index, maintenance_index)
        self.assertLess(tasks_index, maintenance_index)
        self.assertIn(
            '<details className="memory-remaster-details memory-remaster-maintenance">',
            source,
        )

    def test_focus_history_has_no_mutation_controls(self):
        source = self.overlay_source
        start = source.index("<span>Recent Focus history</span>")
        end = source.index("<span>Saved visual context</span>", start)
        history_block = source[start:end]

        self.assertNotIn("<button", history_block)
        self.assertNotIn("dispatchActiveSessionCommand", history_block)
        self.assertNotIn("clearStoredActiveSession", history_block)


if __name__ == "__main__":
    unittest.main()
