import unittest
from pathlib import Path

from app.post_action_style import compact_success_continuation


REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTER_PATH = REPO_ROOT / "backend" / "app" / "routers" / "tool_continuation.py"


class PostActionReplyStylePhase21I2Tests(unittest.TestCase):
    def test_removes_would_you_like_tail(self):
        text = (
            'Your QMeet Regression Meeting is now on Wednesday at 2 PM. '
            'Would you like help preparing for this meeting or setting related tasks?'
        )
        self.assertEqual(
            compact_success_continuation(text),
            "Your QMeet Regression Meeting is now on Wednesday at 2 PM.",
        )

    def test_removes_let_me_know_tail(self):
        text = (
            'The task "Final Regression Task" is now marked done. '
            'Let me know if you want help planning what to do next.'
        )
        self.assertEqual(
            compact_success_continuation(text),
            'The task "Final Regression Task" is now marked done.',
        )

    def test_removes_if_you_want_just_let_me_know_tail(self):
        text = (
            'The task “Test Short Reply Two” has been saved successfully as a global task. '
            'If you want to manage or review your tasks next, just let me know.'
        )
        self.assertEqual(
            compact_success_continuation(text),
            'The task “Test Short Reply Two” has been saved successfully as a global task.',
        )

    def test_removes_declarative_task_management_tail(self):
        text = (
            'The task "Test Short Reply" has been saved as a global task. '
            'You can now manage it further or add more tasks if needed.'
        )
        self.assertEqual(
            compact_success_continuation(text),
            'The task "Test Short Reply" has been saved as a global task.',
        )

    def test_removes_view_or_manage_capability_ad(self):
        text = (
            'The task "Review report" has been saved globally. '
            'You can now view or manage it in your task list or add related tasks if needed.'
        )
        self.assertEqual(
            compact_success_continuation(text),
            'The task "Review report" has been saved globally.',
        )

    def test_removes_global_task_focus_bookkeeping_and_followup_offer(self):
        text = (
            'The task “Test Short Reply Two” has been saved successfully as a global task. '
            'It is not linked to any active focus session. '
            'If you want to manage or review your tasks next, just let me know.'
        )
        self.assertEqual(
            compact_success_continuation(text),
            'The task “Test Short Reply Two” has been saved successfully as a global task.',
        )

    def test_preserves_meaningful_focus_linkage(self):
        text = (
            'The task "Prepare slides" was saved. '
            'It is linked to your active Focus "Presentation prep".'
        )
        self.assertEqual(compact_success_continuation(text), text)

    def test_preserves_substantive_multi_sentence_reply(self):
        text = (
            "The search found Framework is strongest on repairability. "
            "Recent reviews also praise the modular port system."
        )
        self.assertEqual(compact_success_continuation(text), text)

    def test_preserves_useful_you_can_consequence(self):
        text = (
            "The export finished successfully. "
            "You can now access the saved file at /exports/qmeet-summary.json."
        )
        self.assertEqual(compact_success_continuation(text), text)

    def test_does_not_remove_non_generic_question(self):
        text = "The event is ambiguous. Which of the two meetings did you mean?"
        self.assertEqual(compact_success_continuation(text), text)

    def test_router_applies_filter_after_verified_continuation(self):
        source = ROUTER_PATH.read_text(encoding="utf-8")
        self.assertIn("compact_success_continuation", source)
        self.assertIn("async for chunk in stream_tool_continuation(req):", source)
        self.assertIn('reply = compact_success_continuation("".join(reply_parts))', source)


if __name__ == "__main__":
    unittest.main()
