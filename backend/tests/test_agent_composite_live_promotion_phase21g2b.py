from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class AgentCompositeLivePromotionPhase21G2BTests(unittest.TestCase):
    def _read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_observation_gate_is_only_a_cheap_candidate_filter(self) -> None:
        source = self._read("src/app/lib/agentCompositePlan.ts")

        self.assertIn("shouldObserveAgentCompositePlan", source)
        self.assertIn("Cheap observation gate only", source)
        self.assertIn("False positives are safe", source)
        self.assertIn("COMPOSITE_STRUCTURE_HINT", source)

    def test_live_preflight_requires_high_confidence(self) -> None:
        source = self._read("src/app/lib/agentCompositeExecution.ts")

        self.assertIn("COMPOSITE_IMMEDIATE_MIN_CONFIDENCE = 0.9", source)
        self.assertIn("plan.plan.confidence < COMPOSITE_IMMEDIATE_MIN_CONFIDENCE", source)
        self.assertIn("'confidence-below-promotion-threshold'", source)

    def test_app_starts_composite_observation_only_on_fresh_exact_turns(self) -> None:
        source = self._read("src/app/App.tsx")

        self.assertIn("const compositePlanTurn =", source)
        self.assertIn("commandRoute === 'exact'", source)
        self.assertIn("!forcedCommandMatch", source)
        self.assertIn("shouldObserveAgentCompositePlan(visibleUserText)", source)
        self.assertIn("observeAgentCompositePlan({", source)

    def test_app_preflights_whole_plan_before_first_atomic_execution(self) -> None:
        source = self._read("src/app/App.tsx")

        preflight = source.index(
            "preflightCompositeImmediatePlan(observedCompositePlan)"
        )
        execute = source.index(
            "executePreflightedCompositeImmediatePlan({"
        )
        recursive = source.index(
            "candidate.commandMatch,",
            execute,
        )
        self.assertLess(preflight, execute)
        self.assertLess(execute, recursive)

    def test_atomic_steps_reenter_existing_handle_send_command_path(self) -> None:
        source = self._read("src/app/App.tsx")

        self.assertIn(
            "await handleSend(",
            source[source.index("executeStep: async (candidate)"):],
        )
        self.assertIn("'agent'", source)
        self.assertIn("candidate.commandMatch", source)
        self.assertIn("candidate.stepId", source)

    def test_composite_has_one_user_bubble_and_normal_tool_cards(self) -> None:
        source = self._read("src/app/App.tsx")

        self.assertIn(
            "const compositeUserMessage = createUserMessage(",
            source,
        )
        self.assertIn(
            "else if (compositeAtomicExecution)",
            source,
        )
        self.assertIn(
            "setMessages((prev) => [...prev, confirmationMsg])",
            source,
        )

    def test_atomic_steps_suppress_per_step_continuation_and_return_receipt(self) -> None:
        source = self._read("src/app/App.tsx")

        self.assertIn(
            "!focusTaskReadToolCardIsComplete && !compositeAtomicExecution",
            source,
        )
        self.assertIn("compositeStepReceiptRef.current = {", source)
        self.assertIn("ok: !hasFailureLanguage(confirmationContent)", source)
        self.assertIn("toolResult: confirmationContent", source)
        self.assertIn("splitCommandResult.continuationContext", source)

    def test_live_composite_still_has_no_pending_plan_state(self) -> None:
        source = self._read("src/app/App.tsx")

        self.assertNotIn("pendingCompositePlan", source)
        self.assertNotIn("setPendingCompositePlan", source)

    def test_finished_plan_gets_one_grounded_local_completion_message(self) -> None:
        source = self._read("src/app/App.tsx")

        self.assertIn(
            "Done — both requested actions completed successfully.",
            source,
        )
        self.assertIn(
            "The completed Tool updates remain valid.",
            source,
        )
        self.assertIn(
            "const compositeSummaryMessage = createAssistantMessage(",
            source,
        )

    def test_confirmation_and_unsupported_dependency_plans_still_fall_through(self) -> None:
        execution = self._read("src/app/lib/agentCompositeExecution.ts")
        app = self._read("src/app/App.tsx")

        self.assertIn("'confirmation-pause-required'", execution)
        self.assertIn("'dependency-not-yet-promoted'", execution)
        self.assertIn("'unsupported-result-binding'", execution)
        self.assertIn("isSupportedVerifiedResultBinding", execution)
        self.assertIn("if (compositePreflight.ok)", app)

        branch_start = app.index("if (compositePlanTurn) {")
        branch_end = app.index("const directFocusTerminalCommandMatch", branch_start)
        branch = app[branch_start:branch_end]
        self.assertNotIn("return;", branch.split("if (compositePreflight.ok)")[0])


if __name__ == "__main__":
    unittest.main()
