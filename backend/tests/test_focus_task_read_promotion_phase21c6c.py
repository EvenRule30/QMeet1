from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "app" / "App.tsx"
FOCUS_TASK_READ = ROOT / "src" / "app" / "lib" / "focusTaskRead.ts"


class FocusTaskReadPromotionPhase21C6CTests(unittest.TestCase):
    def test_focus_task_read_has_dedicated_deterministic_scope_detector(self):
        source = FOCUS_TASK_READ.read_text(encoding="utf-8")

        self.assertIn("export function isExplicitFocusTaskReadRequest", source)
        self.assertIn("FOCUS_TASK_READ_NOUN", source)
        self.assertIn("FOCUS_TASK_READ_VERB", source)
        self.assertIn("FOCUS_TASK_REFERENCE", source)
        self.assertIn("TASK_MUTATION_OR_COMPLETION", source)
        self.assertIn("payload: 'focus-task-read'", source)
        self.assertIn("command: 'read-memory'", source)

    def test_explicit_focus_task_read_cannot_fall_through_to_agent_conversation(self):
        source = APP.read_text(encoding="utf-8")
        promoted = source.index("const promotedSingleIntent =")
        promoted_end = source.index("const promotedTaskCompletionCandidate", promoted)
        block = source[promoted:promoted_end]

        self.assertIn("!explicitFocusTaskReadRequest", block)
        self.assertIn(
            "const explicitFocusTaskReadCommandMatch = explicitFocusTaskReadRequest",
            source,
        )
        self.assertIn(
            "? 'Deterministic Focus task read ownership floor'",
            source,
        )

    def test_focus_task_read_rechecks_canonical_focus_and_authoritative_tasks(self):
        source = APP.read_text(encoding="utf-8")
        focus_read = source.index("const focusTaskReadCommandResult")
        global_read = source.index("const globalTaskReadCommandResult", focus_read)
        block = source[focus_read:global_read]

        self.assertIn(
            "await reconcileCanonicalFocusProjection(",
            block,
        )
        self.assertIn("activeSession,", block)
        self.assertIn("recentFocusSessions,", block)
        self.assertIn("const authoritativeTasks = await getMemoryTasks();", block)
        self.assertIn(
            "formatFocusTaskReadout(\n                    canonicalFocusSession,\n                    authoritativeTasks.tasks ?? [],",
            block,
        )
        self.assertIn("qmeetFocusTaskReadVerified=true", block)
        self.assertIn(
            "canonical /api/focus/state linkage and authoritative /api/memory/tasks records",
            block,
        )

    def test_focus_task_read_fails_closed_instead_of_using_stale_projection(self):
        source = APP.read_text(encoding="utf-8")
        focus_read = source.index("const focusTaskReadCommandResult")
        global_read = source.index("const globalTaskReadCommandResult", focus_read)
        block = source[focus_read:global_read]

        self.assertIn("} catch (error) {", block)
        self.assertIn(
            "refusing to substitute local or historical task state",
            block,
        )
        self.assertIn("qmeetFocusTaskReadVerified=false", block)
        self.assertIn(
            "Do not infer, reconstruct, or list Focus tasks from recent conversation, local projection, Focus history, or global task state.",
            block,
        )
        self.assertNotIn("formatFocusTaskReadout(routingActiveSession, memoryTasks)", block)

    def test_no_active_focus_does_not_fall_back_to_global_tasks(self):
        source = APP.read_text(encoding="utf-8")
        focus_read = source.index("const focusTaskReadCommandResult")
        global_read = source.index("const globalTaskReadCommandResult", focus_read)
        block = source[focus_read:global_read]

        self.assertIn("'No active Focus is currently running.'", block)
        self.assertNotIn("formatOpenTasksReadout", block)

    def test_focus_read_result_preempts_generic_memory_handler(self):
        source = APP.read_text(encoding="utf-8")
        memory_result = source.index("const memoryCommandResult")
        memory_handler = source.index("await handleMemoryCommand(commandMatch", memory_result)
        block = source[memory_result:memory_handler]

        self.assertIn("focusTaskReadCommandResult.handled", block)
        self.assertIn("? focusTaskReadCommandResult", block)

    def test_global_and_focus_task_read_scopes_remain_separate(self):
        source = APP.read_text(encoding="utf-8")

        self.assertIn("commandMatch.payload === 'focus-task-read'", source)
        self.assertIn("commandMatch.payload === 'global-task-read'", source)
        self.assertIn("qmeetScope=focus-linked-tasks", source)
        self.assertIn("qmeetScope=global-tasks", source)


if __name__ == "__main__":
    unittest.main()
