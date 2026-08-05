from __future__ import annotations

import unittest
from pathlib import Path


class NativeFocusResumeInstallContractPhase20D2C1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.lifecycle = (cls.repo_root / "backend/app/focus/lifecycle.py").read_text(encoding="utf-8")
        cls.router = (cls.repo_root / "backend/app/routers/focus_lifecycle.py").read_text(encoding="utf-8")
        cls.client = (cls.repo_root / "src/app/lib/nativeFocusLifecycle.ts").read_text(encoding="utf-8")
        cls.memory = (cls.repo_root / "src/app/commandHandlers/memory.ts").read_text(encoding="utf-8")

    def test_backend_exposes_verified_resume_executor(self) -> None:
        self.assertIn("class NativeFocusResumeRequest", self.lifecycle)
        self.assertIn("def resume_focus_verified(", self.lifecycle)
        self.assertIn('operation: Literal["resume_focus"]', self.lifecycle)
        self.assertIn("historicalFocusPreserved", self.lifecycle)
        self.assertIn("resumeEventPersisted", self.lifecycle)

    def test_router_exposes_resume_endpoint(self) -> None:
        self.assertIn('@router.post("/resume"', self.router)
        self.assertIn("resume_focus_verified(request)", self.router)
        self.assertIn('"resume_focus"', self.router)

    def test_frontend_client_requires_canonical_resume_proof(self) -> None:
        self.assertIn("export async function resumeNativeFocusVerified", self.client)
        self.assertIn("/api/focus/lifecycle/resume", self.client)
        self.assertIn("isVerifiedNativeFocusResumeResult", self.client)
        self.assertIn("historicalFocusPreserved === true", self.client)
        self.assertIn("resumeEventPersisted === true", self.client)

    def test_memory_handler_intercepts_resume_before_legacy_core(self) -> None:
        native_position = self.memory.index("commandMatch.command === 'resume-last-focus-session'")
        fallback_position = self.memory.index("return handleMemoryCommandCore(commandMatch, deps);")
        self.assertLess(native_position, fallback_position)
        self.assertIn("resumeNativeFocusVerified", self.memory)
        self.assertIn("applyVerifiedFocusProjection(activeSession)", self.memory)
        self.assertIn("describeNativeFocusResumeFailure", self.memory)

    def test_resume_does_not_require_app_or_semantic_bridge_changes(self) -> None:
        self.assertNotIn("resume-focus-session", self.memory)
        self.assertIn("resume-last-focus-session", self.memory)


if __name__ == "__main__":
    unittest.main()
