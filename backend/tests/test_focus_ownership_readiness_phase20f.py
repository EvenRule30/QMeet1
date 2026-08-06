from __future__ import annotations

import unittest
from unittest.mock import patch

from app.focus import ownership


def health_section(
    *,
    attempts: int = 1,
    verified: int = 1,
    failed: int = 0,
    outcome: str = "verified",
    failure: str = "",
) -> dict[str, object]:
    return {
        "attemptCount": attempts,
        "verifiedCount": verified,
        "failedCount": failed,
        "lastOutcome": outcome,
        "lastFailureCode": failure,
        "lastUpdatedAt": "2026-08-05T13:45:00-07:00",
    }


class NativeFocusOwnershipReadinessPhase20FTests(unittest.TestCase):
    def _patch_health(
        self,
        *,
        lifecycle: dict[str, object],
        summary: dict[str, object],
        tasks: dict[str, object],
        calendar: dict[str, object],
        context: dict[str, object],
    ):
        return (
            patch.object(
                ownership,
                "get_native_focus_lifecycle_health",
                return_value=lifecycle,
            ),
            patch.object(
                ownership,
                "get_native_focus_summary_health",
                return_value=summary,
            ),
            patch.object(
                ownership,
                "get_native_focus_task_health",
                return_value=tasks,
            ),
            patch.object(
                ownership,
                "get_native_calendar_focus_prep_health",
                return_value=calendar,
            ),
            patch.object(
                ownership,
                "get_native_focus_context_health",
                return_value=context,
            ),
        )

    def test_all_verified_operations_are_ready(self) -> None:
        verified = health_section()
        patches = self._patch_health(
            lifecycle={
                "startFocus": verified,
                "updateFocus": verified,
                "endFocus": verified,
                "resumeFocus": verified,
            },
            summary={"saveFocusSummary": verified},
            tasks={"linkFocusTasks": verified},
            calendar={"prepareCalendarFocus": verified},
            context={"addFocusContext": verified},
        )
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
        ):
            result = ownership.get_native_focus_ownership_readiness()

        self.assertTrue(result.ok)
        self.assertEqual(result.readiness, "ready")
        self.assertTrue(result.readyForLegacyProjectionRetirement)
        self.assertEqual(result.verifiedOperationCount, 8)
        self.assertEqual(result.requiredOperationCount, 8)
        self.assertEqual(result.blockers, [])
        self.assertEqual(result.evidenceNeeded, [])
        self.assertTrue(result.legacyProjection.retired)
        self.assertTrue(result.legacyProjection.fallbackBlocked)
        self.assertIn(
            "prepare-calendar-focus",
            result.legacyProjection.quarantinedCommands,
        )
        self.assertEqual(
            result.legacyProjection.remainingBrowserOwnedWriteSurfaces,
            [],
        )
        context_operation = next(
            item for item in result.operations if item.operation == "add_focus_context"
        )
        self.assertEqual(context_operation.status, "verified")

    def test_unexercised_operation_keeps_readiness_collecting(self) -> None:
        verified = health_section()
        unexercised = health_section(
            attempts=0,
            verified=0,
            outcome="",
        )
        patches = self._patch_health(
            lifecycle={
                "startFocus": verified,
                "updateFocus": verified,
                "endFocus": verified,
                "resumeFocus": unexercised,
            },
            summary={"saveFocusSummary": verified},
            tasks={"linkFocusTasks": verified},
            calendar={"prepareCalendarFocus": verified},
            context={"addFocusContext": verified},
        )
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
        ):
            result = ownership.get_native_focus_ownership_readiness()

        self.assertTrue(result.ok)
        self.assertEqual(result.readiness, "collecting")
        self.assertFalse(result.readyForLegacyProjectionRetirement)
        self.assertEqual(result.blockers, [])
        self.assertIn("Run and verify resume_focus at least once", result.evidenceNeeded)

    def test_latest_failed_receipt_blocks_readiness(self) -> None:
        verified = health_section()
        failed = health_section(
            attempts=2,
            verified=1,
            failed=1,
            outcome="failed",
            failure="verification_failed",
        )
        patches = self._patch_health(
            lifecycle={
                "startFocus": verified,
                "updateFocus": verified,
                "endFocus": verified,
                "resumeFocus": verified,
            },
            summary={"saveFocusSummary": verified},
            tasks={"linkFocusTasks": verified},
            calendar={"prepareCalendarFocus": failed},
            context={"addFocusContext": verified},
        )
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
        ):
            result = ownership.get_native_focus_ownership_readiness()

        self.assertFalse(result.ok)
        self.assertEqual(result.readiness, "blocked")
        self.assertFalse(result.readyForLegacyProjectionRetirement)
        self.assertIn(
            "prepare_calendar_focus has a degraded latest ownership receipt",
            result.blockers,
        )
        calendar_operation = next(
            item
            for item in result.operations
            if item.operation == "prepare_calendar_focus"
        )
        self.assertEqual(calendar_operation.status, "degraded")
        self.assertEqual(calendar_operation.lastFailureCode, "verification_failed")

    def test_historical_failures_do_not_block_after_a_verified_latest_receipt(self) -> None:
        recovered = health_section(
            attempts=3,
            verified=2,
            failed=1,
            outcome="created",
            failure="",
        )
        patches = self._patch_health(
            lifecycle={
                "startFocus": recovered,
                "updateFocus": recovered,
                "endFocus": recovered,
                "resumeFocus": recovered,
            },
            summary={"saveFocusSummary": recovered},
            tasks={"linkFocusTasks": recovered},
            calendar={"prepareCalendarFocus": recovered},
            context={"addFocusContext": recovered},
        )
        with (
            patches[0],
            patches[1],
            patches[2],
            patches[3],
            patches[4],
        ):
            result = ownership.get_native_focus_ownership_readiness()

        self.assertEqual(result.readiness, "ready")
        self.assertTrue(result.ok)
        self.assertEqual(result.blockers, [])
        self.assertTrue(all(item.status == "verified" for item in result.operations))


if __name__ == "__main__":
    unittest.main()
