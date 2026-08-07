from __future__ import annotations

import unittest

from app.focus.context import _context_turn_group_is_exclusive
from app.focus.models import FocusEvent, FocusEventType


class FocusContextVerificationTelemetryPhase20L1Tests(unittest.TestCase):
    def _event(
        self,
        event_type: FocusEventType,
        *,
        source: str,
        focus_id: str = "focus-trip",
    ) -> FocusEvent:
        return FocusEvent(
            id=f"event-{event_type.value}-{source}",
            focusId=focus_id,
            type=event_type,
            payload={},
            sourceTurnId="phase20l1-turn",
            source=source,
            createdAt="2026-08-06T16:25:00-07:00",
        )

    def test_response_telemetry_does_not_break_context_turn_ownership(self) -> None:
        events = [
            self._event(
                FocusEventType.TURN_PLANNED,
                source="native-focus-context",
            ),
            self._event(
                FocusEventType.LIST_ITEM_ADDED,
                source="native-focus-context",
            ),
            self._event(
                FocusEventType.QUESTION_CLEARED,
                source="native-focus-context",
            ),
            self._event(
                FocusEventType.RESPONSE_CANDIDATE,
                source="focus-response-candidate",
            ),
            self._event(
                FocusEventType.RESPONSE_SELECTION,
                source="focus-response-selection",
            ),
            self._event(
                FocusEventType.ASSISTANT_REPLIED,
                source="assistant-response",
            ),
        ]
        self.assertTrue(
            _context_turn_group_is_exclusive(events, focus_id="focus-trip")
        )

    def test_non_context_mutation_still_conflicts(self) -> None:
        events = [
            self._event(
                FocusEventType.TURN_PLANNED,
                source="native-focus-context",
            ),
            self._event(
                FocusEventType.LIST_ITEM_ADDED,
                source="different-operation",
            ),
        ]
        self.assertFalse(
            _context_turn_group_is_exclusive(events, focus_id="focus-trip")
        )

    def test_response_telemetry_for_another_focus_still_conflicts(self) -> None:
        events = [
            self._event(
                FocusEventType.TURN_PLANNED,
                source="native-focus-context",
            ),
            self._event(
                FocusEventType.RESPONSE_CANDIDATE,
                source="focus-response-candidate",
                focus_id="focus-other",
            ),
        ]
        self.assertFalse(
            _context_turn_group_is_exclusive(events, focus_id="focus-trip")
        )


if __name__ == "__main__":
    unittest.main()
