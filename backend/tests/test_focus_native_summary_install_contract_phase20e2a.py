from __future__ import annotations

import unittest
from pathlib import Path


class NativeFocusSummaryInstallContractPhase20E2ATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.backend_root = Path(__file__).resolve().parents[1]
        cls.summary = (
            cls.backend_root / "app" / "focus" / "summary.py"
        ).read_text(encoding="utf-8")
        cls.router = (
            cls.backend_root / "app" / "routers" / "focus_lifecycle.py"
        ).read_text(encoding="utf-8")
        repository_root = cls.backend_root.parent
        cls.memory = (
            repository_root / "src" / "app" / "commandHandlers" / "memory.ts"
        ).read_text(encoding="utf-8")
        cls.client = (
            repository_root / "src" / "app" / "lib" / "nativeFocusSummary.ts"
        ).read_text(encoding="utf-8")
        cls.app = (
            repository_root / "src" / "app" / "App.tsx"
        ).read_text(encoding="utf-8")

    def test_backend_exposes_verified_summary_receipt(self) -> None:
        self.assertIn("class NativeFocusSummaryRequest", self.summary)
        self.assertIn("def save_focus_summary_verified", self.summary)
        self.assertIn("activeFocusMatches", self.summary)
        self.assertIn("notePersisted", self.summary)
        self.assertIn("relationshipPersisted", self.summary)
        self.assertIn("sourceTurnUnique", self.summary)
        self.assertIn('@router.post("/summary"', self.router)
        self.assertIn('"save_focus_summary"', self.router)

    def test_frontend_requires_all_canonical_proofs(self) -> None:
        self.assertIn("/api/focus/lifecycle/summary", self.client)
        self.assertIn("verification?.activeFocusMatches === true", self.client)
        self.assertIn("verification?.notePersisted === true", self.client)
        self.assertIn("verification?.relationshipPersisted === true", self.client)
        self.assertIn("verification?.sourceTurnUnique === true", self.client)
        self.assertIn("applyVerifiedFocusSummaryProjection", self.client)

    def test_memory_wrapper_owns_summary_before_legacy_fallback(self) -> None:
        native_position = self.memory.index(
            "if (commandMatch.command === 'save-focus-summary')"
        )
        fallback_position = self.memory.index(
            "return handleMemoryCommandCore(commandMatch, deps);"
        )
        self.assertLess(native_position, fallback_position)
        self.assertIn("saveNativeFocusSummaryVerified", self.memory)
        self.assertIn("deps.deleteNote(note.id)", self.memory)
        self.assertIn("'save-focus-summary',", self.memory)

    def test_app_supplies_note_staging_and_rollback_dependencies(self) -> None:
        call_position = self.app.index("await handleMemoryCommand(commandMatch")
        call_window = self.app[call_position : call_position + 600]
        self.assertIn("saveNote,", call_window)
        self.assertIn("deleteNote,", call_window)

    def test_summary_success_is_not_authored_by_legacy_core(self) -> None:
        self.assertIn(
            "I could not verify that the Focus summary Note",
            self.client,
        )
        self.assertIn("result.message", self.memory)
        self.assertNotIn("dispatchFocusSummaryNote(activeSession, summary)", self.memory)


if __name__ == "__main__":
    unittest.main()
