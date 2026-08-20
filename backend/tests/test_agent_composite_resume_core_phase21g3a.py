from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class AgentCompositeResumeCorePhase21G3ATests(unittest.TestCase):
    def _read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_g2c_live_immediate_preflight_remains_unchanged(self) -> None:
        source = self._read("src/app/lib/agentCompositeExecution.ts")

        immediate_start = source.index(
            "export function preflightCompositeImmediatePlan("
        )
        resumable_start = source.index(
            "export function preflightCompositeResumablePlan("
        )
        immediate_block = source[immediate_start:resumable_start]

        self.assertIn("CONFIRMATION_PAUSE_ACTIONS.has(step.proposedAction)", immediate_block)
        self.assertIn("'confirmation-pause-required'", immediate_block)

    def test_resumable_preflight_is_additive_and_calendar_only(self) -> None:
        source = self._read("src/app/lib/agentCompositeExecution.ts")

        self.assertIn("G3A_RESUMABLE_CONFIRMATION_ACTIONS", source)
        self.assertIn("'add-calendar-event'", source)
        self.assertIn("'edit-last-event'", source)
        self.assertIn("'delete-calendar-event'", source)
        self.assertIn("'unsupported-confirmation-action'", source)

    def test_calendar_pause_candidates_reuse_existing_single_intent_validators(self) -> None:
        source = self._read("src/app/lib/agentCompositeExecution.ts")

        self.assertIn("resolvePromotedCalendarCreateToolCommand(decision)", source)
        self.assertIn("resolvePromotedCalendarDeleteToolCommand(decision)", source)
        self.assertIn("resolvePromotedCalendarEditToolCommand(decision)", source)
        self.assertIn("calendarEditTargetCriteria: resolved.target", source)

    def test_resumable_coordinator_stops_before_confirmation_step(self) -> None:
        source = self._read("src/app/lib/agentCompositeExecution.ts")

        coordinator = source[source.index("async function executeResumableCandidates("):]
        pause = coordinator.index("plannedCandidate.confirmationMode === 'required'")
        execute = coordinator.index("receipt = await options.executeStep(candidate)")

        self.assertLess(pause, execute)
        self.assertIn("status: 'paused'", coordinator)
        self.assertIn("receiptsBeforePause: [...receipts]", coordinator)

    def test_resume_requires_exact_matching_successful_verified_receipt(self) -> None:
        source = self._read("src/app/lib/agentCompositeExecution.ts")

        resume = source[source.index(
            "export async function resumePreflightedCompositeAfterConfirmation("
        ):]

        self.assertIn("pause.planId !== options.preflight.planId", resume)
        self.assertIn("pausedCandidate.stepId !== pause.pausedStepId", resume)
        self.assertIn("pausedCandidate.proposedAction !== pause.expectedAction", resume)
        self.assertIn("confirmedReceipt.stepId !== pause.pausedStepId", resume)
        self.assertIn("confirmedReceipt.ok !== true", resume)
        self.assertIn("!confirmedReceipt.toolResult.trim()", resume)
        self.assertIn("startIndex: pause.pausedStepIndex + 1", resume)

    def test_pending_resume_state_never_owns_canonical_object_identity(self) -> None:
        source = self._read("src/app/lib/agentCompositeResume.ts")

        self.assertIn("PendingCompositeResume", source)
        self.assertIn("Canonical Calendar event identity", source)
        self.assertIn("pending Calendar target refs", source)
        self.assertNotIn("eventId:", source)
        self.assertNotIn("taskId:", source)
        self.assertNotIn("focusId:", source)

    def test_pending_resume_checkpoint_validates_action_and_receipt(self) -> None:
        source = self._read("src/app/lib/agentCompositeResume.ts")

        self.assertIn("createPendingCompositeResume", source)
        self.assertIn("getPendingCompositePausedCandidate", source)
        self.assertIn("matchesPendingCompositeConfirmationAction", source)
        self.assertIn("validatePendingCompositeConfirmedReceipt", source)
        self.assertIn("receipt.stepId === pending.pause.pausedStepId", source)

    def test_g3a_core_is_now_consumed_by_g3b_without_owning_calendar_identity(self) -> None:
        source = self._read("src/app/App.tsx")
        resume_source = self._read("src/app/lib/agentCompositeResume.ts")

        self.assertIn("preflightCompositeResumablePlan", source)
        self.assertIn("executePreflightedCompositeResumablePlan", source)
        self.assertIn("resumePreflightedCompositeAfterConfirmation", source)
        self.assertIn("PendingCompositeResume", source)
        self.assertIn("pendingCompositeResumeRef", source)
        self.assertIn("pendingCalendarEditTargetIdRef", source)
        self.assertIn("pendingCalendarDeleteTargetIdRef", source)
        self.assertNotIn("eventId:", resume_source)
        self.assertNotIn("taskId:", resume_source)
        self.assertNotIn("focusId:", resume_source)


if __name__ == "__main__":
    unittest.main()
