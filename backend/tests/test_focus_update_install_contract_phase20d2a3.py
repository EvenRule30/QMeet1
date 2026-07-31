from __future__ import annotations

import unittest
from pathlib import Path


class FocusUpdateInstallContractPhase20D2A3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[2]

    def _read(self, relative_path: str) -> str:
        path = self.repo_root / relative_path
        self.assertTrue(path.exists(), f"Required takeover file is missing: {relative_path}")
        return path.read_text(encoding="utf-8")

    def test_backend_update_executor_and_route_are_installed(self) -> None:
        lifecycle = self._read("backend/app/focus/lifecycle.py")
        router = self._read("backend/app/routers/focus_lifecycle.py")

        self.assertIn("class NativeFocusUpdateRequest", lifecycle)
        self.assertIn("def update_focus_verified", lifecycle)
        self.assertIn('operation: Literal["update_focus"]', lifecycle)
        self.assertIn('@router.post("/update"', router)
        self.assertIn("update_focus_verified", router)

    def test_frontend_verified_update_and_projection_are_installed(self) -> None:
        client = self._read("src/app/lib/nativeFocusLifecycle.ts")
        handler = self._read("src/app/commandHandlers/memory.ts")

        self.assertIn("export async function updateNativeFocusVerified", client)
        self.assertIn("/api/focus/lifecycle/update", client)
        self.assertIn("applyVerifiedFocusProjection(activeSession)", handler)
        self.assertIn("commandMatch.command === 'update-focus-session'", handler)
        self.assertIn("await updateNativeFocusVerified", handler)

    def test_rename_my_focus_cannot_fall_through_to_chat(self) -> None:
        command_router = self._read("backend/app/routers/command.py")

        self.assertIn("(?:the|my|our|current|active)", command_router)
        self.assertIn('action="update_focus_session"', command_router)
        self.assertIn('frontend_command=f"set current focus on {title}"', command_router)


if __name__ == "__main__":
    unittest.main()
