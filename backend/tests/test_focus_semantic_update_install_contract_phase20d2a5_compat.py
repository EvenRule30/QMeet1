from __future__ import annotations

import re
import unittest
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent


class SemanticFocusUpdateInstallContractTests(unittest.TestCase):
    def test_legacy_update_preflight_remains_available_for_compatibility(self) -> None:
        router_path = BACKEND_ROOT / "app" / "routers" / "focus_lifecycle.py"
        service_path = (
            BACKEND_ROOT / "app" / "focus" / "semantic_update_preflight.py"
        )
        router_text = router_path.read_text(encoding="utf-8")
        service_text = service_path.read_text(encoding="utf-8")

        self.assertIn('"/semantic-update/interpret"', router_text)
        self.assertIn("semantic_focus_update_preflight", router_text)
        self.assertIn("SemanticFocusUpdatePreflightResult", service_text)

    def test_observation_monkeypatch_is_not_installed(self) -> None:
        main_path = BACKEND_ROOT / "app" / "main.py"
        main_text = main_path.read_text(encoding="utf-8")

        self.assertNotIn(
            "install_semantic_focus_update_observation_policy",
            main_text,
        )
        self.assertIn("FocusShadowMiddleware", main_text)
        self.assertIn("focus_lifecycle", main_text)

    def test_general_command_router_does_not_run_semantic_lifecycle_model(self) -> None:
        command_path = BACKEND_ROOT / "app" / "routers" / "command.py"
        command_text = command_path.read_text(encoding="utf-8")

        self.assertNotIn("semantic_focus_update_command", command_text)
        self.assertNotIn("semantic_focus_lifecycle_preflight", command_text)
        self.assertIn("interpret_qmeet_orchestrator", command_text)

    def test_frontend_uses_unified_lifecycle_preflight_before_interpreter(self) -> None:
        app_path = REPO_ROOT / "src" / "app" / "App.tsx"
        helper_path = (
            REPO_ROOT / "src" / "app" / "lib" / "semanticFocusLifecycle.ts"
        )
        backend_preflight_path = (
            BACKEND_ROOT / "app" / "focus" / "semantic_lifecycle_preflight.py"
        )
        app_text = app_path.read_text(encoding="utf-8")
        helper_text = helper_path.read_text(encoding="utf-8")
        backend_preflight_text = backend_preflight_path.read_text(encoding="utf-8")

        preflight_index = app_text.index(
            "await interpretSemanticFocusLifecycle(trimmed)"
        )
        generic_index = app_text.index(
            "await interpretCommandIntent(trimmed)",
            preflight_index,
        )
        self.assertLess(preflight_index, generic_index)
        self.assertNotIn("interpretSemanticFocusUpdate(trimmed)", app_text)

        frontend_match = re.search(
            r"SEMANTIC_FOCUS_LIFECYCLE_BRIDGE_VERSION\s*=\s*['\"]([^'\"]+)['\"]",
            helper_text,
        )
        backend_match = re.search(
            r"SEMANTIC_LIFECYCLE_BRIDGE_VERSION\s*=\s*['\"]([^'\"]+)['\"]",
            backend_preflight_text,
        )
        self.assertIsNotNone(frontend_match)
        self.assertIsNotNone(backend_match)
        assert frontend_match is not None
        assert backend_match is not None
        self.assertEqual(frontend_match.group(1), backend_match.group(1))
        self.assertTrue(frontend_match.group(1).startswith("phase20d2a5"))

        self.assertIn(
            "/api/focus/lifecycle/semantic/interpret",
            helper_text,
        )

    def test_typed_lifecycle_preflight_reuses_verified_update_executor(self) -> None:
        helper_path = (
            REPO_ROOT / "src" / "app" / "lib" / "semanticFocusLifecycle.ts"
        )
        memory_path = (
            REPO_ROOT / "src" / "app" / "commandHandlers" / "memory.ts"
        )
        lifecycle_path = (
            REPO_ROOT / "src" / "app" / "lib" / "nativeFocusLifecycle.ts"
        )
        helper_text = helper_path.read_text(encoding="utf-8")
        memory_text = memory_path.read_text(encoding="utf-8")
        lifecycle_text = lifecycle_path.read_text(encoding="utf-8")

        self.assertIn("command: 'update-focus-session'", helper_text)
        self.assertIn("updateNativeFocusVerified", memory_text)
        self.assertIn("/api/focus/lifecycle/update", lifecycle_text)
        self.assertIn("applyVerifiedFocusProjection", memory_text)


if __name__ == "__main__":
    unittest.main()
