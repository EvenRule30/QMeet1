from __future__ import annotations

import unittest
from pathlib import Path


class FocusOwnershipPlannerInstallContractPhase20HTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.readiness = (cls.root / "app/focus/readiness.py").read_text(encoding="utf-8")
        cls.router = (cls.root / "app/routers/focus.py").read_text(encoding="utf-8")
        cls.frontend = (
            cls.root.parent / "src/app/components/FocusResponseHealth.tsx"
        ).read_text(encoding="utf-8")

    def test_status_route_supplies_native_ownership_snapshot(self) -> None:
        self.assertIn("get_native_focus_ownership_readiness", self.router)
        self.assertIn("ownership_readiness=ownership_readiness", self.router)
        self.assertIn('"ownershipReadiness": ownership_readiness', self.router)

    def test_readiness_exposes_required_ownership_gate(self) -> None:
        self.assertIn('"ownershipGate": ownership_gate', self.readiness)
        self.assertIn('"required": True', self.readiness)
        self.assertIn('"legacyProjectionRetired": legacy_retired', self.readiness)
        self.assertIn('"fallbackBlocked": fallback_blocked', self.readiness)

    def test_automatic_promotion_remains_disabled(self) -> None:
        self.assertIn('"automaticPromotion": False', self.readiness)
        self.assertNotIn("set_focus_mode", self.readiness)
        self.assertNotIn("os.environ[", self.readiness)

    def test_success_history_requires_explicit_gate_to_be_ready(self) -> None:
        self.assertIn("not ownership_required or ownership_ready", self.readiness)
        self.assertIn('"ownershipGateStatus"', self.readiness)
        self.assertIn('"ownershipVersion"', self.readiness)

    def test_frontend_surfaces_compact_ownership_gate(self) -> None:
        self.assertIn("type OwnershipGate", self.frontend)
        self.assertIn("Focus Ownership", self.frontend)
        self.assertIn("Ownership version", self.frontend)
        self.assertIn("Legacy projection", self.frontend)
        self.assertIn("Ownership blockers", self.frontend)


if __name__ == "__main__":
    unittest.main()
