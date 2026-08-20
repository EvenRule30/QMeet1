from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class AgentCompositeExecutionPhase21G2ATests(unittest.TestCase):
    def _read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_plan_client_calls_additive_shadow_plan_endpoint(self) -> None:
        source = self._read("src/app/lib/agentCompositePlan.ts")

        self.assertIn("/api/agent/shadow/plan", source)
        self.assertIn("validateAgentCompositePlanResponse", source)
        self.assertIn("containsForbiddenIdentity", source)
        self.assertIn("Single-intent routing remains authoritative", source)

    def test_frontend_revalidates_step_order_and_identity(self) -> None:
        source = self._read("src/app/lib/agentCompositePlan.ts")

        self.assertIn("stepId !== `step-${index + 1}`", source)
        self.assertIn("earlierSteps.has(dependency)", source)
        self.assertIn("FORBIDDEN_IDENTITY_KEY", source)
        self.assertIn("containsForbiddenIdentity(proposedArguments)", source)

    def test_g2a_reuses_existing_single_intent_validators(self) -> None:
        source = self._read("src/app/lib/agentCompositeExecution.ts")

        for resolver in (
            "resolvePromotedSearchToolCommand",
            "resolvePromotedTaskCreateToolCommand",
            "resolvePromotedTaskReadToolCommand",
            "resolvePromotedNoteSaveToolCommand",
            "resolvePromotedNoteReadToolCommand",
            "resolvePromotedCalendarReadToolCommand",
        ):
            self.assertIn(resolver, source)

        self.assertIn("toPromotedAtomicDecision", source)
        self.assertIn("CommandMatch", source)

    def test_confirmation_pausing_actions_are_blocked_before_execution(self) -> None:
        source = self._read("src/app/lib/agentCompositeExecution.ts")

        for action in (
            "add-calendar-event",
            "edit-last-event",
            "delete-calendar-event",
            "mark-task-done",
            "delete-task",
        ):
            self.assertIn(f"'{action}'", source)

        self.assertIn("'confirmation-pause-required'", source)
        self.assertIn("preflights the whole plan before any step can run", source)

    def test_untyped_dependencies_stay_blocked_but_g2c_typed_binding_is_promoted(self) -> None:
        source = self._read("src/app/lib/agentCompositeExecution.ts")

        self.assertIn("'dependency-not-yet-promoted'", source)
        self.assertIn("'unsupported-result-binding'", source)
        self.assertIn("isSupportedVerifiedResultBinding", source)
        self.assertIn("binding.sourceField !== 'search.resultText'", source)
        self.assertIn("resolveBoundCandidate", source)
        self.assertIn("resolvePromotedNoteSaveToolCommand(decision)", source)

    def test_coordinator_requires_one_matching_verified_receipt_per_step(self) -> None:
        source = self._read("src/app/lib/agentCompositeExecution.ts")

        self.assertIn("receipt.stepId !== candidate.stepId", source)
        self.assertIn("receipt.ok !== true", source)
        self.assertIn("!receipt.toolResult.trim()", source)
        self.assertIn("receipts.push(receipt)", source)
        self.assertIn("status: 'completed'", source)

    def test_g2a_core_does_not_own_resumable_composite_state(self) -> None:
        execution_source = self._read("src/app/lib/agentCompositeExecution.ts")
        app_source = self._read("src/app/App.tsx")

        # Phase 21G2B may wire the G2A observer/coordinator into App, but G2A
        # itself still must not introduce a resumable pending-plan state or
        # bypass confirmation-pausing actions.
        self.assertIn("preflightCompositeImmediatePlan", execution_source)
        self.assertIn("executePreflightedCompositeImmediatePlan", execution_source)
        self.assertIn("'confirmation-pause-required'", execution_source)
        self.assertIn("'dependency-not-yet-promoted'", execution_source)
        self.assertNotIn("pendingCompositePlan", execution_source)
        self.assertNotIn("setPendingCompositePlan", execution_source)

        # Live G2B wiring is allowed, but resumable confirmation sequencing
        # remains intentionally absent from App until a later phase.
        self.assertIn("observeAgentCompositePlan", app_source)
        self.assertIn("executePreflightedCompositeImmediatePlan", app_source)
        self.assertNotIn("pendingCompositePlan", app_source)
        self.assertNotIn("setPendingCompositePlan", app_source)


if __name__ == "__main__":
    unittest.main()
