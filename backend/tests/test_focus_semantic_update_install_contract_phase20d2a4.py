from __future__ import annotations

import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


class SemanticFocusUpdateInstallContractTests(unittest.TestCase):
    def test_semantic_preflight_lives_on_unobserved_lifecycle_surface(self) -> None:
        router_path = BACKEND_ROOT / "app" / "routers" / "focus_lifecycle.py"
        service_path = (
            BACKEND_ROOT / "app" / "focus" / "semantic_update_preflight.py"
        )
        router_text = router_path.read_text(encoding="utf-8")
        service_text = service_path.read_text(encoding="utf-8")

        self.assertIn('"/semantic-update/interpret"', router_text)
        self.assertIn("semantic_focus_update_preflight", router_text)
        self.assertIn("SemanticFocusUpdatePreflightResult", service_text)
        self.assertIn("Typed classification only", service_text)

    def test_observation_monkeypatch_is_not_installed(self) -> None:
        main_path = BACKEND_ROOT / "app" / "main.py"
        main_text = main_path.read_text(encoding="utf-8")

        self.assertNotIn(
            "install_semantic_focus_update_observation_policy",
            main_text,
        )
        self.assertIn("FocusShadowMiddleware", main_text)
        self.assertIn("focus_lifecycle", main_text)

    def test_general_command_router_no_longer_runs_semantic_update_model(self) -> None:
        command_path = BACKEND_ROOT / "app" / "routers" / "command.py"
        command_text = command_path.read_text(encoding="utf-8")

        self.assertNotIn("semantic_focus_update_command", command_text)
        self.assertNotIn("focus-update-capability", command_text)
        self.assertIn("interpret_qmeet_orchestrator", command_text)

    def test_frontend_preflights_before_general_command_interpreter(self) -> None:
        app_path = REPO_ROOT / "src" / "app" / "App.tsx"
        helper_path = (
            REPO_ROOT / "src" / "app" / "lib" / "semanticFocusUpdate.ts"
        )
        app_text = app_path.read_text(encoding="utf-8")
        helper_text = helper_path.read_text(encoding="utf-8")

        preflight_index = app_text.index(
            "await interpretSemanticFocusUpdate(trimmed)"
        )
        generic_index = app_text.index(
            "await interpretCommandIntent(trimmed)",
            preflight_index,
        )
        self.assertLess(preflight_index, generic_index)
        self.assertIn(
            "SEMANTIC_FOCUS_UPDATE_BRIDGE_VERSION = 'phase20d2a4c'",
            helper_text,
        )
        self.assertIn(
            "/api/focus/lifecycle/semantic-update/interpret",
            helper_text,
        )

    def test_typed_preflight_reuses_verified_update_executor(self) -> None:
        app_path = REPO_ROOT / "src" / "app" / "App.tsx"
        helper_path = (
            REPO_ROOT / "src" / "app" / "lib" / "semanticFocusUpdate.ts"
        )
        memory_path = (
            REPO_ROOT / "src" / "app" / "commandHandlers" / "memory.ts"
        )
        lifecycle_path = (
            REPO_ROOT / "src" / "app" / "lib" / "nativeFocusLifecycle.ts"
        )
        app_text = app_path.read_text(encoding="utf-8")
        helper_text = helper_path.read_text(encoding="utf-8")
        memory_text = memory_path.read_text(encoding="utf-8")
        lifecycle_text = lifecycle_path.read_text(encoding="utf-8")

        self.assertIn("command: 'update-focus-session'", helper_text)
        self.assertIn("semanticFocusUpdate.commandMatch", app_text)
        self.assertIn("updateNativeFocusVerified", memory_text)
        self.assertIn("/api/focus/lifecycle/update", lifecycle_text)
        self.assertIn("applyVerifiedFocusProjection", memory_text)


if __name__ == "__main__":
    unittest.main()
