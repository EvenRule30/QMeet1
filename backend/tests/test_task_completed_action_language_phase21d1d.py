from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FOCUS_RESOLVER = (
    ROOT / "src" / "app" / "lib" / "naturalTaskCompletion.ts"
).read_text(encoding="utf-8")
GLOBAL_RESOLVER = (
    ROOT / "src" / "app" / "lib" / "taskCompletionResolver.ts"
).read_text(encoding="utf-8")


class TaskCompletedActionLanguagePhase21D1DTests(unittest.TestCase):
    def test_focus_linked_completion_recognizes_asked_as_completed_action(self) -> None:
        self.assertIn("|emailed|asked|updated|", FOCUS_RESOLVER)
        self.assertIn("  'asked',", FOCUS_RESOLVER)
        self.assertIn("  asked: 'ask',", FOCUS_RESOLVER)
        self.assertIn("  asking: 'ask',", FOCUS_RESOLVER)

    def test_global_completion_recognizes_asked_as_completed_action(self) -> None:
        self.assertIn("  asked: 'ask',", GLOBAL_RESOLVER)
        self.assertIn("  asking: 'ask',", GLOBAL_RESOLVER)
        self.assertIn("  'asked',", GLOBAL_RESOLVER)
        self.assertIn("|fixed|asked|did|", GLOBAL_RESOLVER)

    def test_completion_language_is_generic_not_blocker_specific(self) -> None:
        combined = FOCUS_RESOLVER + "\n" + GLOBAL_RESOLVER
        self.assertNotIn("first blocker", combined.casefold())
        self.assertNotIn("ask qmeet for help", combined.casefold())
        self.assertNotIn("presentation", combined.casefold())

    def test_focus_resolution_still_requires_real_open_linked_task_state(self) -> None:
        self.assertIn(
            "const candidateTasks = openFocusLinkedTasks(tasks, activeSession);",
            FOCUS_RESOLVER,
        )
        self.assertIn(
            "if (candidateTasks.length === 0) return null;",
            FOCUS_RESOLVER,
        )
        self.assertIn("candidate.matchedTokenCount >= 2", FOCUS_RESOLVER)
        self.assertIn("candidate.score >= 0.5", FOCUS_RESOLVER)

    def test_global_resolution_still_requires_real_open_task_state(self) -> None:
        self.assertIn(
            "const candidates = openTasks(tasks);",
            GLOBAL_RESOLVER,
        )
        self.assertIn(
            "if (candidates.length === 0) return { kind: 'none' };",
            GLOBAL_RESOLVER,
        )
        self.assertIn(
            "const resolution = resolveGlobalTaskCompletionReference(query, tasks);",
            GLOBAL_RESOLVER,
        )
        self.assertIn(
            "if (resolution.kind === 'none') return null;",
            GLOBAL_RESOLVER,
        )

    def test_confirmation_and_mutation_are_not_part_of_language_resolvers(self) -> None:
        combined = FOCUS_RESOLVER + "\n" + GLOBAL_RESOLVER
        self.assertNotIn("markMemoryTaskDoneById(", combined)
        self.assertNotIn("completeConfirmedTaskTargets(", combined)
        self.assertNotIn("recordVerifiedFocusTaskProgress(", combined)


if __name__ == "__main__":
    unittest.main()
