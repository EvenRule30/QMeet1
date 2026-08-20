from __future__ import annotations

import unittest
from pathlib import Path

from app.qmeet_agent_shadow import (
    AGENT_SHADOW_SYSTEM_PROMPT,
    GLOBAL_CAPABILITY_CONTRACT,
)


ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
PROMOTION = (
    ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts"
).read_text(encoding="utf-8")
RESOLVER = (
    ROOT / "src" / "app" / "lib" / "taskCompletionResolver.ts"
).read_text(encoding="utf-8")


class AgentTaskCompletionPromotionPhase21C4Tests(unittest.TestCase):
    def test_shared_contract_exposes_query_only_completion_semantics(self) -> None:
        tasks = next(
            item
            for item in GLOBAL_CAPABILITY_CONTRACT
            if item.get("owner") == "tasks"
        )
        self.assertEqual(tasks.get("promotedCompleteAction"), "mark-task-done")
        schema = tasks["completeArgumentSchema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(schema["required"], ["scope", "query"])
        self.assertEqual(schema["properties"]["scope"]["enum"], ["global"])
        self.assertEqual(schema["properties"]["query"]["maxLength"], 240)
        self.assertIn("never task identity", str(schema.get("constraint", "")))

    def test_agent_prompt_promotes_one_semantic_completion_reference(self) -> None:
        self.assertIn(
            "proposedAction=mark-task-done",
            AGENT_SHADOW_SYSTEM_PROMPT,
        )
        self.assertIn(
            '{"scope": "global", "query": "<concise identifying task reference>"}',
            AGENT_SHADOW_SYSTEM_PROMPT,
        )
        self.assertIn('"I finished the invoice"', AGENT_SHADOW_SYSTEM_PROMPT)
        self.assertIn('"I took care of the slides"', AGENT_SHADOW_SYSTEM_PROMPT)
        self.assertIn("Task completion remains", AGENT_SHADOW_SYSTEM_PROMPT)
        self.assertIn("never a task id", AGENT_SHADOW_SYSTEM_PROMPT)
        self.assertIn(
            "multiple candidates require clarification",
            AGENT_SHADOW_SYSTEM_PROMPT,
        )

    def test_frontend_validator_requires_global_scope_and_query_only(self) -> None:
        self.assertIn(
            "export function isPromotedTaskCompletionToolDecision",
            PROMOTION,
        )
        self.assertIn(
            "export function resolvePromotedTaskCompletionToolCommand",
            PROMOTION,
        )
        self.assertIn(
            "hasExactlyKeys(argumentsValue, ['scope', 'query'])",
            PROMOTION,
        )
        self.assertIn("argumentsValue.scope !== 'global'", PROMOTION)
        self.assertIn(
            "decision.proposedAction === 'mark-task-done'",
            PROMOTION,
        )
        self.assertIn("payload: query", PROMOTION)

    def test_state_aware_fallback_runs_after_agent_but_before_conversation(self) -> None:
        decision_index = APP.index("const promotedSingleIntent =")
        fallback_index = APP.index(
            "const naturalGlobalTaskCompletionRequest ="
        )
        conversation_index = APP.index("const promotedConversationAllowed =")
        self.assertLess(decision_index, fallback_index)
        self.assertLess(fallback_index, conversation_index)
        fallback_source = APP[fallback_index:conversation_index]
        self.assertIn("!explicitDeterministicRoute", fallback_source)
        self.assertIn("!parsedCommandMatch", fallback_source)
        self.assertIn("memoryTasks", fallback_source)
        self.assertIn(
            "naturalGlobalTaskCompletionTouchesActiveFocus",
            APP,
        )
        self.assertIn("!naturalGlobalTaskCompletionFallback", APP)

    def test_promoted_no_match_retries_authoritative_task_state(self) -> None:
        self.assertIn(
            'import { getMemoryTasks, resetConversation, interpretCommandIntent } from "./api";',
            APP,
        )
        local_resolution = APP.index(
            "let effectiveTaskCompletionResolution ="
        )
        refresh = APP.index(
            "const authoritativeTasks = await getMemoryTasks();",
            local_resolution,
        )
        no_match_reply = APP.index(
            "I couldn't find an open task matching",
            refresh,
        )
        self.assertLess(local_resolution, refresh)
        self.assertLess(refresh, no_match_reply)
        refreshed_source = APP[refresh:no_match_reply]
        self.assertIn(
            "resolveGlobalTaskCompletionReference",
            refreshed_source,
        )
        self.assertIn("authoritativeTasks.tasks ?? []", refreshed_source)

    def test_resolved_task_identity_reuses_existing_confirmation_seam(self) -> None:
        self.assertIn(
            "{ id: resolvedTask.id, title: resolvedTask.title }",
            APP,
        )
        self.assertIn(
            "promotedTaskCompletionTarget: ConfirmedTaskTarget | null = null",
            APP,
        )
        self.assertIn(
            "task.id === promotedTaskCompletionTarget.id",
            APP,
        )
        self.assertIn(
            "task.title.trim() === promotedTaskCompletionTarget.title.trim()",
            APP,
        )
        self.assertIn("id: promotedTaskCompletionTarget.id", APP)
        self.assertIn("title: promotedTaskCompletionTarget.title", APP)
        self.assertIn(
            "pendingTaskCompletionTargetsRef.current = isTaskCompletionCommand",
            APP,
        )
        self.assertIn(
            "const confirmedTaskCommandMatch: CommandMatch | undefined =",
            APP,
        )
        self.assertIn(
            "return executeConfirmedPendingCommand(confirmedTaskCommandMatch);",
            APP,
        )

        wrapper_start = APP.index(
            "const executeConfirmedPendingCommand = async ("
        )
        wrapper_end = APP.index(
            "if (confirmedCalendarEditCommandMatch)",
            wrapper_start,
        )
        wrapper = APP[wrapper_start:wrapper_end]
        self.assertIn("confirmedCommandMatch", wrapper)
        self.assertIn("resolvedTaskTargets", wrapper)
        self.assertIn("'confirmed'", wrapper)

    def test_confirm_rechecks_identity_against_authoritative_tasks_if_local_state_is_stale(self) -> None:
        immutable_local = APP.index(
            "const immutableConfirmedTaskTargets ="
        )
        execution_state = APP.index(
            "let confirmedTaskExecutionState = memoryTasks;",
            immutable_local,
        )
        refresh = APP.index(
            "const authoritativeTasks = await getMemoryTasks();",
            execution_state,
        )
        immutable_guard = APP.index(
            "setTrackedInputRoute('Confirmed task identity changed')",
            refresh,
        )
        local_completion = APP.index(
            "completeConfirmedTaskTargets(\n              memoryTasks,\n              confirmedTaskTargets,",
            immutable_guard,
        )
        authoritative_completion = APP.index(
            "completeConfirmedTaskTargets(\n                confirmedTaskExecutionState,",
            local_completion,
        )
        self.assertLess(immutable_local, execution_state)
        self.assertLess(execution_state, refresh)
        self.assertLess(refresh, immutable_guard)
        self.assertLess(immutable_guard, local_completion)
        self.assertLess(local_completion, authoritative_completion)
        refreshed_source = APP[refresh:immutable_guard]
        self.assertIn(
            "authoritativeTasks.tasks ?? []",
            refreshed_source,
        )
        self.assertIn(
            "confirmedTaskExecutionState = authoritativeTaskState",
            refreshed_source,
        )
        self.assertIn(
            "verifiedConfirmedTaskTargets = authoritativeConfirmedTaskTargets",
            refreshed_source,
        )

    def test_single_task_resolver_has_zero_one_many_outcomes(self) -> None:
        for expected in (
            "kind: 'exact'",
            "kind: 'likely'",
            "kind: 'ambiguous'",
            "kind: 'none'",
        ):
            self.assertIn(expected, RESOLVER)
        self.assertIn(
            "tasks.filter((task) => !task.completedAt)",
            RESOLVER,
        )
        self.assertIn("queryTokens.length === 1", RESOLVER)
        self.assertIn(
            "Math.abs(best.score - runnerUp.score) < 0.15",
            RESOLVER,
        )
        self.assertIn("No task was changed", APP)


if __name__ == "__main__":
    unittest.main()
