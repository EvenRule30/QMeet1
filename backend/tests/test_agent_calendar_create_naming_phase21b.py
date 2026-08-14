from __future__ import annotations

import unittest
from pathlib import Path

from app import qmeet_agent_shadow as shadow


ROOT = Path(__file__).resolve().parents[2]


class AgentCalendarCreateNamingPhase21BTests(unittest.TestCase):
    def test_prompt_requests_human_friendly_semantic_event_titles(self) -> None:
        prompt = shadow.AGENT_SHADOW_SYSTEM_PROMPT
        self.assertIn("concise human-friendly event title", prompt)
        self.assertIn('"a business meeting" -> "Business Meeting"', prompt)
        self.assertIn('"time to practice my presentation" -> "Presentation Practice"', prompt)
        self.assertIn("Do not invent people, companies, locations, goals", prompt)

    def test_fallback_title_cleanup_removes_articles_without_inventing_details(self) -> None:
        self.assertEqual(
            shadow._clean_fallback_calendar_create_title("a business meeting"),
            "Business Meeting",
        )
        self.assertEqual(
            shadow._clean_fallback_calendar_create_title("Dungeons and Dragons session"),
            "Dungeons and Dragons Session",
        )
        self.assertEqual(
            shadow._clean_fallback_calendar_create_title("lunch with Sarah"),
            "Lunch with Sarah",
        )

    def test_fallback_create_proposal_uses_cleaned_title(self) -> None:
        result = shadow._calendar_create_arguments(
            "schedule a business meeting tomorrow at 3 PM"
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["title"], "Business Meeting")
        self.assertEqual(result["day"], "tomorrow")
        self.assertEqual(result["time"], "3 PM")

    def test_frontend_exports_shared_conservative_title_cleanup(self) -> None:
        source = (
            ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts"
        ).read_text(encoding="utf-8")
        self.assertIn("export function normalizePromotedCalendarCreateTitle", source)
        self.assertIn("replace(/^(?:a|an|the|my|our)", source)
        self.assertIn("CALENDAR_TITLE_SMALL_WORDS", source)
        self.assertIn("title: normalized.title", source)

    def test_exact_and_agent_create_confirmation_share_normalized_title(self) -> None:
        source = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
        self.assertIn("normalizePromotedCalendarCreateTitle", source)
        self.assertIn(
            "const targetTitle = normalizePromotedCalendarCreateTitle(",
            source,
        )
        self.assertIn("commandMatch.calendarEvent?.title?.trim() ?? ''", source)
        self.assertIn("const frontendCommand = `add event ${targetView} at ${targetTime} called ${targetTitle}`;", source)
        self.assertIn("create a Google Calendar event", source)


if __name__ == "__main__":
    unittest.main()
