from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class SemanticLifecycleBoundaryInstallContractTests(unittest.TestCase):
    def test_backend_contract_uses_boundary_refinement_version(self) -> None:
        preflight_text = (
            REPO_ROOT / "backend/app/focus/semantic_lifecycle_preflight.py"
        ).read_text(encoding="utf-8")
        self.assertIn('SEMANTIC_LIFECYCLE_BRIDGE_VERSION = "phase20d2a5b"', preflight_text)
        self.assertIn("_apply_semantic_boundary_guards", preflight_text)
        self.assertIn("_explicit_replacement_signal", preflight_text)
        self.assertIn("_explicit_mode_request", preflight_text)
        self.assertIn("SemanticLifecycleIntent.CANCELLED", preflight_text)

    def test_frontend_contract_accepts_concise_cancellation(self) -> None:
        bridge_text = (
            REPO_ROOT / "src/app/lib/semanticFocusLifecycle.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("phase20d2a5b", bridge_text)
        self.assertIn("kind: 'acknowledged'", bridge_text)
        self.assertIn("payload.intent === 'cancelled'", bridge_text)

    def test_app_stops_cancelled_lifecycle_turn_before_chat(self) -> None:
        app_text = (REPO_ROOT / "src/app/App.tsx").read_text(encoding="utf-8")
        acknowledgement_index = app_text.index(
            "semanticFocusLifecycle.kind === 'acknowledged'"
        )
        interpreter_index = app_text.index("interpretCommandIntent(trimmed)")
        self.assertLess(acknowledgement_index, interpreter_index)
        self.assertIn("Semantic Focus lifecycle cancellation", app_text)
        self.assertIn("Focus lifecycle change cancelled", app_text)

    def test_verified_native_executors_remain_unchanged_authorities(self) -> None:
        memory_text = (
            REPO_ROOT / "src/app/commandHandlers/memory.ts"
        ).read_text(encoding="utf-8")
        lifecycle_text = (
            REPO_ROOT / "src/app/lib/nativeFocusLifecycle.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("startNativeFocusVerified", memory_text)
        self.assertIn("updateNativeFocusVerified", memory_text)
        self.assertIn("/api/focus/lifecycle/start", lifecycle_text)
        self.assertIn("/api/focus/lifecycle/update", lifecycle_text)


if __name__ == "__main__":
    unittest.main()
