from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "app" / "App.tsx"
RESOLVER = ROOT / "src" / "app" / "lib" / "taskDeletionResolver.ts"
VERIFIED_DELETE = ROOT / "src" / "app" / "lib" / "verifiedTaskDeletion.ts"
CAPABILITIES = ROOT / "backend" / "app" / "qmeet_capabilities.py"
MEMORY_ROUTER = ROOT / "backend" / "app" / "routers" / "memory.py"


class AgentTaskDeletePromotionPhase21D1Tests(unittest.TestCase):
    def test_tasks_contract_exposes_targeted_delete_lookup_only(self) -> None:
        source = CAPABILITIES.read_text(encoding="utf-8")
        ast.parse(source)

        self.assertIn('"delete-task"', source)
        self.assertIn('"promotedDeleteAction": "delete-task"', source)
        self.assertIn('"required": ["scope", "query"]', source)
        self.assertIn('"scope": {"type": "string", "enum": ["global"]}', source)
        self.assertIn(
            "query is semantic lookup language only and never task identity",
            source,
        )
        self.assertIn(
            "Active Focus-linked task deletion remains prohibited by the canonical backend guard",
            source,
        )

    def test_targeted_delete_accepts_agent_proposal_and_deterministic_natural_floor(self) -> None:
        source = RESOLVER.read_text(encoding="utf-8")

        self.assertIn(
            "export function isPromotedTaskDeleteToolDecision(",
            source,
        )
        self.assertIn("decision.proposedAction === 'delete-task'", source)
        self.assertIn("decision.proposedCapability === 'tasks'", source)
        self.assertIn("argumentsValue.scope !== 'global'", source)
        self.assertIn(
            "export function resolveNaturalGlobalTaskDeletionRequest(",
            source,
        )
        self.assertIn("(?:delete|remove|erase)", source)

    def test_deletion_resolution_is_zero_one_multiple_and_never_model_identity(self) -> None:
        source = RESOLVER.read_text(encoding="utf-8")

        self.assertIn("export function resolveTaskDeletionReference(", source)
        self.assertIn("if (exact.length === 1)", source)
        self.assertIn("if (exact.length > 1)", source)
        self.assertIn("if (contained.length === 1)", source)
        self.assertIn("if (contained.length > 1)", source)
        self.assertIn("kind: 'ambiguous'", source)
        self.assertIn("kind: 'none'", source)
        self.assertNotIn("taskId", source)

    def test_conversation_cannot_swallow_explicit_targeted_delete(self) -> None:
        source = APP.read_text(encoding="utf-8")
        gate = source.index("const promotedConversationAllowed")
        first_tool = source.index("const promotedSearchTool", gate)
        block = source[gate:first_tool]

        self.assertIn("!naturalGlobalTaskDeletionRequest", block)
        self.assertIn("const effectiveTaskDeleteQuery", block)
        self.assertIn("await getMemoryTasks()", block)
        self.assertIn("resolveTaskDeletionReference(", block)

    def test_exact_task_identity_is_locked_and_rechecked_after_confirmation(self) -> None:
        source = APP.read_text(encoding="utf-8")

        self.assertIn(
            "const pendingTaskDeleteTargetRef = useRef<ConfirmedTaskTarget | null>(null);",
            source,
        )
        self.assertIn("action: 'delete-task'", source)
        self.assertIn(
            "pendingTaskDeleteTargetRef.current = {",
            source,
        )
        confirmed = source.index("if (commandToRun.action === 'delete-task')")
        confirmed_block = source[confirmed:source.index("if (\n              commandToRun.action === 'delete-calendar-event'", confirmed)]
        self.assertIn("const authoritativeTasks = await getMemoryTasks();", confirmed_block)
        self.assertIn("task.id === resolvedTaskDeleteTarget.id", confirmed_block)
        self.assertIn(
            "task.title.trim() === resolvedTaskDeleteTarget.title.trim()",
            confirmed_block,
        )
        self.assertIn("await deleteVerifiedGlobalTask({", confirmed_block)
        self.assertIn("deleteMemoryTask(authoritativeDeleteTarget.id);", confirmed_block)

    def test_backend_delete_receipt_must_match_confirmed_id_before_projection(self) -> None:
        source = VERIFIED_DELETE.read_text(encoding="utf-8")

        request = source.index("await deleteMemoryTaskById(taskId)")
        verification = source.index("response.deletedTaskId !== taskId", request)
        success = source.index("ok: true", verification)
        self.assertLess(request, verification)
        self.assertLess(verification, success)

    def test_active_focus_linked_task_delete_guard_remains_backend_authoritative(self) -> None:
        source = MEMORY_ROUTER.read_text(encoding="utf-8")
        delete_route = source.index('@router.delete("/tasks/{task_id}"')
        delete_block = source[delete_route:delete_route + 900]

        self.assertIn("if _protected_focus_task(task_id):", delete_block)
        self.assertIn("_retired_focus_task_delete()", delete_block)
        self.assertIn("delete_memory_task(task_id)", delete_block)


if __name__ == "__main__":
    unittest.main()
