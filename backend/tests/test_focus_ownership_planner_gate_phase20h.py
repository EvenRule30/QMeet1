from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.focus.readiness import (
    build_promotion_readiness,
    update_last_successful_validation,
)


def healthy_response() -> dict[str, object]:
    return {
        "guardedAttemptCount": 3,
        "healthyDecisionRate": 1.0,
        "systemFailureCount": 0,
        "unknownFallbackCount": 0,
    }


def healthy_routes() -> dict[str, object]:
    return {
        "decisionCount": 8,
        "healthyDecisionRate": 1.0,
        "systemFailureCount": 0,
        "unknownFallbackCount": 0,
    }


def healthy_exact() -> dict[str, object]:
    return {"observationCount": 5, "unknownCount": 0}


def ownership(
    *,
    readiness: str = "ready",
    ready: bool = True,
    verified: int = 7,
    required: int = 7,
    retired: bool = True,
    fallback_blocked: bool = True,
    blockers: list[str] | None = None,
    evidence: list[str] | None = None,
    historical_failed_count: int = 0,
) -> dict[str, object]:
    return {
        "ok": readiness != "blocked",
        "ownership": "backend-native",
        "readiness": readiness,
        "readyForLegacyProjectionRetirement": ready,
        "verifiedOperationCount": verified,
        "requiredOperationCount": required,
        "operations": [
            {
                "operation": "link_focus_tasks",
                "status": "verified" if readiness == "ready" else readiness,
                "failedCount": historical_failed_count,
                "lastOutcome": "created" if readiness == "ready" else "failed",
                "lastFailureCode": "" if readiness == "ready" else "verification_failed",
            }
        ],
        "legacyProjection": {
            "retired": retired,
            "fallbackBlocked": fallback_blocked,
            "ownershipVersion": "phase20g",
            "quarantinedCommands": [],
            "remainingBrowserOwnedWriteSurfaces": [],
        },
        "blockers": blockers or [],
        "evidenceNeeded": evidence or [],
    }


def build(ownership_readiness: dict[str, object] | None) -> dict[str, object]:
    return build_promotion_readiness(
        response_selection=healthy_response(),
        route_selection=healthy_routes(),
        exact_route_observation=healthy_exact(),
        planner_mode="shadow",
        response_mode="guarded",
        route_mode="guarded",
        planner_enabled=True,
        ownership_readiness=ownership_readiness,
    )


class FocusOwnershipPlannerGatePhase20HTests(unittest.TestCase):
    def test_ready_ownership_allows_manual_promotion_readiness(self) -> None:
        result = build(ownership())

        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["ready"])
        self.assertFalse(result["automaticPromotion"])
        self.assertEqual(result["ownershipGate"]["status"], "ready")
        self.assertTrue(result["ownershipGate"]["ready"])

    def test_blocked_ownership_blocks_planner_readiness(self) -> None:
        result = build(
            ownership(
                readiness="blocked",
                ready=False,
                verified=5,
                blockers=["link_focus_tasks has a degraded latest ownership receipt"],
            )
        )

        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["ready"])
        self.assertIn(
            "Focus ownership gate: link_focus_tasks has a degraded latest ownership receipt",
            result["blockers"],
        )

    def test_collecting_ownership_keeps_planner_collecting(self) -> None:
        result = build(
            ownership(
                readiness="collecting",
                ready=False,
                verified=6,
                evidence=["Run and verify prepare_calendar_focus at least once"],
            )
        )

        self.assertEqual(result["status"], "collecting")
        self.assertFalse(result["ready"])
        self.assertIn(
            "Focus ownership gate: Run and verify prepare_calendar_focus at least once",
            result["missingEvidence"],
        )

    def test_historical_failed_counts_do_not_block_latest_verified_ownership(self) -> None:
        result = build(ownership(historical_failed_count=9))

        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["ownershipGate"]["ready"])
        self.assertEqual(result["blockers"], [])

    def test_active_mode_is_advisory_and_never_changes_modes(self) -> None:
        result = build_promotion_readiness(
            response_selection=healthy_response(),
            route_selection=healthy_routes(),
            exact_route_observation=healthy_exact(),
            planner_mode="active",
            response_mode="guarded",
            route_mode="guarded",
            planner_enabled=True,
            ownership_readiness=ownership(
                readiness="blocked",
                ready=False,
                retired=False,
                blockers=["Legacy projection remains writable"],
            ),
        )

        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["automaticPromotion"])
        self.assertEqual(result["promotionTarget"], "active")
        self.assertEqual(result["stage"], "active_validation")

    def test_missing_snapshot_remains_backward_compatible_for_direct_callers(self) -> None:
        result = build(None)

        self.assertEqual(result["status"], "ready")
        self.assertFalse(result["ownershipGate"]["required"])
        self.assertEqual(result["ownershipGate"]["status"], "not_evaluated")

    def test_blocked_explicit_gate_is_not_recorded_as_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "history.json"
            result = build(
                ownership(
                    readiness="blocked",
                    ready=False,
                    blockers=["receipt failed"],
                )
            )
            # Defend against a caller accidentally mutating only the top-level flag.
            result["ready"] = True

            record = update_last_successful_validation(
                readiness=result,
                session_started_at="2026-08-05T16:00:00-07:00",
                planner_mode="shadow",
                response_mode="guarded",
                route_mode="guarded",
                planner_enabled=True,
                history_path=history_path,
                validated_at="2026-08-05T16:30:00-07:00",
            )

            self.assertIsNone(record)
            self.assertFalse(history_path.exists())

    def test_ready_validation_history_records_ownership_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            history_path = Path(directory) / "history.json"
            result = build(ownership(historical_failed_count=1))

            record = update_last_successful_validation(
                readiness=result,
                session_started_at="2026-08-05T16:00:00-07:00",
                planner_mode="shadow",
                response_mode="guarded",
                route_mode="guarded",
                planner_enabled=True,
                history_path=history_path,
                validated_at="2026-08-05T16:30:00-07:00",
            )

            self.assertIsNotNone(record)
            self.assertEqual(record["ownershipGateStatus"], "ready")
            self.assertEqual(record["ownershipVersion"], "phase20g")
            self.assertEqual(record["ownershipVerifiedOperationCount"], 7)
            self.assertEqual(record["ownershipRequiredOperationCount"], 7)
            self.assertTrue(record["legacyProjectionRetired"])
            self.assertTrue(record["ownershipFallbackBlocked"])
            persisted = json.loads(history_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["ownershipGateStatus"], "ready")


if __name__ == "__main__":
    unittest.main()
