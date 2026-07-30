from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.focus.readiness import (
    build_promotion_readiness,
    load_last_successful_validation,
    update_last_successful_validation,
)


def response_summary(**overrides):
    value = {
        "guardedAttemptCount": 3,
        "healthyDecisionRate": 1.0,
        "systemFailureCount": 0,
        "unknownFallbackCount": 0,
    }
    value.update(overrides)
    return value


def route_summary(**overrides):
    value = {
        "decisionCount": 8,
        "healthyDecisionRate": 1.0,
        "systemFailureCount": 0,
        "unknownFallbackCount": 0,
    }
    value.update(overrides)
    return value


def exact_summary(**overrides):
    value = {
        "observationCount": 5,
        "unknownCount": 0,
    }
    value.update(overrides)
    return value


class FocusPromotionReadinessTests(unittest.TestCase):
    def build(self, **overrides):
        payload = {
            "response_selection": response_summary(),
            "route_selection": route_summary(),
            "exact_route_observation": exact_summary(),
            "planner_mode": "shadow",
            "response_mode": "guarded",
            "route_mode": "guarded",
            "planner_enabled": True,
        }
        payload.update(overrides)
        return build_promotion_readiness(**payload)

    def test_ready_when_all_current_session_evidence_is_healthy(self) -> None:
        result = self.build()

        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["ready"])
        self.assertEqual(result["blockers"], [])
        self.assertEqual(result["missingEvidence"], [])
        self.assertFalse(result["automaticPromotion"])
        self.assertEqual(result["panelTitle"], "Planner Promotion Readiness")
        self.assertEqual(result["statusLabel"], "Ready for review")
        self.assertIn("promotion review", result["recommendation"])

    def test_collecting_when_sample_requirements_are_not_met(self) -> None:
        result = self.build(
            response_selection=response_summary(guardedAttemptCount=1),
            route_selection=route_summary(decisionCount=3),
            exact_route_observation=exact_summary(observationCount=2),
        )

        self.assertEqual(result["status"], "collecting")
        self.assertFalse(result["ready"])
        self.assertEqual(result["blockers"], [])
        self.assertEqual(len(result["missingEvidence"]), 3)
        self.assertIn("shadow mode", result["recommendation"])

    def test_blocked_when_current_session_has_system_failure(self) -> None:
        result = self.build(
            response_selection=response_summary(systemFailureCount=1),
        )

        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["ready"])
        self.assertIn("response system failure", result["blockers"][0])
        self.assertIn("shadow mode", result["recommendation"])

    def test_blocked_when_guarded_modes_are_not_enabled(self) -> None:
        result = self.build(response_mode="shadow", route_mode="shadow")

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(len(result["blockers"]), 2)

    def test_active_mode_collecting_uses_validation_display_language(self) -> None:
        result = self.build(
            planner_mode="active",
            response_selection=response_summary(guardedAttemptCount=1),
            route_selection=route_summary(decisionCount=3),
            exact_route_observation=exact_summary(observationCount=2),
        )

        self.assertEqual(result["status"], "collecting")
        self.assertEqual(result["stage"], "active_validation")
        self.assertEqual(result["panelTitle"], "Active Planner Validation")
        self.assertEqual(result["statusLabel"], "Collecting health evidence")
        self.assertEqual(result["statusMeta"], "Current-session guarded health")
        self.assertNotIn("shadow mode", result["recommendation"])

    def test_active_mode_ready_is_labeled_healthy(self) -> None:
        result = self.build(planner_mode="active")

        self.assertEqual(result["status"], "ready")
        self.assertTrue(result["ready"])
        self.assertEqual(result["statusLabel"], "Healthy")
        self.assertIn("continued active-mode operation", result["recommendation"])
        self.assertNotIn("promotion review", result["recommendation"])

    def test_active_mode_blocked_is_labeled_attention_required(self) -> None:
        result = self.build(
            planner_mode="active",
            response_selection=response_summary(systemFailureCount=1),
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["statusLabel"], "Attention required")
        self.assertIn("guarded routing", result["recommendation"])

    def test_off_mode_uses_setup_display_language(self) -> None:
        result = self.build(planner_mode="off", planner_enabled=False)

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["stage"], "planner_setup")
        self.assertEqual(result["panelTitle"], "Planner Setup Readiness")
        self.assertEqual(result["statusLabel"], "Planner disabled")


class FocusValidationHistoryTests(unittest.TestCase):
    def build_active_ready(self):
        return build_promotion_readiness(
            response_selection=response_summary(),
            route_selection=route_summary(),
            exact_route_observation=exact_summary(observationCount=6),
            planner_mode="active",
            response_mode="guarded",
            route_mode="guarded",
            planner_enabled=True,
        )

    def record(self, path: Path, readiness, **overrides):
        payload = {
            "readiness": readiness,
            "session_started_at": "2026-07-30T11:45:41-07:00",
            "planner_mode": "active",
            "response_mode": "guarded",
            "route_mode": "guarded",
            "planner_enabled": True,
            "history_path": path,
            "validated_at": "2026-07-30T12:05:00-07:00",
        }
        payload.update(overrides)
        return update_last_successful_validation(**payload)

    def test_ready_active_session_is_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validation.json"
            record = self.record(path, self.build_active_ready())

            self.assertIsNotNone(record)
            self.assertEqual(record["kind"], "active_validation")
            self.assertEqual(record["plannerMode"], "active")
            self.assertEqual(record["routeDecisions"], 8)
            self.assertEqual(record["responseGuardedAttempts"], 3)
            self.assertEqual(record["exactRouteObservations"], 6)
            self.assertEqual(load_last_successful_validation(history_path=path), record)

    def test_polling_same_session_does_not_rewrite_validation_time(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validation.json"
            first = self.record(path, self.build_active_ready())
            second = self.record(
                path,
                self.build_active_ready(),
                validated_at="2026-07-30T12:10:00-07:00",
            )

            self.assertEqual(second, first)
            self.assertEqual(second["validatedAt"], "2026-07-30T12:05:00-07:00")

    def test_collecting_session_keeps_previous_successful_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validation.json"
            first = self.record(path, self.build_active_ready())
            collecting = build_promotion_readiness(
                response_selection=response_summary(guardedAttemptCount=0),
                route_selection=route_summary(decisionCount=0),
                exact_route_observation=exact_summary(observationCount=1),
                planner_mode="active",
                response_mode="guarded",
                route_mode="guarded",
                planner_enabled=True,
            )
            returned = self.record(
                path,
                collecting,
                session_started_at="2026-07-30T13:00:00-07:00",
            )

            self.assertEqual(returned, first)
            self.assertEqual(load_last_successful_validation(history_path=path), first)

    def test_new_ready_session_replaces_previous_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validation.json"
            first = self.record(path, self.build_active_ready())
            second = self.record(
                path,
                self.build_active_ready(),
                session_started_at="2026-07-31T09:00:00-07:00",
                validated_at="2026-07-31T09:20:00-07:00",
            )

            self.assertNotEqual(second, first)
            self.assertEqual(second["sessionStartedAt"], "2026-07-31T09:00:00-07:00")
            self.assertEqual(second["validatedAt"], "2026-07-31T09:20:00-07:00")

    def test_invalid_history_file_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validation.json"
            path.write_text("not-json", encoding="utf-8")

            self.assertIsNone(load_last_successful_validation(history_path=path))

    def test_unready_session_does_not_create_history_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validation.json"
            collecting = build_promotion_readiness(
                response_selection=response_summary(guardedAttemptCount=0),
                route_selection=route_summary(decisionCount=0),
                exact_route_observation=exact_summary(observationCount=0),
                planner_mode="active",
                response_mode="guarded",
                route_mode="guarded",
                planner_enabled=True,
            )

            record = self.record(path, collecting)

            self.assertIsNone(record)
            self.assertFalse(path.exists())

    def test_history_json_contains_only_normalized_public_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validation.json"
            self.record(path, self.build_active_ready())
            raw = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(
                set(raw),
                {
                    "kind",
                    "plannerMode",
                    "validatedAt",
                    "sessionStartedAt",
                    "routeDecisions",
                    "responseGuardedAttempts",
                    "exactRouteObservations",
                    "routeHealthyRate",
                    "responseHealthyRate",
                },
            )


if __name__ == "__main__":
    unittest.main()
