from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
RESOLVER = (
    ROOT / "src" / "app" / "lib" / "taskDeletionResolver.ts"
).read_text(encoding="utf-8")


class TaskDeleteClarificationPhase21D1ATests(unittest.TestCase):
    def test_ambiguous_delete_persists_only_shown_candidate_identities(self) -> None:
        ambiguous = APP.index(
            "if (authoritativeDeleteResolution.kind === 'ambiguous')"
        )
        prompt = APP.index("Which one did you mean? No task was changed.", ambiguous)
        block = APP[ambiguous:prompt]

        self.assertIn("pendingTaskDeleteClarificationRef.current = {", block)
        self.assertIn("originalText: visibleUserText", block)
        self.assertIn("id: task.id", block)
        self.assertIn("title: task.title", block)

    def test_clarification_is_resolved_before_agent_routing(self) -> None:
        clarification = APP.index(
            "const pendingTaskDeleteClarification ="
        )
        routing_focus = APP.index("const routingActiveSession =", clarification)
        promoted_agent = APP.index(
            "const promotedSingleIntent =",
            routing_focus,
        )

        self.assertLess(clarification, routing_focus)
        self.assertLess(routing_focus, promoted_agent)

    def test_clarification_rechecks_authoritative_tasks_by_locked_id_and_title(self) -> None:
        clarification = APP.index(
            "const pendingTaskDeleteClarification ="
        )
        routing_focus = APP.index("const routingActiveSession =", clarification)
        block = APP[clarification:routing_focus]

        self.assertIn("const authoritativeTasks = await getMemoryTasks();", block)
        self.assertIn("authoritativeById.get(candidate.id)", block)
        self.assertIn(
            "authoritativeTask.title.trim() === candidate.title.trim()",
            block,
        )
        self.assertIn(
            "resolveTaskDeletionClarificationReference(",
            block,
        )

    def test_resolved_clarification_still_requires_confirmation(self) -> None:
        clarification = APP.index(
            "const pendingTaskDeleteClarification ="
        )
        routing_focus = APP.index("const routingActiveSession =", clarification)
        block = APP[clarification:routing_focus]

        self.assertIn("pendingTaskDeleteTargetRef.current = {", block)
        self.assertIn("setPendingInterpreterCommand({", block)
        self.assertIn("action: 'delete-task'", block)
        self.assertIn(
            'Say "confirm" to delete it, or "cancel" to stop.',
            block,
        )
        self.assertNotIn("deleteVerifiedGlobalTask({", block)

    def test_unmatched_clarification_cannot_claim_or_execute_delete(self) -> None:
        clarification = APP.index(
            "const pendingTaskDeleteClarification ="
        )
        routing_focus = APP.index("const routingActiveSession =", clarification)
        block = APP[clarification:routing_focus]

        self.assertIn(
            "pendingTaskDeleteClarificationRef.current = null;",
            block,
        )
        self.assertIn(
            "message route normally as a fresh turn",
            block,
        )
        self.assertNotIn("has been deleted", block)

    def test_clarification_resolver_is_limited_to_supplied_candidates(self) -> None:
        self.assertIn(
            "export function resolveTaskDeletionClarificationReference(",
            RESOLVER,
        )
        resolver_start = RESOLVER.index(
            "export function resolveTaskDeletionClarificationReference("
        )
        resolver_end = RESOLVER.index(
            "function cleanDeletionQuery",
            resolver_start,
        )
        block = RESOLVER[resolver_start:resolver_end]

        self.assertIn(
            "return resolveTaskDeletionReference(reply, candidates);",
            block,
        )
        self.assertNotIn("getMemoryTasks", block)

    def test_ordinal_clarifications_are_supported_without_model_guessing(self) -> None:
        self.assertIn("function readClarificationOrdinalIndex(", RESOLVER)
        for token in ("first: 0", "second: 1", "third: 2"):
            self.assertIn(token, RESOLVER)


if __name__ == "__main__":
    unittest.main()
