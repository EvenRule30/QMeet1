from __future__ import annotations

import unittest

from app import qmeet_agent_shadow as shadow


class AgentSearchIntentReliabilityPhase21BTests(unittest.TestCase):
    def _decision(self, message: str):
        request = shadow.AgentShadowRequest(
            userMessage=message,
            recentConversation=[],
            uiState={},
            clientContext={},
        )
        return shadow.normalize_shadow_decision(
            shadow._fallback_shadow_decision(request, None)
        )

    def test_natural_reviewer_question_is_search_owned_tool_work(self) -> None:
        message = "I wonder what reviewers think about the Framework Laptop"
        decision = self._decision(message)

        self.assertEqual(decision.turnOwner, "search")
        self.assertEqual(decision.disposition, "tool")
        self.assertEqual(decision.proposedCapability, "search")
        self.assertEqual(decision.proposedAction, "run-search")
        self.assertEqual(decision.proposedArguments, {"query": message})
        self.assertGreaterEqual(decision.confidence, 0.9)

    def test_natural_people_are_saying_question_is_search_owned_tool_work(self) -> None:
        message = "could you see what people are saying about Framework Laptop repairability?"
        decision = self._decision(message)

        self.assertEqual(decision.turnOwner, "search")
        self.assertEqual(decision.disposition, "tool")
        self.assertEqual(decision.proposedAction, "run-search")
        self.assertEqual(decision.proposedArguments, {"query": message})

    def test_general_knowledge_question_does_not_become_search_by_default(self) -> None:
        decision = self._decision("why is the sky blue?")

        self.assertEqual(decision.turnOwner, "general_chat")
        self.assertEqual(decision.disposition, "conversation")
        self.assertNotEqual(decision.proposedAction, "run-search")

    def test_search_contract_exposes_exact_executable_argument_schema(self) -> None:
        contract = next(
            item
            for item in shadow.GLOBAL_CAPABILITY_CONTRACT
            if item.get("owner") == "search"
        )

        self.assertEqual(contract.get("executableAction"), "run-search")
        schema = contract.get("argumentSchema") or {}
        self.assertEqual(schema.get("required"), ["query"])
        self.assertFalse(schema.get("additionalProperties"))
        self.assertEqual(
            ((schema.get("properties") or {}).get("query") or {}).get("type"),
            "string",
        )

    def test_model_prompt_forbids_answering_external_research_from_memory(self) -> None:
        prompt = shadow.AGENT_SHADOW_SYSTEM_PROMPT
        self.assertIn("external/web evidence", prompt)
        self.assertIn("Do not answer those requests from model memory", prompt)
        self.assertIn('proposedArguments with exactly one field: {"query":', prompt)


if __name__ == "__main__":
    unittest.main()
