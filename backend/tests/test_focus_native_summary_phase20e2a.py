from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import memory_store
from app.focus import store as focus_store
from app.focus.lifecycle import NativeFocusStartRequest, start_focus_verified
from app.focus.summary import (
    NativeFocusSummaryError,
    NativeFocusSummaryNote,
    NativeFocusSummaryRequest,
    NativeFocusSummaryVerification,
    get_native_focus_summary_health,
    reset_native_focus_summary_health,
    save_focus_summary_verified,
)


class NativeFocusSummaryPhase20E2ATests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        root = Path(self._temp_dir.name)
        self._previous = {
            name: os.environ.get(name)
            for name in (
                "QMEET_FOCUS_FILE",
                "QMEET_FOCUS_LIFECYCLE_HEALTH_FILE",
                "QMEET_FOCUS_RELATIONSHIPS_FILE",
                "QMEET_FOCUS_SUMMARY_HEALTH_FILE",
            )
        }
        os.environ["QMEET_FOCUS_FILE"] = str(root / "qmeet_focus.json")
        os.environ["QMEET_FOCUS_LIFECYCLE_HEALTH_FILE"] = str(
            root / "qmeet_focus_lifecycle_health.json"
        )
        os.environ["QMEET_FOCUS_RELATIONSHIPS_FILE"] = str(
            root / "qmeet_focus_relationships.json"
        )
        os.environ["QMEET_FOCUS_SUMMARY_HEALTH_FILE"] = str(
            root / "qmeet_focus_summary_health.json"
        )
        self._memory_path = root / "qmeet_memory.json"
        self._memory_file_patcher = patch.object(
            memory_store,
            "_memory_file",
            return_value=self._memory_path,
        )
        self._memory_file_patcher.start()
        focus_store.reset_store()
        reset_native_focus_summary_health()
        self._start = start_focus_verified(
            NativeFocusStartRequest(
                title="Plan a vacation",
                objective="Choose dates and destination",
                mode="planning",
                tags=[],
                sourceTurnId="start-summary-focus",
            )
        )

    def tearDown(self) -> None:
        self._memory_file_patcher.stop()
        for name, value in self._previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self._temp_dir.cleanup()

    def _request(
        self,
        *,
        turn: str = "summary-turn",
        note_id: str = "note-summary-one",
        content: str = "Focus summary for Plan a vacation.",
    ) -> NativeFocusSummaryRequest:
        return NativeFocusSummaryRequest(
            expectedFocusId=self._start.activeFocus.focusId,
            note=NativeFocusSummaryNote(
                id=note_id,
                content=content,
                createdAt="2026-08-05T10:00:00-07:00",
            ),
            sourceTurnId=turn,
        )

    def test_saves_exact_note_and_verified_focus_relationship(self) -> None:
        result = save_focus_summary_verified(self._request())

        self.assertTrue(result.ok)
        self.assertTrue(result.verified)
        self.assertEqual(result.outcome, "saved")
        self.assertEqual(result.focusId, self._start.activeFocus.focusId)
        self.assertEqual(result.note.id, "note-summary-one")
        self.assertTrue(result.verification.activeFocusMatches)
        self.assertTrue(result.verification.notePersisted)
        self.assertTrue(result.verification.relationshipPersisted)
        self.assertTrue(result.verification.sourceTurnUnique)
        notes = memory_store.list_memory_notes()["notes"]
        self.assertEqual(notes[0]["id"], "note-summary-one")
        self.assertEqual(notes[0]["content"], result.summary)
        self.assertIn("Saved Focus summary", result.message)

    def test_same_source_turn_and_note_is_idempotent(self) -> None:
        first = save_focus_summary_verified(self._request())
        second = save_focus_summary_verified(self._request())

        self.assertEqual(first.outcome, "saved")
        self.assertEqual(second.outcome, "reused")
        self.assertEqual(first.receiptId, second.receiptId)
        notes = memory_store.list_memory_notes()["notes"]
        self.assertEqual(len(notes), 1)

    def test_same_source_turn_with_different_note_is_conflict(self) -> None:
        save_focus_summary_verified(self._request())
        with self.assertRaises(NativeFocusSummaryError) as caught:
            save_focus_summary_verified(
                self._request(note_id="note-summary-two")
            )
        self.assertEqual(caught.exception.code, "source_turn_conflict")
        self.assertEqual(len(memory_store.list_memory_notes()["notes"]), 1)

    def test_stale_focus_is_rejected_before_note_write(self) -> None:
        replacement = start_focus_verified(
            NativeFocusStartRequest(
                title="Prepare quarterly review",
                objective="Finish the review deck",
                mode="planning",
                tags=[],
                sourceTurnId="replace-before-summary",
            )
        )
        self.assertNotEqual(
            replacement.activeFocus.focusId,
            self._start.activeFocus.focusId,
        )
        with self.assertRaises(NativeFocusSummaryError) as caught:
            save_focus_summary_verified(self._request())
        self.assertEqual(caught.exception.code, "stale_focus")
        self.assertEqual(memory_store.list_memory_notes()["notes"], [])

    def test_existing_note_id_with_different_content_is_rejected(self) -> None:
        with memory_store._STORE_LOCK:
            before = memory_store._read_payload_unlocked()
            memory_store._write_payload_unlocked(
                before["tasks"],
                before["recentActions"],
                [
                    {
                        "id": "note-summary-one",
                        "content": "Different content",
                        "createdAt": "2026-08-05T10:00:00-07:00",
                    }
                ],
                before["activeSession"],
                before["recentFocusSessions"],
                before["visualContext"],
                preserve_active_session=False,
                preserve_recent_focus_sessions=False,
                preserve_visual_context=False,
            )
        with self.assertRaises(NativeFocusSummaryError) as caught:
            save_focus_summary_verified(self._request())
        self.assertEqual(caught.exception.code, "note_id_conflict")
        self.assertEqual(
            memory_store.list_memory_notes()["notes"][0]["content"],
            "Different content",
        )

    def test_relationship_write_failure_rolls_back_new_note(self) -> None:
        from app.focus import summary as summary_module

        original_write = summary_module._write_relationships_unlocked
        calls = 0

        def fail_first_write(document):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("forced relationship write failure")
            return original_write(document)

        with patch.object(
            summary_module,
            "_write_relationships_unlocked",
            side_effect=fail_first_write,
        ):
            with self.assertRaises(NativeFocusSummaryError) as caught:
                save_focus_summary_verified(self._request())

        self.assertEqual(caught.exception.code, "write_failed")
        self.assertEqual(memory_store.list_memory_notes()["notes"], [])

    def test_failed_postcondition_rolls_back_note_and_relationship(self) -> None:
        from app.focus import summary as summary_module

        failed = NativeFocusSummaryVerification(
            activeFocusMatches=True,
            notePersisted=True,
            relationshipPersisted=False,
            sourceTurnUnique=True,
            details=["forced verification failure"],
        )
        with patch.object(summary_module, "_verify_summary", return_value=failed):
            with self.assertRaises(NativeFocusSummaryError) as caught:
                save_focus_summary_verified(self._request())

        self.assertEqual(caught.exception.code, "verification_failed")
        self.assertEqual(memory_store.list_memory_notes()["notes"], [])
        relationship_path = Path(os.environ["QMEET_FOCUS_RELATIONSHIPS_FILE"])
        relationship_document = (
            relationship_path.read_text(encoding="utf-8")
            if relationship_path.exists()
            else ""
        )
        self.assertNotIn("note-summary-one", relationship_document)

    def test_health_is_aggregated_and_persistent(self) -> None:
        save_focus_summary_verified(self._request())
        save_focus_summary_verified(self._request())
        health = get_native_focus_summary_health()["saveFocusSummary"]
        self.assertEqual(health["attemptCount"], 2)
        self.assertEqual(health["savedCount"], 1)
        self.assertEqual(health["reusedCount"], 1)
        self.assertEqual(health["verifiedCount"], 2)
        self.assertEqual(health["lastNoteId"], "note-summary-one")


if __name__ == "__main__":
    unittest.main()
