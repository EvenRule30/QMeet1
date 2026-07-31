from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.focus import store as focus_store
from app.focus.lifecycle import (
    NativeFocusLifecycleError,
    NativeFocusStartRequest,
    get_native_focus_lifecycle_health,
    reset_native_focus_lifecycle_health,
    start_focus_verified,
)
from app.focus.models import FocusEventType, FocusStatus


class NativeFocusStartPhase20D1Tests(unittest.TestCase):
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

    def _request(
        self,
        title: str,
        turn_id: str,
        *,
        objective: str = "",
    ) -> NativeFocusStartRequest:
        return NativeFocusStartRequest(
            title=title,
            objective=objective,
            mode="work",
            sourceTurnId=turn_id,
        )

    def test_starts_first_focus_and_verifies_canonical_state(self) -> None:
        result = start_focus_verified(
            self._request(
                "Finish Phase 20D1",
                "turn-start-first",
                objective="Make Focus start backend-native.",
            )
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.verified)
        self.assertEqual(result.outcome, "started")
        self.assertEqual(result.previousFocusId, "")
        self.assertEqual(result.activeFocus.title, "Finish Phase 20D1")
        self.assertEqual(result.activeFocus.status, FocusStatus.CLARIFYING)
        self.assertTrue(result.verification.activeFocusMatches)
        self.assertTrue(result.verification.exactlyOneFocusOpen)
        self.assertEqual(
            result.verification.openFocusIds,
            [result.activeFocus.focusId],
        )
        self.assertIn("Started Focus", result.message)

    def test_replaces_open_focus_and_closes_previous_focus_once(self) -> None:
        first = start_focus_verified(
            self._request("First Focus", "turn-first")
        )
        second = start_focus_verified(
            self._request("Second Focus", "turn-second")
        )

        self.assertTrue(second.verified)
        self.assertEqual(second.outcome, "replaced")
        self.assertEqual(second.previousFocusId, first.activeFocus.focusId)
        self.assertEqual(second.closedFocusIds, [first.activeFocus.focusId])
        self.assertNotEqual(second.activeFocus.focusId, first.activeFocus.focusId)
        self.assertEqual(
            second.verification.openFocusIds,
            [second.activeFocus.focusId],
        )

        matching_end_events = [
            event
            for event in focus_store.list_events(limit=100)
            if event.type == FocusEventType.FOCUS_ENDED
            and event.focusId == first.activeFocus.focusId
            and event.payload.get("newFocusId") == second.activeFocus.focusId
        ]
        self.assertEqual(len(matching_end_events), 1)
        self.assertIn("previous Focus was moved to history", second.message)

    def test_same_source_turn_is_idempotent(self) -> None:
        first = start_focus_verified(
            self._request("Idempotent Focus", "turn-idempotent")
        )
        second = start_focus_verified(
            self._request("Idempotent Focus", "turn-idempotent")
        )

        self.assertEqual(second.outcome, "reused")
        self.assertTrue(second.verified)
        self.assertEqual(second.activeFocus.focusId, first.activeFocus.focusId)
        starts = [
            event
            for event in focus_store.list_events(limit=100)
            if event.type == FocusEventType.FOCUS_STARTED
            and event.sourceTurnId == "turn-idempotent"
        ]
        self.assertEqual(len(starts), 1)

    def test_source_turn_conflict_cannot_claim_success(self) -> None:
        start_focus_verified(
            self._request("Original Focus", "turn-conflict")
        )

        with self.assertRaises(NativeFocusLifecycleError) as caught:
            start_focus_verified(
                self._request("Different Focus", "turn-conflict")
            )

        self.assertEqual(caught.exception.code, "source_turn_conflict")
        self.assertNotIn("Started", caught.exception.message)
        self.assertEqual(focus_store.get_state().title, "Original Focus")

    def test_forced_write_failure_leaves_canonical_state_unchanged(self) -> None:
        original = start_focus_verified(
            self._request("Stable Focus", "turn-stable")
        )

        with patch.object(
            focus_store,
            "_atomic_write_unlocked",
            side_effect=focus_store.FocusStoreError("forced write failure"),
        ):
            with self.assertRaises(NativeFocusLifecycleError) as caught:
                start_focus_verified(
                    self._request("Should Not Start", "turn-write-failure")
                )

        self.assertEqual(caught.exception.code, "write_failed")
        current = focus_store.get_state()
        self.assertEqual(current.focusId, original.activeFocus.focusId)
        self.assertEqual(current.title, "Stable Focus")

    def test_failed_postcondition_blocks_write_and_success_wording(self) -> None:
        from app.focus import lifecycle

        original_verifier = lifecycle._verify_postcondition

        def fail_verification(**kwargs):
            result = original_verifier(**kwargs)
            result.exactlyOneFocusOpen = False
            result.details.append("forced verification failure")
            return result

        with patch.object(
            lifecycle,
            "_verify_postcondition",
            side_effect=fail_verification,
        ):
            with self.assertRaises(NativeFocusLifecycleError) as caught:
                start_focus_verified(
                    self._request("Unverified Focus", "turn-verification-failure")
                )

        self.assertEqual(caught.exception.code, "verification_failed")
        self.assertNotIn("Started", caught.exception.message)
        self.assertEqual(focus_store.get_state().status, FocusStatus.INACTIVE)
        self.assertFalse(
            any(
                event.type == FocusEventType.FOCUS_STARTED
                for event in focus_store.list_events(limit=100)
            )
        )

    def test_health_is_aggregated_and_persists(self) -> None:
        start_focus_verified(self._request("First", "turn-health-1"))
        start_focus_verified(self._request("Second", "turn-health-2"))

        health = get_native_focus_lifecycle_health()
        summary = health["startFocus"]
        self.assertEqual(summary["attemptCount"], 2)
        self.assertEqual(summary["startedCount"], 1)
        self.assertEqual(summary["replacedCount"], 1)
        self.assertEqual(summary["verifiedCount"], 2)
        self.assertEqual(summary["failedCount"], 0)

        reloaded = get_native_focus_lifecycle_health()
        self.assertEqual(reloaded["startFocus"], summary)


if __name__ == "__main__":
    unittest.main()
