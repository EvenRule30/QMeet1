import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.focus import store
from app.focus.models import FocusEventType


class FocusEventRetentionPhase21H7Tests(unittest.TestCase):
    def test_demo_build_disables_destructive_focus_event_cap(self):
        # Phase 21H7 intentionally leaves the historical store implementation
        # intact but raises its cap at package initialization until snapshot-aware
        # compaction exists.
        self.assertEqual(store._MAX_EVENTS, sys.maxsize)

    def test_canonical_focus_seed_survives_more_than_four_thousand_events(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            focus_path = Path(temp_dir) / "qmeet_focus.json"
            with patch.dict(os.environ, {"QMEET_FOCUS_FILE": str(focus_path)}):
                focus_id = "focus-phase21h7-retention"
                seed = store._new_event(
                    FocusEventType.FOCUS_STARTED,
                    focus_id=focus_id,
                    payload={
                        "title": "Retention regression",
                        "objective": "Keep canonical Focus replayable",
                        "tags": [],
                    },
                    source="phase21h7-test",
                )
                observations = [
                    store._new_event(
                        FocusEventType.ASSISTANT_REPLIED,
                        focus_id=focus_id,
                        payload={"text": f"observation-{index}"},
                        source="phase21h7-test",
                    )
                    for index in range(4005)
                ]
                document = store._empty_log()
                document.events.extend([seed, *observations])

                store._atomic_write_unlocked(document)
                persisted = store._read_log_unlocked()

                self.assertEqual(len(persisted.events), 4006)
                self.assertEqual(persisted.events[0].id, seed.id)
                self.assertEqual(
                    persisted.events[0].type,
                    FocusEventType.FOCUS_STARTED,
                )

                replayed = store.reduce_events(persisted.events)
                self.assertEqual(replayed.focusId, focus_id)
                self.assertEqual(replayed.title, "Retention regression")


if __name__ == "__main__":
    unittest.main()
