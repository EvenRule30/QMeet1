from __future__ import annotations

import unittest
from pathlib import Path


class FocusContextInstallContractPhase20ITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[2]
        cls.boundary = (cls.root / "backend/app/focus/context_boundary.py").read_text(encoding="utf-8")
        cls.context = (cls.root / "backend/app/focus/context.py").read_text(encoding="utf-8")
        cls.router = (cls.root / "backend/app/routers/focus_lifecycle.py").read_text(encoding="utf-8")
        cls.semantic = (cls.root / "src/app/lib/semanticFocusLifecycle.ts").read_text(encoding="utf-8")
        cls.client = (cls.root / "src/app/lib/nativeFocusContext.ts").read_text(encoding="utf-8")
        cls.wrapper = (cls.root / "src/app/commandHandlers/memory.ts").read_text(encoding="utf-8")

    def test_documented_context_phrases_have_deterministic_boundary(self) -> None:
        for marker in (
            "I want somewhere warm",
            "I have three days available",
            "Keep the total cost under $1,000",
        ):
            self.assertIn(marker, (self.root / "backend/tests/test_focus_context_boundary_phase20i.py").read_text(encoding="utf-8"))
        self.assertIn("classify_focus_context", self.boundary)
        self.assertIn("phase20i-context", self.boundary)

    def test_semantic_preflight_routes_context_to_verified_update_envelope(self) -> None:
        self.assertIn("classify_focus_context(request.message)", self.router)
        self.assertIn("encode_focus_context_reason", self.router)
        self.assertIn("phase20i-context:", self.semantic)
        self.assertIn("contextField", self.semantic)
        self.assertIn("contextValue", self.semantic)

    def test_context_endpoint_requires_objective_preservation_proof(self) -> None:
        self.assertIn('@router.post("/context"', self.router)
        self.assertIn("expectedObjective", self.context)
        self.assertIn("objectivePreserved", self.context)
        self.assertIn("sourceTurnUnique", self.context)
        self.assertIn("focusContext", self.context)

    def test_frontend_independently_checks_exact_context_and_objective(self) -> None:
        self.assertIn("focusContext.objective === expectedObjective", self.client)
        self.assertIn("envelope.state", self.client)
        self.assertIn("/api/focus/state", self.client)
        self.assertIn("containsExact(contextValues, value)", self.client)
        self.assertIn("verification.objectivePreserved === true", self.client)
        self.assertIn("verification.contextPersisted === true", self.client)

    def test_wrapper_handles_context_before_normal_objective_update(self) -> None:
        context_index = self.wrapper.index("parseNativeFocusContextCommand")
        normal_update_index = self.wrapper.index("updateNativeFocusVerified({")
        self.assertLess(context_index, normal_update_index)
        self.assertIn("addNativeFocusContextVerified", self.wrapper)
        self.assertIn("expectedObjective: activeSession.goal", self.wrapper)
        self.assertIn("NATIVE_FOCUS_LIFECYCLE_OWNERSHIP_VERSION = 'phase20i'", self.wrapper)


if __name__ == "__main__":
    unittest.main()
