from __future__ import annotations

from pathlib import Path
import re
import unittest

from app.routers.command import _focus_command_intent


ROOT = Path(__file__).resolve().parents[2]
FRONTEND_COMMANDS = ROOT / "src" / "app" / "commands.ts"


class FocusSummaryPhraseRoutingPhase20E2ATests(unittest.TestCase):
    def test_backend_routes_documented_validation_phrase_to_save(self) -> None:
        intent = _focus_command_intent("save my focus summary")

        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.get("intent"), "command")
        self.assertEqual(intent.get("action"), "save_focus_summary")
        self.assertEqual(intent.get("frontendCommand"), "save focus summary as note")

    def test_backend_keeps_read_only_summary_phrase_distinct(self) -> None:
        intent = _focus_command_intent("summarize my focus")

        self.assertIsNotNone(intent)
        assert intent is not None
        self.assertEqual(intent.get("action"), "summarize_focus_session")

    def test_frontend_parser_accepts_possessive_focus_summary_save_phrase(self) -> None:
        source = FRONTEND_COMMANDS.read_text(encoding="utf-8")
        save_summary_block = re.search(
            r"const\s+saveSummaryPatterns\s*=\s*\[(?P<body>.*?)\];",
            source,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(
            save_summary_block,
            "commands.ts must retain the saveSummaryPatterns command-routing block.",
        )
        assert save_summary_block is not None

        body = save_summary_block.group("body")
        required_segment = (
            r"\s+(?:(?:this|the|my|our|current|active)\s+)*"
            r"(?:focus|session)\s+(?:summary|recap)"
        )
        self.assertIn(
            required_segment,
            body,
            "The save-summary parser must accept possessive wording such as "
            "'save my focus summary'.",
        )
        self.assertIn("'save-focus-summary'", source)


if __name__ == "__main__":
    unittest.main()
