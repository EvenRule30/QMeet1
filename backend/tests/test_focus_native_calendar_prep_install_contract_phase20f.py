from __future__ import annotations

import re
import unittest
from pathlib import Path


class NativeCalendarFocusPrepInstallContractPhase20FTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.backend_root = Path(__file__).resolve().parents[1]
        repository_root = cls.backend_root.parent
        cls.calendar_prep = (
            cls.backend_root / "app" / "focus" / "calendar_prep.py"
        ).read_text(encoding="utf-8")
        cls.ownership = (
            cls.backend_root / "app" / "focus" / "ownership.py"
        ).read_text(encoding="utf-8")
        cls.router = (
            cls.backend_root / "app" / "routers" / "focus_lifecycle.py"
        ).read_text(encoding="utf-8")
        cls.memory = (
            repository_root / "src" / "app" / "commandHandlers" / "memory.ts"
        ).read_text(encoding="utf-8")
        cls.client = (
            repository_root / "src" / "app" / "lib" / "nativeCalendarFocusPrep.ts"
        ).read_text(encoding="utf-8")

    def test_backend_exposes_one_verified_combined_calendar_transaction(self) -> None:
        self.assertIn("class NativeCalendarFocusPrepRequest", self.calendar_prep)
        self.assertIn("def prepare_calendar_focus_verified", self.calendar_prep)
        self.assertIn("start_focus_verified", self.calendar_prep)
        self.assertIn("link_focus_tasks_verified", self.calendar_prep)
        self.assertIn("focus_before =", self.calendar_prep)
        self.assertIn("memory_before =", self.calendar_prep)
        self.assertIn("relationships_before =", self.calendar_prep)
        self.assertIn("_restore_transaction_unlocked", self.calendar_prep)
        self.assertIn("rollbackProtected", self.calendar_prep)
        self.assertIn('@router.post("/calendar-prep"', self.router)
        self.assertIn('"prepare_calendar_focus"', self.router)

    def test_combined_backend_requires_every_proof(self) -> None:
        for proof in (
            "focusReceiptVerified",
            "taskReceiptVerified",
            "activeFocusMatches",
            "exactTasksPersisted",
            "relationshipPersisted",
            "sourceTurnUnique",
            "rollbackProtected",
        ):
            self.assertIn(proof, self.calendar_prep)
        self.assertIn("_count_start_events(source_turn_id) == 1", self.calendar_prep)
        self.assertIn("_count_task_receipts(source_turn_id) == 1", self.calendar_prep)

    def test_frontend_independently_requires_nested_and_combined_proofs(self) -> None:
        self.assertIn("/api/focus/lifecycle/calendar-prep", self.client)
        self.assertIn("isVerifiedNativeFocusStartResult", self.client)
        self.assertIn("validateTaskReceipt", self.client)
        for proof in (
            "verification?.focusReceiptVerified === true",
            "verification?.taskReceiptVerified === true",
            "verification?.activeFocusMatches === true",
            "verification?.exactTasksPersisted === true",
            "verification?.relationshipPersisted === true",
            "verification?.sourceTurnUnique === true",
            "verification?.rollbackProtected === true",
        ):
            self.assertIn(proof, self.client)
        self.assertIn("exactTitles", self.client)
        self.assertIn("exactMemory", self.client)
        self.assertIn("createdIdsBelongToReceipt", self.client)
        self.assertIn("calendarEventMatchesExpected", self.client)
        self.assertIn("createCalendarPrepSourceTurnId", self.client)
        self.assertIn("stableCalendarFingerprint", self.client)

    def test_memory_wrapper_owns_calendar_prep_before_quarantine_and_fallback(self) -> None:
        native_position = self.memory.index(
            "if (commandMatch.command === 'prepare-calendar-focus')"
        )
        quarantine_position = self.memory.index(
            "RETIRED_LEGACY_FOCUS_OWNERSHIP_COMMANDS.has(commandMatch.command)"
        )
        fallback_match = re.search(
            r"return\s+(?:await\s+)?handleMemoryCommandCore\s*\(\s*"
            r"commandMatch\s*,\s*deps\s*,?\s*\)\s*;",
            self.memory,
        )
        self.assertIsNotNone(fallback_match)
        assert fallback_match is not None
        self.assertLess(native_position, quarantine_position)
        self.assertLess(quarantine_position, fallback_match.start())
        self.assertIn("prepareNextCalendarFocusVerified", self.memory)
        self.assertIn("applyVerifiedCalendarFocusPrepProjection", self.memory)
        self.assertIn("'prepare-calendar-focus',", self.memory)

    def test_native_calendar_handler_does_not_create_browser_owned_ids(self) -> None:
        start = self.memory.index(
            "if (commandMatch.command === 'prepare-calendar-focus')"
        )
        end = self.memory.index(
            "if (commandMatch.command === 'focus-to-tasks')"
        )
        handler = self.memory[start:end]
        for retired_write in (
            "replaceActiveSession",
            "replaceMemoryTasks",
            "saveMemoryTask",
            "Math.random",
            "localStorage",
            "qmeet-calendar-focus-prep-command",
        ):
            self.assertNotIn(retired_write, handler)
        self.assertIn("result.message", handler)
        self.assertIn("describeNativeCalendarFocusPrepFailure", handler)

    def test_ownership_readiness_aggregates_every_native_write_surface(self) -> None:
        self.assertIn("class NativeFocusOwnershipReadiness", self.ownership)
        for operation in (
            '"start_focus"',
            '"update_focus"',
            '"end_focus"',
            '"resume_focus"',
            '"save_focus_summary"',
            '"link_focus_tasks"',
            '"prepare_calendar_focus"',
        ):
            self.assertIn(operation, self.ownership)
        self.assertIn("readyForLegacyProjectionRetirement", self.ownership)
        self.assertIn("remainingBrowserOwnedWriteSurfaces=[]", self.ownership)
        self.assertIn('"prepare-calendar-focus"', self.ownership)
        self.assertIn('"/ownership-readiness"', self.router)
        self.assertIn('"ownershipReadiness"', self.router)
        self.assertIn('"calendarPrepHealth"', self.router)
        self.assertIn('"ok": True', self.router)

    def test_calendar_task_shapes_are_stable_and_backend_owned(self) -> None:
        for title_fragment in (
            "Review details for",
            "Gather relevant notes or documents for",
            "Prepare questions for",
            "Identify decisions or next steps needed for",
            "Capture follow-up items after",
        ):
            self.assertIn(title_fragment, self.calendar_prep)
            self.assertIn(title_fragment, self.client)
        self.assertNotIn("id: createId('task')", self.client)
        self.assertNotIn("id: `session-", self.client)
        self.assertNotIn("Math.random", self.client)
        self.assertNotIn("crypto.randomUUID", self.client)


if __name__ == "__main__":
    unittest.main()
