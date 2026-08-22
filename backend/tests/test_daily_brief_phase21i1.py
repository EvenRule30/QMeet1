import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.conversation_lane import ConversationLaneRequest  # noqa: E402
from app.daily_brief import (  # noqa: E402
    DAILY_BRIEF_PROMPT,
    build_daily_brief_input,
    collect_daily_brief_context,
    is_daily_brief_request,
)


class DailyBriefPhase21I1Tests(unittest.TestCase):
    def test_day_planning_language_is_recognized_without_stealing_generic_focus_next(self):
        positives = (
            "what should I do today?",
            "What should I work on today?",
            "what should I work on?",
            "plan my day",
            "help me plan today",
            "How should I spend my day?",
            "give me a game plan for today",
            "what are my priorities for today?",
            "help me prioritize my day",
            "daily brief",
            "morning briefing",
            "start my day",
            "what does my day look like?",
        )
        for message in positives:
            with self.subTest(message=message):
                self.assertTrue(is_daily_brief_request(message))

        negatives = (
            "what should I do next?",
            "what should I do next for this focus?",
            "show my calendar",
            "show my tasks",
            "what is the capital of Japan?",
            "create a meeting today at 3",
        )
        for message in negatives:
            with self.subTest(message=message):
                self.assertFalse(is_daily_brief_request(message))

    @patch("app.daily_brief.list_calendar_events")
    @patch("app.daily_brief.list_memory_tasks")
    @patch("app.daily_brief.active_focus_snapshot")
    def test_context_combines_canonical_focus_open_tasks_and_upcoming_calendar(
        self,
        focus_snapshot,
        memory_tasks,
        calendar_events,
    ):
        focus_snapshot.return_value = {
            "focusId": "focus-1",
            "title": "Finish QMeet demo",
            "objective": "Verify the most important flows",
            "nextAction": "Run the live demo script",
            "status": "active",
            "pendingQuestion": "Old question that should not matter",
        }
        memory_tasks.return_value = {
            "ok": True,
            "tasks": [
                {
                    "id": "task-open",
                    "title": "Prepare demo notes",
                    "createdAt": "2026-08-21T09:00:00-07:00",
                },
                {
                    "id": "task-done",
                    "title": "Finished task",
                    "createdAt": "2026-08-20T09:00:00-07:00",
                    "completedAt": "2026-08-20T12:00:00-07:00",
                },
            ],
        }

        def calendar_side_effect(view):
            if view == "today":
                return {
                    "ok": True,
                    "configured": True,
                    "connected": True,
                    "events": [
                        {
                            "id": "google-today",
                            "title": "Project Meeting",
                            "dateKey": "2026-08-21",
                            "time": "3:00 PM",
                            "allDay": False,
                            "start": "2026-08-21T15:00:00-07:00",
                            "end": "2026-08-21T16:00:00-07:00",
                        }
                    ],
                    "message": "Loaded 1 Google Calendar event.",
                }
            return {
                "ok": True,
                "configured": True,
                "connected": True,
                "events": [],
                "message": "Loaded 0 Google Calendar events.",
            }

        calendar_events.side_effect = calendar_side_effect

        context = collect_daily_brief_context()

        self.assertEqual(context["activeFocus"]["focusId"], "focus-1")
        self.assertEqual(context["activeFocus"]["nextAction"], "Run the live demo script")
        self.assertNotIn("pendingQuestion", context["activeFocus"])
        self.assertEqual(context["tasks"]["openTaskCount"], 1)
        self.assertEqual(
            [task["title"] for task in context["tasks"]["openTasks"]],
            ["Prepare demo notes"],
        )
        self.assertEqual(context["calendar"]["today"]["eventCount"], 1)
        self.assertEqual(
            context["calendar"]["today"]["events"][0]["title"],
            "Project Meeting",
        )
        self.assertTrue(context["calendar"]["today"]["connected"])
        self.assertEqual(calendar_events.call_count, 2)
        calendar_events.assert_any_call("today")
        calendar_events.assert_any_call("tomorrow")

    @patch("app.daily_brief.list_calendar_events")
    @patch("app.daily_brief.list_memory_tasks")
    @patch("app.daily_brief.active_focus_snapshot")
    def test_disconnected_calendar_is_not_represented_as_free_time(
        self,
        focus_snapshot,
        memory_tasks,
        calendar_events,
    ):
        focus_snapshot.return_value = None
        memory_tasks.return_value = {"ok": True, "tasks": []}
        calendar_events.return_value = {
            "ok": True,
            "configured": True,
            "connected": False,
            "events": [],
            "message": "Google Calendar is configured but not authorized yet.",
        }

        context = collect_daily_brief_context()
        today = context["calendar"]["today"]

        self.assertTrue(today["available"])
        self.assertFalse(today["connected"])
        self.assertEqual(today["eventCount"], 0)
        self.assertIn("not authorized", today["message"])

    def test_model_input_contains_verified_cross_capability_context_and_is_read_only(self):
        request = ConversationLaneRequest(
            userMessage="what should I do today?",
            recentConversation=[
                {"role": "assistant", "content": "Earlier unrelated conversation."}
            ],
        )
        context = {
            "generatedAt": "2026-08-21T10:00:00-07:00",
            "activeFocus": {
                "focusId": "focus-1",
                "title": "Demo",
                "objective": "Finish regression",
                "nextAction": "Test Calendar",
            },
            "tasks": {
                "available": True,
                "openTaskCount": 1,
                "openTasks": [{"id": "task-1", "title": "Prepare slides"}],
                "tasksTruncated": False,
            },
            "calendar": {
                "today": {
                    "available": True,
                    "connected": True,
                    "eventCount": 0,
                    "events": [],
                },
                "tomorrow": {
                    "available": True,
                    "connected": True,
                    "eventCount": 0,
                    "events": [],
                },
            },
        }

        messages = build_daily_brief_input(request, context)
        contents = "\n\n".join(item["content"] for item in messages)

        self.assertIn(DAILY_BRIEF_PROMPT, contents)
        self.assertIn("Verified QMeet Daily Brief context", contents)
        self.assertIn('"Finish regression"', contents)
        self.assertIn('"Prepare slides"', contents)
        self.assertIn("This lane is read-only", contents)
        self.assertIn("Never claim that a task, Focus, Calendar event", contents)
        self.assertEqual(messages[-1], {"role": "user", "content": "what should I do today?"})

        # The context must remain serializable data rather than being promoted to
        # tool/developer instructions one field at a time.
        json.dumps(context)

    def test_router_uses_daily_brief_for_conversation_and_legacy_fallbacks(self):
        router_source = (BACKEND / "app" / "routers" / "chat.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("from app.daily_brief import", router_source)
        self.assertIn("if is_daily_brief_request(message):", router_source)
        self.assertIn("if is_daily_brief_request(req.userMessage)", router_source)
        self.assertIn("stream_daily_brief", router_source)
        self.assertIn("generate_daily_brief", router_source)

    def test_daily_brief_module_does_not_import_mutation_services(self):
        source = (BACKEND / "app" / "daily_brief.py").read_text(encoding="utf-8")
        forbidden = (
            "create_memory_task",
            "update_memory_task",
            "delete_memory_task",
            "create_calendar_event",
            "update_calendar_event",
            "delete_calendar_event",
            "append_focus_event",
            "start_focus",
            "end_focus",
        )
        for symbol in forbidden:
            with self.subTest(symbol=symbol):
                self.assertNotIn(symbol, source)


if __name__ == "__main__":
    unittest.main()
