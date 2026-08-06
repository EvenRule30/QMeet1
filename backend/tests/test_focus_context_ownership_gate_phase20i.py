from __future__ import annotations

import unittest
from pathlib import Path


class FocusContextOwnershipGatePhase20ITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[2]
        cls.ownership = (cls.root / "backend/app/focus/ownership.py").read_text(encoding="utf-8")
        cls.context = (cls.root / "backend/app/focus/context.py").read_text(encoding="utf-8")
        cls.wrapper = (cls.root / "src/app/commandHandlers/memory.ts").read_text(encoding="utf-8")

    def test_context_is_an_eighth_required_native_write_surface(self) -> None:
        self.assertIn("get_native_focus_context_health", self.ownership)
        self.assertIn('"add_focus_context"', self.ownership)
        self.assertIn('"addFocusContext"', self.ownership)

    def test_context_health_survives_backend_restart(self) -> None:
        self.assertIn("QMEET_FOCUS_CONTEXT_HEALTH_FILE", self.context)
        self.assertIn("_atomic_write_health_unlocked", self.context)
        self.assertIn("get_native_focus_context_health", self.context)

    def test_source_audit_requires_context_native_executor(self) -> None:
        self.assertIn("addNativeFocusContextVerified", self.ownership)
        self.assertIn("phase20i-context:", self.ownership)
        self.assertIn("objectivePreserved", self.ownership)
        self.assertIn("NATIVE_FOCUS_LIFECYCLE_OWNERSHIP_VERSION = 'phase20i'", self.wrapper)


if __name__ == "__main__":
    unittest.main()
