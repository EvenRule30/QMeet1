from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
OBSERVER = (
    ROOT / "src" / "app" / "lib" / "agentShadowObserver.ts"
).read_text(encoding="utf-8")


class AgentFirstReliabilityPhase21E5Tests(unittest.TestCase):
    def test_standard_promoted_wait_covers_a_three_second_agent_decision(self):
        self.assertIn("AGENT_FIRST_SINGLE_INTENT_WAIT_MS = 7000", OBSERVER)

    def test_single_intent_timeout_is_distinct_from_missing_agent_result(self):
        start = OBSERVER.index(
            "export async function resolvePromotedSingleIntentDecision"
        )
        end = OBSERVER.index(
            "export type AgentShadowFocusMutationGuardResult",
            start,
        )
        block = OBSERVER[start:end]

        self.assertIn("Promise.race", block)
        self.assertIn("waitForSingleIntentTimeout(timeoutMs)", block)
        self.assertIn("AGENT_FIRST_SINGLE_INTENT_TIMEOUT", block)
        self.assertIn("[QMeet agent-first timeout]", block)
        self.assertIn("timed-out-before-promoted-decision", block)
        self.assertNotIn("waitForTimeout(timeoutMs)", block)

    def test_agent_observation_logs_latency_for_runtime_diagnosis(self):
        start = OBSERVER.index("export async function observeAgentShadowTurn")
        end = OBSERVER.index(
            "export async function reportAgentShadowLegacyRoute",
            start,
        )
        block = OBSERVER[start:end]

        self.assertIn("const startedAt = Date.now();", block)
        self.assertIn("latencyMs: Date.now() - startedAt", block)

    def test_short_conversation_ownership_timeout_remains_separate(self):
        start = OBSERVER.index(
            "export async function resolvePromotedConversationOwnership"
        )
        end = OBSERVER.index(
            "export type ExplicitDeterministicRouteBeforeAgent",
            start,
        )
        block = OBSERVER[start:end]

        self.assertIn("CONVERSATION_OWNERSHIP_WAIT_MS", block)
        self.assertIn("waitForTimeout(timeoutMs)", block)
        self.assertNotIn("waitForSingleIntentTimeout(timeoutMs)", block)


if __name__ == "__main__":
    unittest.main()
