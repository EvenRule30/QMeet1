from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from threading import RLock
from unittest.mock import patch


class FakeFocusEventType(str, Enum):
    FOCUS_STARTED = "focus_started"
    FOCUS_ENDED = "focus_ended"
    FOCUS_COMPLETED = "focus_completed"


@dataclass
class FakeFocusEvent:
    focusId: str
    type: FakeFocusEventType
    payload: dict[str, object] = field(default_factory=dict)


class FakeLog:
    def __init__(self, events: list[FakeFocusEvent]) -> None:
        self.events = events


@contextmanager
def load_lineage_module(
    source_path: Path,
    *,
    events: list[FakeFocusEvent],
    relationships: dict[str, object],
    open_focus_ids: list[str],
):
    store_module = types.ModuleType("app.focus.store")
    store_module._STORE_LOCK = RLock()
    store_module._read_log_unlocked = lambda: FakeLog(events)

    summary_module = types.ModuleType("app.focus.summary")
    summary_module._RELATIONSHIP_LOCK = RLock()
    summary_module._read_relationships_unlocked = lambda: relationships
    summary_module._open_focus_ids = lambda _events: list(open_focus_ids)

    models_module = types.ModuleType("app.focus.models")
    models_module.FocusEvent = FakeFocusEvent
    models_module.FocusEventType = FakeFocusEventType

    app_module = types.ModuleType("app")
    focus_package = types.ModuleType("app.focus")
    focus_package.store = store_module
    focus_package.summary = summary_module

    module_name = "phase20j2_task_lineage_test_module"
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)

    with patch.dict(
        sys.modules,
        {
            "app": app_module,
            "app.focus": focus_package,
            "app.focus.store": store_module,
            "app.focus.summary": summary_module,
            "app.focus.models": models_module,
            module_name: module,
        },
        clear=False,
    ):
        spec.loader.exec_module(module)
        yield module


class FocusResumedTaskLineagePhase20J2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.source_path = root / "backend/app/focus/task_lineage.py"

    def test_resumed_focus_inherits_original_verified_task_ids(self) -> None:
        events = [
            FakeFocusEvent("focus-old", FakeFocusEventType.FOCUS_STARTED),
            FakeFocusEvent("focus-old", FakeFocusEventType.FOCUS_COMPLETED),
            FakeFocusEvent(
                "focus-new",
                FakeFocusEventType.FOCUS_STARTED,
                {"resumedFromFocusId": "focus-old"},
            ),
        ]
        relationships = {
            "tasksByFocusId": {
                "focus-old": [
                    {"taskIds": ["task-budget", "task-warm", "task-days"]},
                ],
            },
        }

        with load_lineage_module(
            self.source_path,
            events=events,
            relationships=relationships,
            open_focus_ids=["focus-new"],
        ) as module:
            self.assertEqual(
                module.get_active_focus_lineage_linked_task_ids(),
                {"task-budget", "task-warm", "task-days"},
            )

    def test_current_and_ancestor_receipts_are_unioned_without_copying(self) -> None:
        events = [
            FakeFocusEvent("focus-old", FakeFocusEventType.FOCUS_STARTED),
            FakeFocusEvent("focus-old", FakeFocusEventType.FOCUS_COMPLETED),
            FakeFocusEvent(
                "focus-new",
                FakeFocusEventType.FOCUS_STARTED,
                {"resumedFromFocusId": "focus-old"},
            ),
        ]
        relationships = {
            "tasksByFocusId": {
                "focus-old": [{"taskIds": ["task-a", "task-b"]}],
                "focus-new": [{"taskIds": ["task-b", "task-c"]}],
            },
        }

        with load_lineage_module(
            self.source_path,
            events=events,
            relationships=relationships,
            open_focus_ids=["focus-new"],
        ) as module:
            self.assertEqual(
                module.get_active_focus_lineage_linked_task_ids(),
                {"task-a", "task-b", "task-c"},
            )

    def test_repeated_resume_follows_the_complete_ancestry_chain(self) -> None:
        events = [
            FakeFocusEvent("focus-a", FakeFocusEventType.FOCUS_STARTED),
            FakeFocusEvent("focus-a", FakeFocusEventType.FOCUS_COMPLETED),
            FakeFocusEvent(
                "focus-b",
                FakeFocusEventType.FOCUS_STARTED,
                {"resumedFromFocusId": "focus-a"},
            ),
            FakeFocusEvent("focus-b", FakeFocusEventType.FOCUS_COMPLETED),
            FakeFocusEvent(
                "focus-c",
                FakeFocusEventType.FOCUS_STARTED,
                {"resumedFromFocusId": "focus-b"},
            ),
        ]
        relationships = {
            "tasksByFocusId": {
                "focus-a": [{"taskIds": ["task-original"]}],
                "focus-b": [{"taskIds": ["task-second-run"]}],
            },
        }

        with load_lineage_module(
            self.source_path,
            events=events,
            relationships=relationships,
            open_focus_ids=["focus-c"],
        ) as module:
            self.assertEqual(
                module._focus_lineage_ids(events, "focus-c"),
                ["focus-c", "focus-b", "focus-a"],
            )
            self.assertEqual(
                module.get_active_focus_lineage_linked_task_ids(),
                {"task-original", "task-second-run"},
            )

    def test_unrelated_focus_receipts_are_excluded(self) -> None:
        events = [
            FakeFocusEvent("focus-old", FakeFocusEventType.FOCUS_STARTED),
            FakeFocusEvent("focus-old", FakeFocusEventType.FOCUS_COMPLETED),
            FakeFocusEvent(
                "focus-new",
                FakeFocusEventType.FOCUS_STARTED,
                {"resumedFromFocusId": "focus-old"},
            ),
            FakeFocusEvent("focus-other", FakeFocusEventType.FOCUS_COMPLETED),
        ]
        relationships = {
            "tasksByFocusId": {
                "focus-old": [{"taskIds": ["task-related"]}],
                "focus-other": [{"taskIds": ["task-unrelated"]}],
            },
        }

        with load_lineage_module(
            self.source_path,
            events=events,
            relationships=relationships,
            open_focus_ids=["focus-new"],
        ) as module:
            self.assertEqual(
                module.get_active_focus_lineage_linked_task_ids(),
                {"task-related"},
            )

    def test_no_or_multiple_open_focuses_return_no_membership(self) -> None:
        events = [FakeFocusEvent("focus-a", FakeFocusEventType.FOCUS_STARTED)]
        relationships = {
            "tasksByFocusId": {
                "focus-a": [{"taskIds": ["task-a"]}],
            },
        }

        for open_focus_ids in ([], ["focus-a", "focus-b"]):
            with self.subTest(open_focus_ids=open_focus_ids):
                with load_lineage_module(
                    self.source_path,
                    events=events,
                    relationships=relationships,
                    open_focus_ids=open_focus_ids,
                ) as module:
                    self.assertEqual(
                        module.get_active_focus_lineage_linked_task_ids(),
                        set(),
                    )

    def test_lineage_cycle_is_bounded_and_deduplicated(self) -> None:
        events = [
            FakeFocusEvent(
                "focus-a",
                FakeFocusEventType.FOCUS_STARTED,
                {"resumedFromFocusId": "focus-b"},
            ),
            FakeFocusEvent(
                "focus-b",
                FakeFocusEventType.FOCUS_STARTED,
                {"resumedFromFocusId": "focus-a"},
            ),
        ]

        with load_lineage_module(
            self.source_path,
            events=events,
            relationships={"tasksByFocusId": {}},
            open_focus_ids=["focus-a"],
        ) as module:
            self.assertEqual(
                module._focus_lineage_ids(events, "focus-a"),
                ["focus-a", "focus-b"],
            )


if __name__ == "__main__":
    unittest.main()
