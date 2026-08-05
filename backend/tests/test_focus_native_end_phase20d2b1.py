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
    NativeFocusStartRequest,
    end_focus_verified,
    get_native_focus_lifecycle_health,
    reset_native_focus_lifecycle_health,
    start_focus_verified,
)
from app.focus.models import FocusEventType, FocusStatus


class NativeFocusEndPhase20D2B1Tests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        root = Path(self._temp_dir.name)
        self._previous_focus_file = os.environ.get("QMEET_FOCUS_FILE")
        self._previous_health_file = os.environ.get(
            "QMEET_FOCUS_LIFECYCLE_HEALTH_FILE"
        )
        os.environ["QMEET_FOCUS_FILE"] = str(root / "qmeet_focus.json")
        os.environ["QMEET_FOCUS_LIFECYCLE_HEALTH_FILE"] = str(
            root / "qmeet_focus_lifecycle_health.json"
        )
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
            os.environ[
                "QMEET_FOCUS_LIFECYCLE_HEALTH_FILE"
            ] = self._previous_health_file
        self._temp_dir.cleanup()

    def _start(self, *, turn_id: str = "turn-start"):
        return start_focus_verified(
            NativeFocusStartRequest(
                title="Treehouse planning",
                objective="Choose the building materials",
                mode="planning",
                tags=[],
                sourceTurnId=turn_id,
            )
        )

    def _end(
        self,
        focus_id: str,
        *,
        disposition: str = "ended",
        turn_id: str = "turn-end",
    ):
        return end_focus_verified(
            NativeFocusEndRequest(
                expectedFocusId=focus_id,
                disposition=disposition,
                sourceTurnId=turn_id,
            )
        )

    def test_end_closes_the_only_open_focus_and_verifies_history(self) -> None:
        started = self._start()

        result = self._end(started.activeFocus.focusId)

        self.assertTrue(result.ok)
        self.assertTrue(result.verified)
        self.assertEqual(result.outcome, "ended")
        self.assertEqual(result.disposition, "ended")
        self.assertEqual(result.closedFocus.focusId, started.activeFocus.focusId)
        self.assertEqual(result.closedFocus.status, FocusStatus.INACTIVE)
        self.assertEqual(result.verification.openFocusIds, [])
        self.assertTrue(result.verification.focusIdentityPreserved)
        self.assertTrue(result.verification.terminalStatusMatches)
        self.assertTrue(result.verification.noFocusOpen)
        self.assertTrue(result.verification.terminalEventPersisted)
        self.assertEqual(focus_store.get_state().status, FocusStatus.INACTIVE)
        self.assertIn("Ended Focus", result.message)

        terminal_events = [
            event
            for event in focus_store.list_events(limit=100)
            if event.type == FocusEventType.FOCUS_ENDED
            and event.payload.get("nativeOperation") == "end_focus"
        ]
        self.assertEqual(len(terminal_events), 1)

    def test_complete_uses_completed_event_and_complete_status(self) -> None:
        started = self._start()

        result = self._end(
            started.activeFocus.focusId,
            disposition="completed",
            turn_id="turn-complete",
        )

        self.assertEqual(result.outcome, "completed")
        self.assertEqual(result.disposition, "completed")
        self.assertEqual(result.closedFocus.status, FocusStatus.COMPLETE)
        self.assertIn("Completed Focus", result.message)
        terminal_events = [
            event
            for event in focus_store.list_events(limit=100)
            if event.type == FocusEventType.FOCUS_COMPLETED
            and event.sourceTurnId == "turn-complete"
        ]
        self.assertEqual(len(terminal_events), 1)

    def test_same_source_turn_is_idempotent(self) -> None:
        started = self._start()
        first = self._end(
            started.activeFocus.focusId,
            turn_id="turn-idempotent-end",
        )
        second = self._end(
            started.activeFocus.focusId,
            turn_id="turn-idempotent-end",
        )

        self.assertEqual(first.outcome, "ended")
        self.assertEqual(second.outcome, "reused")
        self.assertTrue(second.verified)
        terminal_events = [
            event
            for event in focus_store.list_events(limit=100)
            if event.sourceTurnId == "turn-idempotent-end"
            and event.payload.get("nativeOperation") == "end_focus"
        ]
        self.assertEqual(len(terminal_events), 1)

    def test_same_source_turn_with_different_disposition_is_conflict(self) -> None:
        started = self._start()
        self._end(
            started.activeFocus.focusId,
            disposition="ended",
            turn_id="turn-terminal-conflict",
        )

        with self.assertRaises(NativeFocusLifecycleError) as caught:
            self._end(
                started.activeFocus.focusId,
                disposition="completed",
                turn_id="turn-terminal-conflict",
            )

        self.assertEqual(caught.exception.code, "source_turn_conflict")
        self.assertNotIn("Completed Focus", caught.exception.message)
        self.assertEqual(focus_store.get_state().status, FocusStatus.INACTIVE)

    def test_stale_focus_id_is_blocked(self) -> None:
        started = self._start()

        with self.assertRaises(NativeFocusLifecycleError) as caught:
            self._end(
                "focus-stale-browser-projection",
                turn_id="turn-stale-end",
            )

        self.assertEqual(caught.exception.code, "stale_focus")
        self.assertEqual(focus_store.get_state().focusId, started.activeFocus.focusId)
        self.assertNotIn("Ended Focus", caught.exception.message)

    def test_no_active_focus_is_blocked(self) -> None:
        with self.assertRaises(NativeFocusLifecycleError) as caught:
            self._end("focus-missing", turn_id="turn-no-active-end")

        self.assertEqual(caught.exception.code, "no_active_focus")
        self.assertNotIn("Ended Focus", caught.exception.message)
        self.assertEqual(focus_store.list_events(limit=100), [])

    def test_forced_write_failure_leaves_focus_open(self) -> None:
        started = self._start()
        with patch.object(
            focus_store,
            "_atomic_write_unlocked",
            side_effect=focus_store.FocusStoreError("forced write failure"),
        ):
            with self.assertRaises(NativeFocusLifecycleError) as caught:
                self._end(
                    started.activeFocus.focusId,
                    turn_id="turn-end-write-failure",
                )

        self.assertEqual(caught.exception.code, "write_failed")
        current = focus_store.get_state()
        self.assertEqual(current.focusId, started.activeFocus.focusId)
        self.assertNotIn(current.status, {FocusStatus.INACTIVE, FocusStatus.COMPLETE})

    def test_failed_postcondition_blocks_write_and_success_wording(self) -> None:
        from app.focus import lifecycle

        started = self._start()
        original_verifier = lifecycle._verify_end_postcondition

        def fail_verification(**kwargs):
            result = original_verifier(**kwargs)
            result.noFocusOpen = False
            result.details.append("forced verification failure")
            return result

        with patch.object(
            lifecycle,
            "_verify_end_postcondition",
            side_effect=fail_verification,
        ):
            with self.assertRaises(NativeFocusLifecycleError) as caught:
                self._end(
                    started.activeFocus.focusId,
                    turn_id="turn-end-verification-failure",
                )

        self.assertEqual(caught.exception.code, "verification_failed")
        self.assertNotIn("Ended Focus", caught.exception.message)
        current = focus_store.get_state()
        self.assertEqual(current.focusId, started.activeFocus.focusId)
        self.assertNotIn(current.status, {FocusStatus.INACTIVE, FocusStatus.COMPLETE})

    def test_health_aggregates_terminal_outcomes(self) -> None:
        first = self._start(turn_id="turn-health-start-1")
        self._end(first.activeFocus.focusId, turn_id="turn-health-end")
        second = self._start(turn_id="turn-health-start-2")
        self._end(
            second.activeFocus.focusId,
            disposition="completed",
            turn_id="turn-health-complete",
        )

        health = get_native_focus_lifecycle_health()["endFocus"]
        self.assertEqual(health["attemptCount"], 2)
        self.assertEqual(health["endedCount"], 1)
        self.assertEqual(health["completedCount"], 1)
        self.assertEqual(health["verifiedCount"], 2)
        self.assertEqual(health["failedCount"], 0)
        self.assertEqual(health["lastDisposition"], "completed")


if __name__ == "__main__":
    unittest.main()
