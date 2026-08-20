from __future__ import annotations

from pathlib import Path
import unittest

from app.qmeet_agent_composite import sanitize_composite_plan


ROOT = Path(__file__).resolve().parents[2]


class AgentCompositeVerifiedBindingPhase21G2CTests(unittest.TestCase):
    def _read(self, relative: str) -> str:
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_backend_accepts_only_typed_search_result_to_note_content_binding(self) -> None:
        plan = sanitize_composite_plan(
            {
                "isComposite": True,
                "steps": [
                    {
                        "turnOwner": "search",
                        "focusRelevant": False,
                        "proposedCapability": "search",
                        "proposedAction": "run-search",
                        "proposedArguments": {
                            "query": "Framework Laptop reviews",
                        },
                        "dependsOn": [],
                        "inputBindings": [],
                        "reason": "Run the requested search.",
                    },
                    {
                        "turnOwner": "notes",
                        "focusRelevant": False,
                        "proposedCapability": "notes",
                        "proposedAction": "save-note",
                        "proposedArguments": {},
                        "dependsOn": [1],
                        "inputBindings": [
                            {
                                "targetArgument": "content",
                                "sourceStep": 1,
                                "sourceField": "search.resultText",
                            }
                        ],
                        "reason": "Save the verified Search result as a note.",
                    },
                ],
                "confidence": 0.98,
                "reason": "The second action explicitly consumes the first result.",
            }
        )

        self.assertTrue(plan.isComposite)
        self.assertEqual(plan.steps[1].dependsOn, ["step-1"])
        self.assertEqual(len(plan.steps[1].inputBindings), 1)
        binding = plan.steps[1].inputBindings[0]
        self.assertEqual(binding.targetArgument, "content")
        self.assertEqual(binding.sourceStepId, "step-1")
        self.assertEqual(binding.sourceField, "search.resultText")
        self.assertNotIn("content", plan.steps[1].proposedArguments)

    def test_backend_rejects_dependency_without_typed_binding(self) -> None:
        plan = sanitize_composite_plan(
            {
                "isComposite": True,
                "steps": [
                    {
                        "turnOwner": "search",
                        "focusRelevant": False,
                        "proposedCapability": "search",
                        "proposedAction": "run-search",
                        "proposedArguments": {"query": "Framework"},
                        "dependsOn": [],
                        "reason": "Search.",
                    },
                    {
                        "turnOwner": "notes",
                        "focusRelevant": False,
                        "proposedCapability": "notes",
                        "proposedAction": "save-note",
                        "proposedArguments": {},
                        "dependsOn": [1],
                        "reason": "Untyped dependency.",
                    },
                ],
                "confidence": 0.99,
                "reason": "Unsafe dependency.",
            }
        )

        self.assertFalse(plan.isComposite)
        self.assertIn("binding", plan.reason)

    def test_backend_rejects_model_prefilled_content_when_binding_declared(self) -> None:
        plan = sanitize_composite_plan(
            {
                "isComposite": True,
                "steps": [
                    {
                        "turnOwner": "search",
                        "focusRelevant": False,
                        "proposedCapability": "search",
                        "proposedAction": "run-search",
                        "proposedArguments": {"query": "Framework"},
                        "dependsOn": [],
                        "inputBindings": [],
                        "reason": "Search.",
                    },
                    {
                        "turnOwner": "notes",
                        "focusRelevant": False,
                        "proposedCapability": "notes",
                        "proposedAction": "save-note",
                        "proposedArguments": {
                            "content": "Model invented this result",
                        },
                        "dependsOn": [1],
                        "inputBindings": [
                            {
                                "targetArgument": "content",
                                "sourceStep": 1,
                                "sourceField": "search.resultText",
                            }
                        ],
                        "reason": "Unsafe prefill.",
                    },
                ],
                "confidence": 0.99,
                "reason": "Unsafe prefilled binding.",
            }
        )

        self.assertFalse(plan.isComposite)
        self.assertIn("binding", plan.reason)

    def test_frontend_revalidates_binding_source_target_and_dependency_identity(self) -> None:
        source = self._read("src/app/lib/agentCompositePlan.ts")

        self.assertIn("AgentCompositeInputBinding", source)
        self.assertIn("binding.targetArgument !== 'content'", source)
        self.assertIn("binding.sourceField !== 'search.resultText'", source)
        self.assertIn("sourceStep.turnOwner !== 'search'", source)
        self.assertIn("sourceStep.proposedAction !== 'run-search'", source)
        self.assertIn("owner !== 'notes' || proposedAction !== 'save-note'", source)
        self.assertIn("dependsOn.length !== bindingDependencies.length", source)

    def test_search_handler_builds_binding_from_successful_search_response(self) -> None:
        source = self._read("src/app/commandHandlers/search.ts")

        self.assertIn("buildVerifiedSearchResultText", source)
        self.assertIn("if (!searchResponse.ok) return ''", source)
        self.assertIn("searchResponse.summary", source)
        self.assertIn("searchResponse.recommendation", source)
        self.assertIn("searchResponse.steps", source)
        self.assertIn("searchResponse.sources", source)
        self.assertIn("compositeBindings = {", source)
        self.assertIn("searchResultText", source)
        self.assertIn(".slice(0, 5900)", source)

    def test_dependent_note_is_bound_only_from_verified_receipt_then_revalidated(self) -> None:
        source = self._read("src/app/lib/agentCompositeExecution.ts")

        self.assertIn("resolveBoundCandidate", source)
        self.assertIn("receiptsByStepId.get(binding.sourceStepId)", source)
        self.assertIn(
            "sourceReceipt.verifiedBindings?.searchResultText",
            source,
        )
        self.assertIn(
            "[binding.targetArgument]: boundValue",
            source,
        )
        self.assertIn(
            "resolvePromotedNoteSaveToolCommand(decision)",
            source,
        )
        self.assertIn("receiptsByStepId.set(receipt.stepId, receipt)", source)

    def test_app_receipt_captures_handler_binding_without_pending_plan_state(self) -> None:
        source = self._read("src/app/App.tsx")

        self.assertIn("splitCommandResult.compositeBindings", source)
        self.assertIn(
            "verifiedBindings: splitCommandResult.compositeBindings",
            source,
        )
        self.assertNotIn("pendingCompositePlan", source)
        self.assertNotIn("setPendingCompositePlan", source)


if __name__ == "__main__":
    unittest.main()
