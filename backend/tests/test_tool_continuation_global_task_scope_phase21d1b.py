from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app.tool_continuation import (
    ToolContinuationRequest,
    build_tool_continuation_input,
    focus_context_relevant_to_continuation,
)


ACTIVE_PRESENTATION_FOCUS = {
    "focusId": "focus-presentation",
    "title": "prepare for my presentation",
    "objective": "prepare a clear presentation for the project review",
    "deliverable": "presentation",
    "subject": "project review",
    "requirements": [],
    "constraints": [],
    "preferences": [],
    "decisions": [],
    "knownFacts": [],
    "milestones": ["review the presentation outline"],
    "completedMilestones": ["review the presentation outline"],
    "nextAction": "write the first concrete presentation step",
    "pendingQuestion": None,
    "status": "active",
}


class ToolContinuationGlobalTaskScopePhase21D1BTests(unittest.TestCase):
    def _request(
        self,
        *,
        user_message: str,
        action: str,
        tool_result: str,
        tool_context: str,
    ) -> ToolContinuationRequest:
        return ToolContinuationRequest(
            userMessage=user_message,
            capability="tasks",
            action=action,
            toolResult=tool_result,
            toolContext=tool_context,
            verified=True,
            success=True,
            verificationSource="frontend-deterministic-command",
            recentConversation=[
                {
                    "role": "user",
                    "content": "show my focus tasks",
                },
                {
                    "role": "tool",
                    "content": "4 tasks linked to prepare for my presentation.",
                },
                {
                    "role": "assistant",
                    "content": "Your presentation Focus is moving forward.",
                },
            ],
            uiContext={"activePanel": "memory", "command": action},
        )

    @staticmethod
    def _payload(messages: list[dict[str, str]]) -> dict:
        final_content = messages[-1]["content"]
        _, payload = final_content.split("\n\n", 1)
        return json.loads(payload)

    def test_global_task_create_excludes_active_focus_and_stale_history(self) -> None:
        request = self._request(
            user_message="Add a task to read my invoices",
            action="remember-task",
            tool_result="Saved task: read my invoices.",
            tool_context=(
                "qmeetScope=global-tasks. qmeetFocusRelationship=none. "
                "This task creation created one global task only."
            ),
        )

        with patch(
            "app.tool_continuation.active_focus_snapshot",
            return_value=ACTIVE_PRESENTATION_FOCUS,
        ):
            messages = build_tool_continuation_input(request)

        self.assertEqual(len(messages), 3)
        payload = self._payload(messages)
        self.assertFalse(payload["focusContextIncluded"])
        self.assertIsNone(payload["activeFocusAdvisoryContext"])
        joined = "\n".join(message["content"] for message in messages)
        self.assertNotIn("Your presentation Focus is moving forward.", joined)
        self.assertNotIn("4 tasks linked to prepare for my presentation.", joined)
        self.assertEqual(payload["originalUserTurn"], "Add a task to read my invoices")
        self.assertEqual(
            payload["verifiedToolReceipt"]["result"],
            "Saved task: read my invoices.",
        )

    def test_global_completion_and_delete_use_the_same_scope_isolation(self) -> None:
        for action, result in (
            ("mark-task-done", "Marked task done: read my invoices"),
            ("delete-last-task", "Deleted task: read my invoices"),
        ):
            with self.subTest(action=action):
                request = self._request(
                    user_message="I finished the invoice task",
                    action=action,
                    tool_result=result,
                    tool_context=(
                        "qmeetScope=global-tasks. qmeetFocusRelationship=none. "
                        "This changed global task state only."
                    ),
                )
                with patch(
                    "app.tool_continuation.active_focus_snapshot",
                    return_value=ACTIVE_PRESENTATION_FOCUS,
                ):
                    messages = build_tool_continuation_input(request)

                self.assertEqual(len(messages), 3)
                payload = self._payload(messages)
                self.assertFalse(payload["focusContextIncluded"])
                self.assertIsNone(payload["activeFocusAdvisoryContext"])

    def test_verified_focus_linked_completion_still_includes_canonical_focus(self) -> None:
        request = self._request(
            user_message="the finished result has been decided",
            action="mark-task-done",
            tool_result=(
                "Marked task done: Decide the finished result for prepare for my presentation\n"
                "Focus progress updated."
            ),
            tool_context=(
                "qmeetScope=focus-linked-task. "
                "qmeetFocusRelationship=verified. "
                "This completion was verified against canonical Active Focus progress."
            ),
        )

        self.assertTrue(
            focus_context_relevant_to_continuation(
                request,
                ACTIVE_PRESENTATION_FOCUS,
            )
        )

        with patch(
            "app.tool_continuation.active_focus_snapshot",
            return_value=ACTIVE_PRESENTATION_FOCUS,
        ):
            messages = build_tool_continuation_input(request)

        payload = self._payload(messages)
        self.assertTrue(payload["focusContextIncluded"])
        self.assertEqual(
            payload["activeFocusAdvisoryContext"]["focusId"],
            "focus-presentation",
        )

    def test_verified_global_scope_outweighs_explicit_focus_words(self) -> None:
        request = self._request(
            user_message="Add a global task related to my focus to email the invoice",
            action="remember-task",
            tool_result="Saved task: email the invoice.",
            tool_context=(
                "qmeetScope=global-tasks. qmeetFocusRelationship=none. "
                "No Active Focus relationship was created or verified."
            ),
        )

        self.assertFalse(
            focus_context_relevant_to_continuation(
                request,
                ACTIVE_PRESENTATION_FOCUS,
            )
        )

    def test_unscoped_non_focus_tool_keeps_existing_relevance_fallback(self) -> None:
        request = self._request(
            user_message="save this presentation idea as a task",
            action="remember-task",
            tool_result="Saved task: presentation idea.",
            tool_context="",
        )

        self.assertTrue(
            focus_context_relevant_to_continuation(
                request,
                ACTIVE_PRESENTATION_FOCUS,
            )
        )


if __name__ == "__main__":
    unittest.main()
