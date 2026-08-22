import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DAILY_BRIEF_PATH = REPO_ROOT / "backend" / "app" / "daily_brief.py"


class DailyBriefGroundingPhase21I1CTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = DAILY_BRIEF_PATH.read_text(encoding="utf-8")

    def test_task_wording_cannot_create_fake_urgency(self):
        self.assertIn(
            "Do not infer urgency, importance, deadlines, or imminence from task wording alone.",
            self.source,
        )
        self.assertIn('Words such as "meeting", "invoice", "review", "prepare", or "final"', self.source)

    def test_task_calendar_relationship_must_be_verified(self):
        self.assertIn(
            "Do not assume a task mentioning a meeting refers to any Calendar event",
            self.source,
        )

    def test_empty_calendar_does_not_imply_task_urgency(self):
        self.assertIn(
            "do not use that fact to imply that a task is urgent or tied to an unseen meeting",
            self.source,
        )

    def test_brief_defaults_to_compact_evidence_grounded_sequence(self):
        self.assertIn("Default to one compact paragraph of 2-4 sentences.", self.source)
        self.assertIn("Never manufacture urgency to justify the order.", self.source)
        self.assertIn('"Let me know if..."', self.source)


if __name__ == "__main__":
    unittest.main()
