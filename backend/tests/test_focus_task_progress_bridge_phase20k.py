from __future__ import annotations

import copy
import importlib.util
import sys
import types
import unittest
from contextlib import contextmanager
from enum import Enum
from pathlib import Path
from threading import RLock
from unittest.mock import patch

from pydantic import BaseModel, ConfigDict, Field


class FakeFocusStatus(str, Enum):
    INACTIVE = "inactive"
    CLARIFYING = "clarifying"
    ACTIVE = "active"
    WAITING = "waiting"
    READY = "ready"
    COMPLETE = "complete"


class FakeFocusEventType(str, Enum):
    FOCUS_STARTED = "focus_started"
    FOCUS_COMPLETED = "focus_completed"
    FOCUS_ENDED = "focus_ended"
    FIELD_SET = "field_set"
    QUESTION_SET = "question_set"
    NEXT_ACTION_SET = "next_action_set"
    MILESTONE_COMPLETED = "milestone_completed"


class FakePendingQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = ""
    question: str = ""
    askedAt: str = ""


class FakePendingAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str = ""
    description: str = ""
    createdAt: str = ""


class FakeFocusState(BaseModel):
    model_config = ConfigDict(extra="ignore")
    focusId: str = ""
    title: str = ""
    objective: str = ""
    status: FakeFocusStatus = FakeFocusStatus.INACTIVE
    completedMilestones: list[str] = Field(default_factory=list)
    pendingQuestion: FakePendingQuestion | None = None
    pendingAction: FakePendingAction | None = None
    nextAction: str = ""


class FakeFocusEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    focusId: str = ""
    type: FakeFocusEventType
    payload: dict[str, object] = Field(default_factory=dict)
    sourceTurnId: str = ""
    source: str = ""
    createdAt: str = ""


class FakeFocusLog(BaseModel):
    events: list[FakeFocusEvent] = Field(default_factory=list)


class BridgeHarness:
    def __init__(
        self,
        *,
        source_path: Path,
        state: FakeFocusState,
        tasks: list[dict[str, object]],
        linked_task_ids: list[str] | None = None,
        ancestor_focus_id: str = "focus-original",
        fail_first_focus_write: bool = False,
    ) -> None:
        self.source_path = source_path
        self.base_state = state.model_copy(deep=True)
        self.focus_id = state.focusId
        self.ancestor_focus_id = ancestor_focus_id
        self.focus_holder = {"doc": FakeFocusLog()}
        self.memory_holder = {
            "payload": {
                "tasks": copy.deepcopy(tasks),
                "recentActions": [],
                "notes": [],
                "activeSession": None,
                "recentFocusSessions": [],
                "visualContext": {},
            }
        }
        self.linked_task_ids = linked_task_ids or [str(task["id"]) for task in tasks]
        self.relationships = {
            "tasksByFocusId": {
                ancestor_focus_id: [
                    {
                        "taskIds": list(self.linked_task_ids),
                        "tasks": [
                            {
                                "id": task["id"],
                                "title": task["title"],
                                "createdAt": task.get("createdAt", "2026-08-06T15:00:00-07:00"),
                            }
                            for task in tasks
                            if str(task["id"]) in self.linked_task_ids
                        ],
                    }
                ]
            }
        }
        self.event_counter = 0
        self.focus_write_count = 0
        self.fail_first_focus_write = fail_first_focus_write

    def reduce_events(self, events: list[FakeFocusEvent]) -> FakeFocusState:
        state = self.base_state.model_copy(deep=True)
        for event in events:
            if event.focusId != state.focusId:
                continue
            if event.type == FakeFocusEventType.MILESTONE_COMPLETED:
                value = " ".join(str(event.payload.get("value", "")).split()).strip()
                if value and value.casefold() not in {
                    item.casefold() for item in state.completedMilestones
                }:
                    state.completedMilestones.append(value)
                if state.status not in {
                    FakeFocusStatus.COMPLETE,
                    FakeFocusStatus.WAITING,
                }:
                    state.status = FakeFocusStatus.ACTIVE
            elif event.type == FakeFocusEventType.FIELD_SET:
                if str(event.payload.get("field", "")) == "status":
                    state.status = FakeFocusStatus(
                        str(event.payload.get("value", "active"))
                    )
            elif event.type == FakeFocusEventType.NEXT_ACTION_SET:
                state.nextAction = str(event.payload.get("value", "")).strip()
        return state

    def read_focus(self) -> FakeFocusLog:
        return self.focus_holder["doc"].model_copy(deep=True)

    def write_focus(self, document: FakeFocusLog) -> None:
        self.focus_write_count += 1
        if self.fail_first_focus_write and self.focus_write_count == 1:
            raise RuntimeError("simulated focus write failure")
        self.focus_holder["doc"] = document.model_copy(deep=True)

    def new_event(
        self,
        event_type: FakeFocusEventType,
        *,
        focus_id: str = "",
        payload: dict[str, object] | None = None,
        source_turn_id: str = "",
        source: str = "",
        confidence: float = 1.0,
    ) -> FakeFocusEvent:
        del confidence
        self.event_counter += 1
        return FakeFocusEvent(
            id=f"event-{self.event_counter}",
            focusId=focus_id,
            type=event_type,
            payload=payload or {},
            sourceTurnId=source_turn_id,
            source=source,
            createdAt=f"2026-08-06T15:30:{self.event_counter:02d}-07:00",
        )

    def read_memory(self) -> dict[str, object]:
        return copy.deepcopy(self.memory_holder["payload"])

    def write_memory(
        self,
        tasks: list[dict],
        recent_actions: list[dict] | None = None,
        notes: list[dict] | None = None,
        active_session: dict | None = None,
        recent_focus_sessions: list[dict] | None = None,
        visual_context: dict | None = None,
        **_: object,
    ) -> dict[str, object]:
        self.memory_holder["payload"] = {
            "tasks": copy.deepcopy(tasks),
            "recentActions": copy.deepcopy(recent_actions or []),
            "notes": copy.deepcopy(notes or []),
            "activeSession": copy.deepcopy(active_session),
            "recentFocusSessions": copy.deepcopy(recent_focus_sessions or []),
            "visualContext": copy.deepcopy(visual_context or {}),
        }
        return self.read_memory()

    @contextmanager
    def load(self):
        store_module = types.ModuleType("app.focus.store")
        store_module._STORE_LOCK = RLock()
        store_module._read_log_unlocked = self.read_focus
        store_module._atomic_write_unlocked = self.write_focus
        store_module._new_event = self.new_event
        store_module.reduce_events = self.reduce_events

        summary_module = types.ModuleType("app.focus.summary")
        summary_module._RELATIONSHIP_LOCK = RLock()
        summary_module._read_relationships_unlocked = lambda: copy.deepcopy(
            self.relationships
        )
        summary_module._open_focus_ids = lambda _events: [self.focus_id]

        memory_module = types.ModuleType("app.memory_store")
        memory_module._STORE_LOCK = RLock()
        memory_module._read_payload_unlocked = self.read_memory
        memory_module._write_payload_unlocked = self.write_memory

        models_module = types.ModuleType("app.focus.models")
        models_module.FocusEvent = FakeFocusEvent
        models_module.FocusEventType = FakeFocusEventType
        models_module.FocusState = FakeFocusState
        models_module.FocusStatus = FakeFocusStatus

        lineage_module = types.ModuleType("app.focus.task_lineage")
        lineage_module._focus_lineage_ids = lambda _events, focus_id: [
            focus_id,
            self.ancestor_focus_id,
        ]
        lineage_module._string_list = lambda value: [
            str(item).strip()
            for item in value
            if str(item).strip()
        ] if isinstance(value, list) else []
        lineage_module._task_relationship_records = lambda document, focus_id: [
            record
            for record in (
                document.get("tasksByFocusId", {}).get(focus_id, [])
                if isinstance(document.get("tasksByFocusId"), dict)
                else []
            )
            if isinstance(record, dict)
        ]

        app_module = types.ModuleType("app")
        app_module.memory_store = memory_module
        focus_package = types.ModuleType("app.focus")
        focus_package.store = store_module
        focus_package.summary = summary_module

        module_name = f"phase20k_task_progress_{id(self)}"
        spec = importlib.util.spec_from_file_location(module_name, self.source_path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)

        with patch.dict(
            sys.modules,
            {
                "app": app_module,
                "app.memory_store": memory_module,
                "app.focus": focus_package,
                "app.focus.store": store_module,
                "app.focus.summary": summary_module,
                "app.focus.models": models_module,
                "app.focus.task_lineage": lineage_module,
                module_name: module,
            },
            clear=False,
        ):
            spec.loader.exec_module(module)
            yield module


class FocusTaskProgressBridgePhase20KTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[2]
        cls.source_path = root / "backend/app/focus/task_progress.py"

    @staticmethod
    def tasks() -> list[dict[str, object]]:
        return [
            {
                "id": "task-budget",
                "title": "Check the plan against this constraint: Keep the total cost under $1,000",
                "createdAt": "2026-08-06T15:00:00-07:00",
            },
            {
                "id": "task-warm",
                "title": "Find an option that matches this preference: somewhere warm",
                "createdAt": "2026-08-06T15:00:01-07:00",
            },
        ]

    def request(self, module, *, task_index: int = 0, source_turn_id: str = "turn-1"):
        task = self.tasks()[task_index]
        return module.NativeFocusTaskProgressRequest(
            expectedFocusId="focus-current",
            tasks=[
                {
                    "id": task["id"],
                    "title": task["title"],
                    "completedAt": "2026-08-06T15:31:00-07:00",
                }
            ],
            sourceTurnId=source_turn_id,
            confirmed=True,
        )

    def test_records_memory_completion_and_canonical_progress(self) -> None:
        harness = BridgeHarness(
            source_path=self.source_path,
            state=FakeFocusState(
                focusId="focus-current",
                title="plan a weekend trip",
                objective="choose a destination, dates, and budget",
                status=FakeFocusStatus.ACTIVE,
            ),
            tasks=self.tasks(),
        )
        with harness.load() as module:
            result = module.record_focus_task_progress_verified(self.request(module))

        self.assertTrue(result.verified)
        self.assertEqual(result.outcome, "recorded")
        self.assertEqual(result.nextAction, self.tasks()[1]["title"])
        self.assertFalse(result.allLinkedTasksComplete)
        self.assertIn(self.tasks()[0]["title"], result.state.completedMilestones)
        self.assertEqual(
            harness.memory_holder["payload"]["tasks"][0]["completedAt"],
            "2026-08-06T15:31:00-07:00",
        )
        self.assertTrue(result.verification.focusContinuityPreserved)

    def test_preserves_pending_question_without_changing_asked_at(self) -> None:
        pending = FakePendingQuestion(
            target="follow_up",
            question="What would make this trip a real success for you?",
            askedAt="2026-08-06T15:11:56-07:00",
        )
        harness = BridgeHarness(
            source_path=self.source_path,
            state=FakeFocusState(
                focusId="focus-current",
                title="plan a weekend trip",
                status=FakeFocusStatus.CLARIFYING,
                pendingQuestion=pending,
                nextAction=pending.question,
            ),
            tasks=self.tasks(),
        )
        with harness.load() as module:
            result = module.record_focus_task_progress_verified(self.request(module))

        self.assertEqual(result.state.pendingQuestion, pending)
        self.assertEqual(result.state.status, FakeFocusStatus.CLARIFYING)
        self.assertEqual(result.nextAction, pending.question)
        event_types = [event.type for event in harness.focus_holder["doc"].events]
        self.assertEqual(
            event_types,
            [FakeFocusEventType.MILESTONE_COMPLETED, FakeFocusEventType.FIELD_SET],
        )

    def test_preserves_pending_action_and_waiting_status(self) -> None:
        pending_action = FakePendingAction(
            kind="calendar_write",
            description="Waiting for calendar confirmation",
            createdAt="2026-08-06T15:20:00-07:00",
        )
        harness = BridgeHarness(
            source_path=self.source_path,
            state=FakeFocusState(
                focusId="focus-current",
                title="plan a weekend trip",
                status=FakeFocusStatus.WAITING,
                pendingAction=pending_action,
                nextAction="Confirm the calendar change.",
            ),
            tasks=self.tasks(),
        )
        with harness.load() as module:
            result = module.record_focus_task_progress_verified(self.request(module))

        self.assertEqual(result.state.pendingAction, pending_action)
        self.assertEqual(result.state.status, FakeFocusStatus.WAITING)
        self.assertEqual(result.nextAction, "Confirm the calendar change.")
        self.assertEqual(len(harness.focus_holder["doc"].events), 1)

    def test_all_linked_tasks_complete_requires_focus_review(self) -> None:
        tasks = [self.tasks()[0]]
        harness = BridgeHarness(
            source_path=self.source_path,
            state=FakeFocusState(
                focusId="focus-current",
                title="plan a weekend trip",
                status=FakeFocusStatus.ACTIVE,
            ),
            tasks=tasks,
        )
        with harness.load() as module:
            result = module.record_focus_task_progress_verified(self.request(module))

        self.assertTrue(result.allLinkedTasksComplete)
        self.assertEqual(
            result.nextAction,
            "Review the completed Focus tasks and complete the Focus when ready.",
        )
        self.assertNotEqual(result.state.status, FakeFocusStatus.COMPLETE)

    def test_rejects_unlinked_or_mismatched_task_without_mutation(self) -> None:
        for mode in ("unlinked", "mismatch"):
            with self.subTest(mode=mode):
                harness = BridgeHarness(
                    source_path=self.source_path,
                    state=FakeFocusState(
                        focusId="focus-current",
                        title="plan a weekend trip",
                        status=FakeFocusStatus.ACTIVE,
                    ),
                    tasks=self.tasks(),
                    linked_task_ids=(
                        ["task-warm"] if mode == "unlinked" else None
                    ),
                )
                before = harness.read_memory()
                with harness.load() as module:
                    request = self.request(module)
                    if mode == "mismatch":
                        request.tasks[0].title = "A different task title"
                    with self.assertRaises(module.NativeFocusTaskProgressError):
                        module.record_focus_task_progress_verified(request)
                self.assertEqual(harness.read_memory(), before)
                self.assertEqual(harness.focus_holder["doc"].events, [])

    def test_requires_explicit_confirmation(self) -> None:
        harness = BridgeHarness(
            source_path=self.source_path,
            state=FakeFocusState(
                focusId="focus-current",
                title="plan a weekend trip",
                status=FakeFocusStatus.ACTIVE,
            ),
            tasks=self.tasks(),
        )
        with harness.load() as module:
            request = self.request(module)
            request.confirmed = False
            with self.assertRaises(module.NativeFocusTaskProgressError) as caught:
                module.record_focus_task_progress_verified(request)
        self.assertEqual(caught.exception.code, "confirmation_required")

    def test_same_source_turn_is_idempotently_reused(self) -> None:
        harness = BridgeHarness(
            source_path=self.source_path,
            state=FakeFocusState(
                focusId="focus-current",
                title="plan a weekend trip",
                status=FakeFocusStatus.ACTIVE,
            ),
            tasks=self.tasks(),
        )
        with harness.load() as module:
            request = self.request(module, source_turn_id="turn-reused")
            first = module.record_focus_task_progress_verified(request)
            event_count = len(harness.focus_holder["doc"].events)
            second = module.record_focus_task_progress_verified(request)

        self.assertEqual(first.outcome, "recorded")
        self.assertEqual(second.outcome, "reused")
        self.assertEqual(len(harness.focus_holder["doc"].events), event_count)

    def test_rejects_relationship_source_turn_conflict(self) -> None:
        harness = BridgeHarness(
            source_path=self.source_path,
            state=FakeFocusState(
                focusId="focus-current",
                title="plan a weekend trip",
                status=FakeFocusStatus.ACTIVE,
            ),
            tasks=self.tasks(),
        )
        harness.relationships["summariesByFocusId"] = {
            "focus-current": [
                {"sourceTurnId": "turn-relationship-conflict"},
            ],
        }
        with harness.load() as module:
            with self.assertRaises(module.NativeFocusTaskProgressError) as caught:
                module.record_focus_task_progress_verified(
                    self.request(
                        module,
                        source_turn_id="turn-relationship-conflict",
                    )
                )
        self.assertEqual(caught.exception.code, "source_turn_conflict")

    def test_rejects_source_turn_conflict(self) -> None:
        harness = BridgeHarness(
            source_path=self.source_path,
            state=FakeFocusState(
                focusId="focus-current",
                title="plan a weekend trip",
                status=FakeFocusStatus.ACTIVE,
            ),
            tasks=self.tasks(),
        )
        harness.focus_holder["doc"].events.append(
            FakeFocusEvent(
                id="foreign-event",
                focusId="focus-current",
                type=FakeFocusEventType.NEXT_ACTION_SET,
                payload={"value": "foreign"},
                sourceTurnId="turn-conflict",
                source="another-operation",
                createdAt="2026-08-06T15:30:00-07:00",
            )
        )
        with harness.load() as module:
            with self.assertRaises(module.NativeFocusTaskProgressError) as caught:
                module.record_focus_task_progress_verified(
                    self.request(module, source_turn_id="turn-conflict")
                )
        self.assertEqual(caught.exception.code, "source_turn_conflict")

    def test_focus_write_failure_rolls_back_memory_and_focus(self) -> None:
        harness = BridgeHarness(
            source_path=self.source_path,
            state=FakeFocusState(
                focusId="focus-current",
                title="plan a weekend trip",
                status=FakeFocusStatus.ACTIVE,
            ),
            tasks=self.tasks(),
            fail_first_focus_write=True,
        )
        memory_before = harness.read_memory()
        focus_before = harness.focus_holder["doc"].model_copy(deep=True)
        with harness.load() as module:
            with self.assertRaises(module.NativeFocusTaskProgressError) as caught:
                module.record_focus_task_progress_verified(self.request(module))

        self.assertEqual(caught.exception.code, "write_failed")
        self.assertEqual(harness.read_memory(), memory_before)
        self.assertEqual(harness.focus_holder["doc"], focus_before)


if __name__ == "__main__":
    unittest.main()
