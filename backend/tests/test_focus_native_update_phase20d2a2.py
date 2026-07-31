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
    NativeFocusUpdateRequest,
    get_native_focus_lifecycle_health,
    reset_native_focus_lifecycle_health,
    start_focus_verified,
    update_focus_verified,
)
from app.focus.models import FocusEventType


class NativeFocusUpdatePhase20D2ATests(unittest.TestCase):
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

    def _start(
        self,
        *,
        title: str = "Initial Focus",
        objective: str = "Initial goal",
        mode: str = "general",
        tags: list[str] | None = None,
        turn_id: str = "turn-start",
    ):
        return start_focus_verified(
            NativeFocusStartRequest(
                title=title,
                objective=objective,
                mode=mode,
                tags=tags or [],
                sourceTurnId=turn_id,
            )
        )

    def _update(
        self,
        focus_id: str,
        turn_id: str,
        **changes,
    ):
        return update_focus_verified(
            NativeFocusUpdateRequest(
                expectedFocusId=focus_id,
                sourceTurnId=turn_id,
                **changes,
            )
        )

    def test_updates_title_objective_and_mode_without_changing_focus_id(self) -> None:
        started = self._start()

        result = self._update(
            started.activeFocus.focusId,
            "turn-update-all",
            title="Reframed Focus",
            objective="Ship verified native updates",
            mode="coding",
        )

        self.assertTrue(result.ok)
        self.assertTrue(result.verified)
        self.assertEqual(result.outcome, "updated")
        self.assertEqual(result.activeFocus.focusId, started.activeFocus.focusId)
        self.assertEqual(result.activeFocus.title, "Reframed Focus")
        self.assertEqual(
            result.activeFocus.objective,
            "Ship verified native updates",
        )
        self.assertEqual(result.changedFields, ["title", "objective", "mode"])
        self.assertEqual(
            [tag for tag in result.activeFocus.tags if tag.startswith("mode:")],
            ["mode:coding"],
        )
        self.assertTrue(result.verification.focusIdentityPreserved)
        self.assertTrue(result.verification.exactlyOneFocusOpen)
        self.assertTrue(result.verification.updateEventsPersisted)
        self.assertEqual(
            result.verification.openFocusIds,
            [started.activeFocus.focusId],
        )
        self.assertIn("Updated Focus", result.message)

    def test_clears_objective_without_replacing_focus(self) -> None:
        started = self._start(objective="Temporary goal")

        result = self._update(
            started.activeFocus.focusId,
            "turn-clear-objective",
            objective="",
        )

        self.assertEqual(result.outcome, "updated")
        self.assertEqual(result.changedFields, ["objective"])
        self.assertEqual(result.activeFocus.objective, "")
        self.assertEqual(result.activeFocus.focusId, started.activeFocus.focusId)

    def test_same_source_turn_is_idempotent(self) -> None:
        started = self._start()
        first = self._update(
            started.activeFocus.focusId,
            "turn-idempotent-update",
            title="Idempotent Focus",
            mode="planning",
        )
        second = self._update(
            started.activeFocus.focusId,
            "turn-idempotent-update",
            title="Idempotent Focus",
            mode="planning",
        )

        self.assertEqual(first.outcome, "updated")
        self.assertEqual(second.outcome, "reused")
        self.assertTrue(second.verified)
        update_events = [
            event
            for event in focus_store.list_events(limit=100)
            if event.sourceTurnId == "turn-idempotent-update"
            and event.payload.get("nativeOperation") == "update_focus"
        ]
        self.assertEqual(len(update_events), 3)

    def test_same_mode_request_repairs_duplicate_mode_tags(self) -> None:
        started = self._start(
            mode="coding",
            tags=["mode:general", "phase:20d2a"],
        )
        self.assertEqual(
            len([tag for tag in started.activeFocus.tags if tag.startswith("mode:")]),
            2,
        )

        result = self._update(
            started.activeFocus.focusId,
            "turn-repair-mode-tags",
            mode="coding",
        )

        self.assertEqual(result.outcome, "updated")
        self.assertEqual(result.changedFields, ["mode"])
        self.assertEqual(
            [tag for tag in result.activeFocus.tags if tag.startswith("mode:")],
            ["mode:coding"],
        )

    def test_source_turn_conflict_cannot_claim_success(self) -> None:
        started = self._start()
        self._update(
            started.activeFocus.focusId,
            "turn-update-conflict",
            title="First Update",
        )

        with self.assertRaises(NativeFocusLifecycleError) as caught:
            self._update(
                started.activeFocus.focusId,
                "turn-update-conflict",
                title="Different Update",
            )

        self.assertEqual(caught.exception.code, "source_turn_conflict")
        self.assertNotIn("Updated Focus", caught.exception.message)
        self.assertEqual(focus_store.get_state().title, "First Update")

    def test_stale_focus_id_is_blocked(self) -> None:
        started = self._start()

        with self.assertRaises(NativeFocusLifecycleError) as caught:
            self._update(
                "focus-stale-browser-projection",
                "turn-stale-focus",
                title="Must Not Apply",
            )

        self.assertEqual(caught.exception.code, "stale_focus")
        self.assertEqual(focus_store.get_state().focusId, started.activeFocus.focusId)
        self.assertEqual(focus_store.get_state().title, "Initial Focus")

    def test_no_active_focus_is_blocked(self) -> None:
        with self.assertRaises(NativeFocusLifecycleError) as caught:
            self._update(
                "focus-missing",
                "turn-no-active-focus",
                title="Must Not Start Locally",
            )

        self.assertEqual(caught.exception.code, "no_active_focus")
        self.assertNotIn("Updated Focus", caught.exception.message)
        self.assertEqual(focus_store.list_events(limit=100), [])

    def test_forced_write_failure_leaves_canonical_state_unchanged(self) -> None:
        started = self._start()
        with patch.object(
            focus_store,
            "_atomic_write_unlocked",
            side_effect=focus_store.FocusStoreError("forced write failure"),
        ):
            with self.assertRaises(NativeFocusLifecycleError) as caught:
                self._update(
                    started.activeFocus.focusId,
                    "turn-update-write-failure",
                    title="Should Not Persist",
                )

        self.assertEqual(caught.exception.code, "write_failed")
        current = focus_store.get_state()
        self.assertEqual(current.focusId, started.activeFocus.focusId)
        self.assertEqual(current.title, "Initial Focus")

    def test_failed_postcondition_blocks_write_and_success_wording(self) -> None:
        from app.focus import lifecycle

        started = self._start()
        original_verifier = lifecycle._verify_update_postcondition

        def fail_verification(**kwargs):
            result = original_verifier(**kwargs)
            result.titleMatches = False
            result.details.append("forced verification failure")
            return result

        with patch.object(
            lifecycle,
            "_verify_update_postcondition",
            side_effect=fail_verification,
        ):
            with self.assertRaises(NativeFocusLifecycleError) as caught:
                self._update(
                    started.activeFocus.focusId,
                    "turn-update-verification-failure",
                    title="Unverified Update",
                )

        self.assertEqual(caught.exception.code, "verification_failed")
        self.assertNotIn("Updated Focus", caught.exception.message)
        self.assertEqual(focus_store.get_state().title, "Initial Focus")
        self.assertFalse(
            any(
                event.sourceTurnId == "turn-update-verification-failure"
                and event.type == FocusEventType.FIELD_SET
                for event in focus_store.list_events(limit=100)
            )
        )

    def test_health_is_aggregated_and_persists(self) -> None:
        started = self._start()
        self._update(
            started.activeFocus.focusId,
            "turn-health-update-1",
            title="Health Update",
        )
        self._update(
            started.activeFocus.focusId,
            "turn-health-update-2",
            title="Health Update",
        )
        with self.assertRaises(NativeFocusLifecycleError):
            self._update(
                "focus-stale",
                "turn-health-update-3",
                title="Blocked",
            )

        health = get_native_focus_lifecycle_health()
        summary = health["updateFocus"]
        self.assertEqual(summary["attemptCount"], 3)
        self.assertEqual(summary["updatedCount"], 1)
        self.assertEqual(summary["reusedCount"], 1)
        self.assertEqual(summary["verifiedCount"], 2)
        self.assertEqual(summary["failedCount"], 1)
        self.assertEqual(summary["staleFocusCount"], 1)

        reloaded = get_native_focus_lifecycle_health()
        self.assertEqual(reloaded["updateFocus"], summary)


if __name__ == "__main__":
    unittest.main()
