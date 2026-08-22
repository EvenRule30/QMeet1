import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
MEMORY_UI_CONTEXT_PATH = REPO_ROOT / 'src' / 'app' / 'lib' / 'memoryUiContext.ts'
MEMORY_READ_SURFACE_PATH = REPO_ROOT / 'src' / 'app' / 'lib' / 'memoryReadSurface.ts'
FOCUS_TOOL_RECEIPT_PATH = REPO_ROOT / 'src' / 'app' / 'lib' / 'focusToolReceipt.ts'
MEMORY_OVERLAY_PATH = REPO_ROOT / 'src' / 'app' / 'panels' / 'MemoryOverlay.tsx'
MEMORY_CSS_PATH = REPO_ROOT / 'src' / 'app' / 'panels' / 'MemoryOverlay.css'


class MemoryConversationUiSyncPhase21I3BTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context_source = MEMORY_UI_CONTEXT_PATH.read_text(encoding='utf-8')
        cls.read_surface_source = MEMORY_READ_SURFACE_PATH.read_text(encoding='utf-8')
        cls.focus_receipt_source = FOCUS_TOOL_RECEIPT_PATH.read_text(encoding='utf-8')
        cls.overlay_source = MEMORY_OVERLAY_PATH.read_text(encoding='utf-8')
        cls.css_source = MEMORY_CSS_PATH.read_text(encoding='utf-8')

    def test_memory_ui_context_is_tab_scoped_and_one_shot(self):
        self.assertIn("window.sessionStorage.setItem", self.context_source)
        self.assertIn("window.sessionStorage.removeItem", self.context_source)
        self.assertIn("MEMORY_UI_CONTEXT_EVENT", self.context_source)
        self.assertNotIn("window.localStorage.setItem", self.context_source)

    def test_verified_task_read_surface_targets_tasks(self):
        self.assertIn("rememberMemoryUiContext('tasks')", self.read_surface_source)
        self.assertIn("export function formatOpenTasksReadout", self.read_surface_source)
        self.assertIn("export function formatFocusTaskReadout", self.read_surface_source)

    def test_verified_focus_receipts_target_focus_without_end_focus_hijack(self):
        self.assertIn("'read-focus-session'", self.focus_receipt_source)
        self.assertIn("'summarize-focus-session'", self.focus_receipt_source)
        self.assertIn("rememberMemoryUiContext('focus')", self.focus_receipt_source)
        self.assertNotIn("'end-focus-session',", self.focus_receipt_source)

    def test_memory_overlay_consumes_context_and_scrolls_to_matching_card(self):
        self.assertIn("consumeMemoryUiContext()", self.overlay_source)
        self.assertIn("MEMORY_UI_CONTEXT_EVENT", self.overlay_source)
        self.assertIn("ref={focusCardRef}", self.overlay_source)
        self.assertIn("ref={tasksCardRef}", self.overlay_source)
        self.assertIn("scrollIntoView({ behavior: 'smooth', block: 'start' })", self.overlay_source)
        self.assertIn("memoryUiTarget === 'focus'", self.overlay_source)
        self.assertIn("memoryUiTarget === 'tasks'", self.overlay_source)

    def test_context_emphasis_is_temporary_visual_polish(self):
        self.assertIn("memory-remaster-context-target", self.css_source)
        self.assertIn("memory-remaster-context-pulse", self.css_source)
        self.assertIn("setMemoryUiTarget(null)", self.overlay_source)


if __name__ == '__main__':
    unittest.main()
