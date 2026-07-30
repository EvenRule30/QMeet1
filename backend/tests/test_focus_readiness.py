from __future__ import annotations

import unittest

from app.focus.readiness import build_promotion_readiness


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

    def test_blocked_when_current_session_has_system_failure(self) -> None:
        result = self.build(
            response_selection=response_summary(systemFailureCount=1),
        )

        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["ready"])
        self.assertIn("response system failure", result["blockers"][0])

    def test_blocked_when_guarded_modes_are_not_enabled(self) -> None:
        result = self.build(response_mode="shadow", route_mode="shadow")

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(len(result["blockers"]), 2)


if __name__ == "__main__":
    unittest.main()
