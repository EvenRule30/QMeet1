from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
NEW_RESOLVER = (
    ROOT / "src" / "app" / "lib" / "taskCompletionResolver.ts"
).read_text(encoding="utf-8")
CAPS = (
    ROOT / "backend" / "app" / "qmeet_capabilities.py"
).read_text(encoding="utf-8")


class TaskCompletionSafetyCompatPhase21C4Tests(unittest.TestCase):
    def test_existing_focus_natural_completion_resolver_is_not_replaced(self) -> None:
        self.assertIn("resolveNaturalFocusTaskCompletionTarget", APP)
        self.assertIn("resolveNaturalFocusTaskCompletionTarget(", APP)
        self.assertIn("routingActiveSession", APP)
        self.assertIn(
            "Natural Focus task completion needs safety confirmation",
            APP,
        )

    def test_exact_deterministic_commands_still_outrank_natural_fallback(self) -> None:
        parser_index = APP.index(
            "const rawParsedCommandMatch = forcedCommandMatch ?? parseCommand(trimmed);"
        )
        explicit_index = APP.index("const explicitDeterministicRoute =")
        fallback_index = APP.index("const naturalGlobalTaskCompletionRequest =")
        self.assertLess(parser_index, explicit_index)
        self.assertLess(explicit_index, fallback_index)
        fallback_source = APP[
            fallback_index : APP.index("const promotedConversationAllowed =")
        ]
        self.assertIn("!explicitDeterministicRoute", fallback_source)
        self.assertIn("!parsedCommandMatch", fallback_source)

    def test_global_fallback_does_not_steal_active_focus_linked_candidate(self) -> None:
        self.assertIn("naturalGlobalTaskCompletionTouchesActiveFocus", APP)
        self.assertIn(
            "routingActiveSession.linkedTaskIds.includes(task.id)",
            APP,
        )
        self.assertIn("!naturalGlobalTaskCompletionTouchesActiveFocus", APP)

    def test_ambiguous_agent_completion_never_creates_confirmation(self) -> None:
        ambiguous_index = APP.index(
            "effectiveTaskCompletionResolution.kind === 'ambiguous'"
        )
        resolved_index = APP.index(
            "const resolvedTask = effectiveTaskCompletionResolution.task;"
        )
        source = APP[ambiguous_index:resolved_index]
        self.assertIn("pendingTaskCompletionTargetsRef.current = []", source)
        self.assertIn("Which one did you mean? No task was changed.", source)
        self.assertIn("return;", source)

    def test_linked_focus_progress_verification_stays_after_confirmation(self) -> None:
        self.assertIn("recordVerifiedFocusTaskProgress(", APP)
        self.assertIn("immutableConfirmedTaskTargets", APP)
        self.assertIn(
            "routingActiveSession.linkedTaskIds.includes(task.id)",
            APP,
        )
        self.assertIn("completeConfirmedTaskTargets(", APP)

    def test_task_contract_expansion_preserves_completion_safety(self) -> None:
        # Phase 21D1 expands Tasks with targeted deletion. Phase 21C4's
        # compatibility invariant is the completion safety contract, not the
        # historical statement that creation was the only promoted task action.
        self.assertIn(
            '"promotedCompleteAction": "mark-task-done"',
            CAPS,
        )
        self.assertIn(
            '"required": ["scope", "query"]',
            CAPS,
        )
        self.assertIn(
            "Exactly one real open task must be deterministically resolved before confirmation.",
            CAPS,
        )
        self.assertIn(
            "Completion still verifies canonical Focus progress when the task is Focus-linked.",
            CAPS,
        )
        self.assertIn(
            '"promotedDeleteAction": "delete-task"',
            CAPS,
        )

    def test_natural_global_completion_only_activates_for_completed_work_language(self) -> None:
        self.assertIn("extractNaturalCompletionQuery", NEW_RESOLVER)

        # Assert the semantic completion vocabulary rather than freezing the
        # exact regex text. Later phases may safely add completed-action verbs
        # without invalidating this older safety regression.
        for verb in (
            "finished",
            "completed",
            "sent",
            "submitted",
            "reviewed",
            "handled",
            "resolved",
            "fixed",
            "asked",
        ):
            self.assertIn(f"  '{verb}',", NEW_RESOLVER)

        self.assertIn("  asked: 'ask',", NEW_RESOLVER)
        self.assertIn("took\\s+care\\s+of", NEW_RESOLVER)
        self.assertNotIn("want to", NEW_RESOLVER)
        self.assertNotIn("need to", NEW_RESOLVER)


if __name__ == "__main__":
    unittest.main()
