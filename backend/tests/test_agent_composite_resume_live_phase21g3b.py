from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class AgentCompositeResumeLivePhase21G3B3V3Tests(unittest.TestCase):
    def _read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_g2c_immediate_path_remains_first_and_authoritative(self) -> None:
        source = self._read("src/app/App.tsx")
        immediate = source.index(
            "preflightCompositeImmediatePlan(observedCompositePlan)"
        )
        immediate_execute = source.index(
            "executePreflightedCompositeImmediatePlan({",
            immediate,
        )
        resumable = source.index(
            "preflightCompositeResumablePlan(observedCompositePlan, {",
            immediate_execute,
        )
        self.assertLess(immediate, immediate_execute)
        self.assertLess(immediate_execute, resumable)
        self.assertIn(
            "compositePreflight.reason === 'confirmation-pause-required'",
            source,
        )

    def test_g3b3_delegates_first_targeted_calendar_mutation_to_current_turn_route(self) -> None:
        source = self._read("src/app/App.tsx")
        composite = self._read("src/app/lib/agentCompositeExecution.ts")
        self.assertIn(
            "deferFirstCalendarConfirmationToCanonicalRoute: true",
            source,
        )
        self.assertIn(
            "confirmationAuthority ===\n              'canonical-current-turn'",
            source,
        )
        self.assertIn(
            "confirmationAuthority: 'canonical-current-turn'",
            composite,
        )
        self.assertIn("commandMatch: null", composite)
        self.assertIn("index === 0", composite)
        self.assertIn("step.turnOwner === 'calendar'", composite)
        self.assertIn("step.proposedCapability === 'calendar'", composite)
        self.assertIn("'edit-last-event'", composite)
        self.assertIn("'delete-calendar-event'", composite)

    def test_planner_calendar_arguments_are_not_reentered_as_executable_authority(self) -> None:
        source = self._read("src/app/App.tsx")
        start = source.index("const g3bLiveEligible =")
        end = source.index("const expectedCompositeCalendarAction =", start)
        branch = source[start:end]
        self.assertIn(
            "compositeResumeForCanonicalRoute = pendingCompositeResume;",
            branch,
        )
        self.assertNotIn("pausedCandidate.commandMatch", branch)
        self.assertNotIn("pausedCandidate.calendarEditTargetCriteria", branch)
        self.assertNotIn("'agent',\n                  pausedCandidate", branch)

    def test_current_turn_is_locked_to_same_calendar_action_while_checkpoint_is_carried(self) -> None:
        source = self._read("src/app/App.tsx")
        self.assertIn("const expectedCompositeCalendarAction =", source)
        self.assertIn("const rawParsedCommandMatch =", source)
        self.assertIn(
            "rawParsedCommandMatch?.command !== expectedCompositeCalendarAction",
            source,
        )
        self.assertIn("const observedPromotedSingleIntent =", source)
        self.assertIn(
            "observedPromotedSingleIntent.turnOwner === 'calendar'",
            source,
        )
        self.assertIn(
            "observedPromotedSingleIntent.proposedAction ===\n          expectedCompositeCalendarAction",
            source,
        )
        self.assertIn(
            "resolvePromotedCalendarEditToolCommand(\n                observedPromotedSingleIntent",
            source,
        )
        self.assertIn(
            "resolvePromotedCalendarDeleteToolCommand(\n                  observedPromotedSingleIntent",
            source,
        )
        self.assertIn(
            "explicitCalendarWriteIntent?.expectedAction ??\n      expectedCompositeCalendarAction ??",
            source,
        )
        self.assertIn(
            "const promotedNonFocusToolOwner = expectedCompositeCalendarAction",
            source,
        )

    def test_non_calendar_routes_cannot_steal_canonical_primary_turn(self) -> None:
        source = self._read("src/app/App.tsx")
        self.assertIn(
            "const explicitGlobalTaskReadRequest =\n      !expectedCompositeCalendarAction",
            source,
        )
        self.assertIn(
            "const explicitFocusTaskReadRequest =\n      !expectedCompositeCalendarAction",
            source,
        )
        self.assertIn(
            "const naturalGlobalTaskCompletionRequest =\n      !expectedCompositeCalendarAction",
            source,
        )
        self.assertIn(
            "const naturalGlobalTaskDeletionRequest =\n      !expectedCompositeCalendarAction",
            source,
        )
        self.assertIn(
            "const explicitDeterministicRoute =\n      !expectedCompositeCalendarAction",
            source,
        )

    def test_resume_candidate_survives_calendar_routing_recursions(self) -> None:
        source = self._read("src/app/App.tsx")
        self.assertGreaterEqual(
            source.count("compositeResumeForCanonicalRoute,"),
            4,
        )
        self.assertIn(
            "promotedCalendarDeleteTool.commandMatch,",
            source,
        )
        self.assertIn(
            "promotedCalendarEditTool.target,\n        null,\n        null,\n        compositeResumeForCanonicalRoute,",
            source,
        )
        self.assertIn(
            "interpretedCommand.frontendCommand,\n            visibleUserText,\n            'interpreter',\n            undefined",
            source,
        )

    def test_canonical_event_identity_and_changes_still_lock_before_resume_arms(self) -> None:
        source = self._read("src/app/App.tsx")
        identity = source.index(
            "pendingCalendarEditTargetIdRef.current = targetEditEvent.id;"
        )
        changes = source.index(
            "pendingCalendarEditChangesRef.current = resolvedCalendarEditChanges;",
            identity,
        )
        arm = source.index(
            "armPendingCompositeResumeForAction(commandMatch.command);",
            changes,
        )
        self.assertLess(identity, changes)
        self.assertLess(changes, arm)
        self.assertIn(
            "pendingCompositeResumeRef.current = compositeResumeForCanonicalRoute;",
            source,
        )

    def test_diagnostic_noop_planner_calendar_payload_remains_invalid(self) -> None:
        validator = self._read("src/app/lib/agentToolPromotion.ts")
        composite = self._read("src/app/lib/agentCompositeExecution.ts")
        self.assertIn("destination === targetDay", validator)
        canonical_branch = composite.index(
            "options.deferFirstCalendarConfirmationToCanonicalRoute"
        )
        planner_validator = composite.index(
            "resolveResumableConfirmationCandidate(plan, step)",
            canonical_branch,
        )
        self.assertLess(canonical_branch, planner_validator)

        missing_command_guard = composite.index(
            "!plannedCandidate.commandMatch"
        )
        canonical_authority_guard = composite.index(
            "plannedCandidate.confirmationAuthority !== 'canonical-current-turn'",
            missing_command_guard,
        )
        paused_status = composite.index("status: 'paused'", canonical_authority_guard)
        self.assertLess(missing_command_guard, canonical_authority_guard)
        self.assertLess(canonical_authority_guard, paused_status)

    def test_confirmed_receipt_still_verifies_before_tail_resume(self) -> None:
        source = self._read("src/app/App.tsx")
        confirmed = source.index("validatePendingCompositeConfirmedReceipt(")
        resume = source.index(
            "resumePreflightedCompositeAfterConfirmation({",
            confirmed,
        )
        self.assertLess(confirmed, resume)
        self.assertIn("compositeStepReceiptRef.current", source)

    def test_cancel_and_end_chat_clear_pending_composite_state(self) -> None:
        source = self._read("src/app/App.tsx")
        self.assertGreaterEqual(
            source.count("pendingCompositeResumeRef.current = null;"),
            3,
        )

    def test_success_summary_remains_single_composite_completion(self) -> None:
        source = self._read("src/app/App.tsx")
        self.assertIn(
            "Done — both requested actions completed successfully.",
            source,
        )


if __name__ == "__main__":
    unittest.main()
