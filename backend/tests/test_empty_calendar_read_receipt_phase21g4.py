import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TOAST_UTILS = REPO_ROOT / "src" / "app" / "lib" / "toastUtils.ts"


class EmptyCalendarReadReceiptPhase21G4Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = TOAST_UTILS.read_text(encoding="utf-8")

    def test_empty_calendar_read_is_explicitly_exempted_from_failure_language(self) -> None:
        self.assertIn("SUCCESSFUL_EMPTY_CALENDAR_READ_RE", self.source)
        self.assertIn(
            "^No (?:Google Calendar|local calendar|calendar) events saved for .+\\.$",
            self.source,
        )
        self.assertIn(
            "if (SUCCESSFUL_EMPTY_CALENDAR_READ_RE.test(trimmed))",
            self.source,
        )
        self.assertIn("return false;", self.source)

    def test_generic_failure_language_remains_fail_closed(self) -> None:
        self.assertRegex(
            self.source,
            re.compile(
                r"could not\|did not\|failed\|error\|not connected\|not supported\|no \|none\|missing\|unavailable\|denied"
            ),
        )
        self.assertNotIn("return !/\\bno\\b/i.test", self.source)

    def test_real_calendar_no_match_language_is_not_whitelisted(self) -> None:
        whitelist_match = re.search(
            r"SUCCESSFUL_EMPTY_CALENDAR_READ_RE\s*=\s*\n?\s*/(.+?)/i;",
            self.source,
        )
        self.assertIsNotNone(whitelist_match)
        pattern = re.compile(whitelist_match.group(1), re.IGNORECASE)
        self.assertIsNotNone(
            pattern.fullmatch("No Google Calendar events saved for today.")
        )
        self.assertIsNotNone(
            pattern.fullmatch(
                "No Google Calendar events saved for Monday, August 24, 2026."
            )
        )
        self.assertIsNone(
            pattern.fullmatch(
                'No Google Calendar event matched "Project Meeting" at 3 PM.'
            )
        )


if __name__ == "__main__":
    unittest.main()
