from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


class AgentCompositeResumeLivePhase21G3BTests(unittest.TestCase):
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
            "preflightCompositeResumablePlan(observedCompositePlan)",
            immediate_execute,
        )

        self.assertLess(immediate, immediate_execute)
        self.assertLess(immediate_execute, resumable)
        self.assertIn(
            "compositePreflight.reason === 'confirmation-pause-required'",
            source,
        )

    def test_first_live_resume_slice_is_one_first_step_targeted_calendar_mutation(self) -> None:
        source = self._read("src/app/App.tsx")

        self.assertIn("confirmationCandidates.length === 1", source)
        self.assertIn("livePause?.index === 0", source)
        self.assertIn("livePauseAction === 'edit-last-event'", source)
        self.assertIn("livePauseAction === 'delete-calendar-event'", source)
        self.assertNotIn("livePauseAction === 'add-calendar-event'", source)

    def test_initial_pause_reenters_existing_calendar_confirmation_path(self) -> None:
        source = self._read("src/app/App.tsx")

        branch = source[source.index("const g3bLiveEligible ="):]
        self.assertIn("createPendingCompositeResume({", branch)
        self.assertIn(
            "getPendingCompositePausedCandidate(pendingCompositeResume)",
            branch,
        )
        self.assertIn("pausedCandidate.commandMatch", branch)
        self.assertIn(
            "pausedCandidate.calendarEditTargetCriteria ?? null",
            branch,
        )
        self.assertIn("pendingCompositeResume,", branch)

    def test_resume_checkpoint_is_armed_only_inside_existing_confirmation_setup(self) -> None:
        source = self._read("src/app/App.tsx")

        self.assertIn("const armPendingCompositeResumeForAction", source)
        self.assertIn(
            "matchesPendingCompositeConfirmationAction(compositeResumeToArm, action)",
            source,
        )

        edit_identity = source.index(
            "pendingCalendarEditTargetIdRef.current = targetEditEvent.id"
        )
        edit_arm = source.index(
            "armPendingCompositeResumeForAction(commandMatch.command)",
            edit_identity,
        )
        edit_pending = source.index("setPendingInterpreterCommand({", edit_arm)
        self.assertLess(edit_identity, edit_arm)
        self.assertLess(edit_arm, edit_pending)

        delete_identity = source.index(
            "pendingCalendarDeleteTargetIdRef.current =",
            edit_pending,
        )
        delete_arm = source.index(
            "armPendingCompositeResumeForAction(commandMatch.command)",
            delete_identity,
        )
        delete_pending = source.index("setPendingInterpreterCommand({", delete_arm)
        self.assertLess(delete_identity, delete_arm)
        self.assertLess(delete_arm, delete_pending)

    def test_pending_resume_does_not_replace_calendar_identity_refs(self) -> None:
        source = self._read("src/app/App.tsx")
        resume_source = self._read("src/app/lib/agentCompositeResume.ts")

        self.assertIn("pendingCompositeResumeRef", source)
        self.assertIn("pendingCalendarEditTargetIdRef", source)
        self.assertIn("pendingCalendarDeleteTargetIdRef", source)
        self.assertNotIn("eventId:", resume_source)
        self.assertNotIn("taskId:", resume_source)
        self.assertNotIn("focusId:", resume_source)

    def test_confirmed_mutation_is_tagged_with_exact_paused_step_id(self) -> None:
        source = self._read("src/app/App.tsx")

        confirmed = source[source.index("const executeConfirmedPendingCommand = async"):]
        self.assertIn(
            "confirmedCompositeResume?.pause.pausedStepId ?? null",
            confirmed,
        )
        self.assertIn("compositeStepReceiptRef.current = null", confirmed)
        self.assertIn(
            "validatePendingCompositeConfirmedReceipt(",
            confirmed,
        )

    def test_trailing_steps_resume_only_after_matching_successful_receipt(self) -> None:
        source = self._read("src/app/App.tsx")

        validate_index = source.index(
            "validatePendingCompositeConfirmedReceipt("
        )
        resume_index = source.index(
            "resumePreflightedCompositeAfterConfirmation({",
            validate_index,
        )
        trailing_execute = source.index(
            "candidate.commandMatch,",
            resume_index,
        )

        self.assertLess(validate_index, resume_index)
        self.assertLess(resume_index, trailing_execute)
        self.assertIn("candidate.stepId", source[resume_index:])

    def test_confirm_is_visible_but_recursive_atomic_user_bubble_stays_suppressed(self) -> None:
        source = self._read("src/app/App.tsx")

        confirmed = source[source.index("const executeConfirmedPendingCommand = async"):]
        self.assertIn("const confirmUserMessage = createUserMessage(", confirmed)
        self.assertIn("composite-confirm-", confirmed)
        self.assertIn("setMessages((prev) => [...prev, confirmUserMessage])", confirmed)
        self.assertIn("else if (compositeAtomicExecution)", source)

    def test_cancel_and_unrelated_reply_clear_resume_checkpoint(self) -> None:
        source = self._read("src/app/App.tsx")

        cancel = source[source.index("if (isRejectingPendingCommand(trimmed))"):]
        self.assertIn("pendingCompositeResumeRef.current = null", cancel)
        self.assertIn("compositeStepReceiptRef.current = null", cancel)

        self.assertGreaterEqual(
            source.count("pendingCompositeResumeRef.current = null"),
            3,
        )

    def test_completed_resume_emits_one_final_composite_summary(self) -> None:
        source = self._read("src/app/App.tsx")

        resumed = source[source.index(
            "resumePreflightedCompositeAfterConfirmation({"
        ):]
        self.assertIn(
            "Done — both requested actions completed successfully.",
            resumed,
        )
        self.assertIn("composite-resume-summary-", resumed)
        self.assertIn(
            "The completed Tool updates remain valid.",
            resumed,
        )


if __name__ == "__main__":
    unittest.main()
