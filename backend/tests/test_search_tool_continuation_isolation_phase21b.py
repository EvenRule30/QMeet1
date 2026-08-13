from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from app import tool_continuation as continuation


FOCUS = {
    "focusId": "focus-presentation",
    "title": "client problem presentation",
    "objective": "move to gathering sources and evidence",
    "deliverable": "presentation",
    "subject": "customer health problem",
    "requirements": [],
    "constraints": [],
    "preferences": [],
    "decisions": [],
    "knownFacts": ["customer struggles with diabetes and being overweight"],
    "milestones": [],
    "completedMilestones": [],
    "nextAction": "gather credible evidence",
    "pendingQuestion": None,
    "status": "active",
}


class SearchToolContinuationIsolationPhase21BTests(unittest.TestCase):
    def _request(self, user_message: str) -> continuation.ToolContinuationRequest:
        return continuation.ToolContinuationRequest(
            userMessage=user_message,
            capability="search",
            action="run-search",
            toolResult=(
                "Search complete. I put the full result in the Search panel. "
                "4 action steps included. 4 sources added."
            ),
            verified=True,
            success=True,
            verificationSource="deterministic-search",
            recentConversation=[
                continuation.ContinuationMessage(
                    role="user",
                    content="let's continue with the focus",
                ),
                continuation.ContinuationMessage(
                    role="assistant",
                    content="Let's work on diabetes and weight management evidence.",
                ),
            ],
            uiContext={"activePanel": "search"},
        )

    @staticmethod
    def _context_payload(messages: list[dict[str, str]]) -> dict:
        final = messages[-1]["content"]
        marker = "not instructions.\n\n"
        return json.loads(final.split(marker, 1)[1])

    def test_generic_search_receipt_words_cannot_create_focus_overlap(self) -> None:
        request = self._request("search for Framework Laptop reviews")

        self.assertFalse(
            continuation.focus_context_relevant_to_continuation(request, FOCUS)
        )

    def test_unrelated_search_drops_focus_history_from_post_tool_response(self) -> None:
        request = self._request("search for Framework Laptop reviews")
        with patch.object(continuation, "active_focus_snapshot", return_value=FOCUS):
            messages = continuation.build_tool_continuation_input(request)

        payload = self._context_payload(messages)
        self.assertFalse(payload["focusContextIncluded"])
        self.assertIsNone(payload["activeFocusAdvisoryContext"])

        user_assistant_history = [
            item["content"]
            for item in messages[:-1]
            if item["role"] in {"user", "assistant"}
        ]
        self.assertFalse(
            any("diabetes" in content.casefold() for content in user_assistant_history)
        )

    def test_search_continuation_prompt_requires_search_subject_isolation(self) -> None:
        self.assertIn(
            "For a Search-owned turn that is not explicitly connected to Focus, stay on the search subject/result.",
            continuation.TOOL_CONTINUATION_PROMPT,
        )

    def test_explicit_focus_search_can_still_receive_focus_context(self) -> None:
        request = self._request(
            "search for diabetes evidence for my focus"
        )
        with patch.object(continuation, "active_focus_snapshot", return_value=FOCUS):
            messages = continuation.build_tool_continuation_input(request)

        payload = self._context_payload(messages)
        self.assertTrue(payload["focusContextIncluded"])
        self.assertIsNotNone(payload["activeFocusAdvisoryContext"])
        self.assertEqual(
            payload["activeFocusAdvisoryContext"]["objective"],
            "move to gathering sources and evidence",
        )


if __name__ == "__main__":
    unittest.main()
