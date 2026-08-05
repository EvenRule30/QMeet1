from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class SemanticFocusLifecycleInstallContractTests(unittest.TestCase):
    def test_router_exposes_one_unified_semantic_lifecycle_endpoint(self) -> None:
        router_text = (
            REPO_ROOT / "backend/app/routers/focus_lifecycle.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"/semantic/interpret"', router_text)
        self.assertIn("semantic_focus_lifecycle_preflight", router_text)
        self.assertIn('"semantic_lifecycle_interpret"', router_text)

    def test_frontend_uses_one_lifecycle_preflight_before_general_interpreter(self) -> None:
        app_text = (REPO_ROOT / "src/app/App.tsx").read_text(encoding="utf-8")
        lifecycle_index = app_text.index("interpretSemanticFocusLifecycle(trimmed)")
        interpreter_index = app_text.index("interpretCommandIntent(trimmed)")
        self.assertLess(lifecycle_index, interpreter_index)
        self.assertNotIn("interpretSemanticFocusUpdate(trimmed)", app_text)
        self.assertIn("Semantic lifecycle Focus start", app_text)
        self.assertIn("Semantic lifecycle Focus update", app_text)

    def test_frontend_contract_builds_typed_start_and_update_commands(self) -> None:
        bridge_text = (
            REPO_ROOT / "src/app/lib/semanticFocusLifecycle.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("phase20d2a5", bridge_text)
        self.assertIn("/api/focus/lifecycle/semantic/interpret", bridge_text)
        self.assertIn("command: 'start-focus-session'", bridge_text)
        self.assertIn("command: 'update-focus-session'", bridge_text)
        self.assertNotIn("/api/chat", bridge_text)
        self.assertNotIn("/api/command/interpret", bridge_text)

    def test_existing_verified_executors_remain_the_only_writers(self) -> None:
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

    def test_semantic_classifier_does_not_write_focus_state(self) -> None:
        preflight_text = (
            REPO_ROOT / "backend/app/focus/semantic_lifecycle_preflight.py"
        ).read_text(encoding="utf-8")
        for token in [
            "append_event(",
            "append_events(",
            "start_focus_verified(",
            "update_focus_verified(",
            "apply_plan(",
        ]:
            with self.subTest(token=token):
                self.assertNotIn(token, preflight_text)


if __name__ == "__main__":
    unittest.main()
