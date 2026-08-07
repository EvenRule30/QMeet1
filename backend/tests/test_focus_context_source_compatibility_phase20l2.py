from __future__ import annotations

import unittest
from types import SimpleNamespace

from app.focus.context import _context_turn_group_is_exclusive
from app.focus.models import FocusEventType


class FocusContextSourceCompatibilityPhase20L2Tests(unittest.TestCase):
    def test_legacy_receipt_without_source_remains_native_compatible(self) -> None:
        receipt = SimpleNamespace(
            focusId="focus-trip",
            type=FocusEventType.LIST_ITEM_ADDED,
            payload={"field": "preferences", "value": "somewhere warm"},
        )

        self.assertTrue(
            _context_turn_group_is_exclusive([receipt], focus_id="focus-trip")
        )

    def test_explicit_foreign_mutation_source_is_still_rejected(self) -> None:
        receipt = SimpleNamespace(
            focusId="focus-trip",
            type=FocusEventType.LIST_ITEM_ADDED,
            source="semantic-focus-lifecycle",
            payload={"field": "preferences", "value": "somewhere warm"},
        )

        self.assertFalse(
            _context_turn_group_is_exclusive([receipt], focus_id="focus-trip")
        )

    def test_response_telemetry_remains_neutral(self) -> None:
        receipt = SimpleNamespace(
            focusId="focus-trip",
            type=FocusEventType.RESPONSE_CANDIDATE,
            source="focus-response-candidate",
            payload={},
        )

        self.assertTrue(
            _context_turn_group_is_exclusive([receipt], focus_id="focus-trip")
        )


if __name__ == "__main__":
    unittest.main()
