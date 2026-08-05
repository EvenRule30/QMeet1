from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.focus import store as focus_store
from app.focus.lifecycle import (
    NativeFocusEndRequest,
    NativeFocusLifecycleError,
    NativeFocusResumeRequest,
    NativeFocusStartRequest,
    end_focus_verified,
    get_native_focus_lifecycle_health,
    reset_native_focus_lifecycle_health,
    resume_focus_verified,
    start_focus_verified,
)
from app.focus.models import FocusEventType, FocusStatus


class NativeFocusResumePhase20D2C1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        root = Path(self._temp_dir.name)
        self._previous_focus_file = os.environ.get("QMEET_FOCUS_FILE")
        self._previous_health_file = os.environ.get("QMEET_FOCUS_LIFECYCLE_HEALTH_FILE")
        os.environ["QMEET_FOCUS_FILE"] = str(root / "qmeet_focus.json")
        os.environ["QMEET_FOCUS_LIFECYCLE_HEALTH_FILE"] = str(root / "qmeet_focus_lifecycle_health.json")
        focus_store.reset_store()
        reset_native_focus_lifecycle_health()

    def tearDown(self) -> None:
        if self._previous_focus_file is None:
            os.environ.pop("QMEET_FOCUS_FILE", None)
        else:
            os.environ["QMEET_FOCUS_FILE"] = self._previous_focus_file
        if self._previous_health_file is None:
            os.environ.pop("QMEET_FOCUS_LIFECYCLE_HEALTH_FILE", None)
        else:
            os.environ["QMEET_FOCUS_LIFECYCLE_HEALTH_FILE"] = self._previous_health_file
        self._temp_dir.cleanup()

    def _start(self, title: str, *, mode: str = "general", turn: str):
        return start_focus_verified(NativeFocusStartRequest(
            title=title,
            objective=f"Goal for {title}",
            mode=mode,
            tags=[],
            sourceTurnId=turn,
        ))

    def _end(self, focus_id: str, *, completed: bool = False, turn: str):
        return end_focus_verified(NativeFocusEndRequest(
            expectedFocusId=focus_id,
            disposition="completed" if completed else "ended",
            sourceTurnId=turn,
        ))

    def _resume(self, *, mode: str | None = None, turn: str = "turn-resume"):
        return resume_focus_verified(NativeFocusResumeRequest(
            mode=mode,
            sourceTurnId=turn,
        ))

    def _append_detail_events(self, focus_id: str) -> None:
        with focus_store._STORE_LOCK:
            doc = focus_store._read_log_unlocked()
            doc.events.extend([
                focus_store._new_event(
                    FocusEventType.FIELD_SET,
                    focus_id=focus_id,
                    payload={"field": "deliverable", "value": "Study guide"},
                    source_turn_id="detail-turn",
                    source="test",
                ),
                focus_store._new_event(
                    FocusEventType.LIST_ITEM_ADDED,
                    focus_id=focus_id,
                    payload={"field": "requirements", "value": "Cover chapters 1-4"},
                    source_turn_id="detail-turn",
                    source="test",
                ),
                focus_store._new_event(
                    FocusEventType.NEXT_ACTION_SET,
                    focus_id=focus_id,
                    payload={"value": "Review chapter one"},
                    source_turn_id="detail-turn",
                    source="test",
                ),
            ])
            focus_store._atomic_write_unlocked(doc)

    def test_resumes_latest_historical_focus_with_new_identity(self) -> None:
        original = self._start("Study for exam", mode="research", turn="start-one")
        self._append_detail_events(original.activeFocus.focusId)
        self._end(original.activeFocus.focusId, turn="end-one")

        result = self._resume(turn="resume-one")

        self.assertTrue(result.ok)
        self.assertTrue(result.verified)
        self.assertEqual(result.outcome, "resumed")
        self.assertNotEqual(result.activeFocus.focusId, original.activeFocus.focusId)
        self.assertEqual(result.resumedFromFocus.focusId, original.activeFocus.focusId)
        self.assertEqual(result.activeFocus.title, "Study for exam")
        self.assertEqual(result.activeFocus.objective, "Goal for Study for exam")
        self.assertEqual(result.activeFocus.deliverable, "Study guide")
        self.assertEqual(result.activeFocus.requirements, ["Cover chapters 1-4"])
        self.assertEqual(result.activeFocus.nextAction, "Review chapter one")
        self.assertEqual(result.verification.openFocusIds, [result.activeFocus.focusId])
        self.assertTrue(result.verification.historicalFocusPreserved)
        self.assertIn("Resumed Focus", result.message)

        historical_events = [
            event for event in focus_store.list_events(limit=200)
            if event.focusId == original.activeFocus.focusId
        ]
        historical_state = focus_store.reduce_events(historical_events)
        self.assertEqual(historical_state.status, FocusStatus.INACTIVE)

    def test_completed_focus_can_be_resumed_without_changing_history(self) -> None:
        original = self._start("Finish report", mode="planning", turn="start-complete")
        self._end(original.activeFocus.focusId, completed=True, turn="complete-one")

        result = self._resume(turn="resume-completed")

        self.assertEqual(result.resumedFromFocus.status, FocusStatus.COMPLETE)
        self.assertNotIn(result.activeFocus.status, {FocusStatus.INACTIVE, FocusStatus.COMPLETE})
        source_state = focus_store.reduce_events([
            event for event in focus_store.list_events(limit=200)
            if event.focusId == original.activeFocus.focusId
        ])
        self.assertEqual(source_state.status, FocusStatus.COMPLETE)

    def test_mode_filter_selects_latest_matching_history(self) -> None:
        planning = self._start("Plan launch", mode="planning", turn="start-plan")
        self._end(planning.activeFocus.focusId, turn="end-plan")
        coding = self._start("Fix backend", mode="coding", turn="start-code")
        self._end(coding.activeFocus.focusId, turn="end-code")

        result = self._resume(mode="planning", turn="resume-plan")

        self.assertEqual(result.resumedFromFocus.focusId, planning.activeFocus.focusId)
        self.assertEqual(result.activeFocus.title, "Plan launch")
        self.assertIn("mode:planning", [tag.lower() for tag in result.activeFocus.tags])

    def test_resume_replaces_current_active_focus(self) -> None:
        historical = self._start("Garden project", turn="start-history")
        self._end(historical.activeFocus.focusId, turn="end-history")
        current = self._start("Current report", turn="start-current")

        result = self._resume(turn="resume-replace")

        self.assertEqual(result.outcome, "replaced")
        self.assertIn(current.activeFocus.focusId, result.closedFocusIds)
        self.assertEqual(focus_store.get_state().focusId, result.activeFocus.focusId)
        self.assertIn("previous active Focus", result.message)

    def test_no_history_is_blocked(self) -> None:
        with self.assertRaises(NativeFocusLifecycleError) as caught:
            self._resume(turn="resume-none")
        self.assertEqual(caught.exception.code, "no_focus_history")
        self.assertNotIn("Resumed Focus", caught.exception.message)

    def test_same_source_turn_is_idempotent(self) -> None:
        original = self._start("Review notes", turn="start-idem")
        self._end(original.activeFocus.focusId, turn="end-idem")
        first = self._resume(turn="resume-idem")
        second = self._resume(turn="resume-idem")
        self.assertEqual(first.outcome, "resumed")
        self.assertEqual(second.outcome, "reused")
        starts = [
            event for event in focus_store.list_events(limit=200)
            if event.sourceTurnId == "resume-idem"
            and event.type == FocusEventType.FOCUS_STARTED
        ]
        self.assertEqual(len(starts), 1)

    def test_same_source_turn_with_different_mode_is_conflict(self) -> None:
        original = self._start("Research topic", mode="research", turn="start-conflict")
        self._end(original.activeFocus.focusId, turn="end-conflict")
        self._resume(mode="research", turn="resume-conflict")
        with self.assertRaises(NativeFocusLifecycleError) as caught:
            self._resume(mode="planning", turn="resume-conflict")
        self.assertEqual(caught.exception.code, "source_turn_conflict")

    def test_forced_write_failure_leaves_history_closed(self) -> None:
        original = self._start("Closed focus", turn="start-write")
        self._end(original.activeFocus.focusId, turn="end-write")
        with patch.object(
            focus_store,
            "_atomic_write_unlocked",
            side_effect=focus_store.FocusStoreError("forced write failure"),
        ):
            with self.assertRaises(NativeFocusLifecycleError) as caught:
                self._resume(turn="resume-write-failure")
        self.assertEqual(caught.exception.code, "write_failed")
        self.assertEqual(focus_store.get_state().status, FocusStatus.INACTIVE)

    def test_missing_durable_restoration_is_rejected_before_write(self) -> None:
        from app.focus import lifecycle
        original = self._start("Durable history", turn="start-durable")
        self._append_detail_events(original.activeFocus.focusId)
        self._end(original.activeFocus.focusId, turn="end-durable")

        with patch.object(lifecycle, "_resume_restoration_events", return_value=[]):
            with self.assertRaises(NativeFocusLifecycleError) as caught:
                self._resume(turn="resume-missing-durable")

        self.assertEqual(caught.exception.code, "verification_failed")
        self.assertNotIn("Resumed Focus", caught.exception.message)
        self.assertEqual(focus_store.get_state().status, FocusStatus.INACTIVE)

    def test_failed_postcondition_blocks_write_and_success_wording(self) -> None:
        from app.focus import lifecycle
        original = self._start("Verify resume", turn="start-verify")
        self._end(original.activeFocus.focusId, turn="end-verify")
        original_verifier = lifecycle._verify_resume_postcondition

        def fail_verification(**kwargs):
            result = original_verifier(**kwargs)
            result.exactlyOneFocusOpen = False
            result.details.append("forced verification failure")
            return result

        with patch.object(lifecycle, "_verify_resume_postcondition", side_effect=fail_verification):
            with self.assertRaises(NativeFocusLifecycleError) as caught:
                self._resume(turn="resume-verification-failure")
        self.assertEqual(caught.exception.code, "verification_failed")
        self.assertNotIn("Resumed Focus", caught.exception.message)
        self.assertEqual(focus_store.get_state().status, FocusStatus.INACTIVE)

    def test_health_aggregates_resume_outcomes(self) -> None:
        original = self._start("Health history", turn="start-health")
        self._end(original.activeFocus.focusId, turn="end-health")
        self._resume(turn="resume-health")
        health = get_native_focus_lifecycle_health()["resumeFocus"]
        self.assertEqual(health["attemptCount"], 1)
        self.assertEqual(health["resumedCount"], 1)
        self.assertEqual(health["verifiedCount"], 1)
        self.assertEqual(health["failedCount"], 0)


if __name__ == "__main__":
    unittest.main()
