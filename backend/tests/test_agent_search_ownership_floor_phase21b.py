from __future__ import annotations

import unittest

from app.qmeet_agent_shadow import (
    AgentShadowDecision,
    AgentShadowRequest,
    apply_search_ownership_floor,
)


class AgentSearchOwnershipFloorPhase21BTests(unittest.TestCase):
    def request(self, message: str) -> AgentShadowRequest:
        return AgentShadowRequest(
            userMessage=message,
            recentConversation=[],
            uiState={},
            clientContext={},
        )

    def conversation_decision(self) -> AgentShadowDecision:
        return AgentShadowDecision(
            turnOwner="general_chat",
            focusRelevant=False,
            disposition="conversation",
            proposedCapability="none",
            proposedAction="conversation.respond",
            proposedArguments={},
            responsePlan="Answer conversationally.",
            confidence=0.96,
            reason="Model thought this could be answered from memory.",
        )

    def test_reviewer_opinion_request_cannot_be_downgraded_to_model_memory_chat(self) -> None:
        request = self.request("I wonder what reviewers think about the Framework Laptop")
        decision = apply_search_ownership_floor(request, None, self.conversation_decision())

        self.assertEqual(decision.turnOwner, "search")
        self.assertEqual(decision.disposition, "tool")
        self.assertEqual(decision.proposedCapability, "search")
        self.assertEqual(decision.proposedAction, "run-search")
        self.assertEqual(
            decision.proposedArguments,
            {"query": "I wonder what reviewers think about the Framework Laptop"},
        )
        self.assertGreaterEqual(decision.confidence, 0.94)

    def test_people_are_saying_request_is_search_owned(self) -> None:
        request = self.request(
            "could you see what people are saying about Framework Laptop repairability?"
        )
        decision = apply_search_ownership_floor(request, None, self.conversation_decision())
        self.assertEqual((decision.turnOwner, decision.proposedAction), ("search", "run-search"))

    def test_plain_personal_opinion_question_is_not_forced_to_search(self) -> None:
        request = self.request("what do you think about the Framework Laptop?")
        original = self.conversation_decision()
        decision = apply_search_ownership_floor(request, None, original)
        self.assertEqual(decision, original)

    def test_valid_model_search_proposal_is_preserved(self) -> None:
        request = self.request("what do reviewers think about the Framework Laptop?")
        model = AgentShadowDecision(
            turnOwner="search",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="search",
            proposedAction="run-search",
            proposedArguments={"query": "Framework Laptop reviews"},
            responsePlan="Search and summarize verified reviewer findings.",
            confidence=0.97,
            reason="External reviewer evidence is required.",
        )
        decision = apply_search_ownership_floor(request, None, model)
        self.assertEqual(decision, model)

    def test_malformed_model_search_arguments_are_replaced_by_safe_query(self) -> None:
        request = self.request("what do reviewers think about the Framework Laptop?")
        malformed = AgentShadowDecision(
            turnOwner="search",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="search",
            proposedAction="run-search",
            proposedArguments={"request": "Framework Laptop", "extra": True},
            responsePlan="Search.",
            confidence=0.99,
            reason="Search requested.",
        )
        decision = apply_search_ownership_floor(request, None, malformed)
        self.assertEqual(
            decision.proposedArguments,
            {"query": "what do reviewers think about the Framework Laptop?"},
        )


if __name__ == "__main__":
    unittest.main()
