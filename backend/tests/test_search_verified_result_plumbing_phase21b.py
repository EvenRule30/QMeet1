from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class SearchVerifiedResultPlumbingPhase21BTests(unittest.TestCase):
    def test_search_handler_builds_context_from_actual_response(self) -> None:
        source = (ROOT / "src/app/commandHandlers/search.ts").read_text(encoding="utf-8")
        self.assertIn("continuationContext?: string;", source)
        self.assertIn("buildSearchContinuationContext(response: SearchResponse)", source)
        self.assertIn("summary: compactText(response.summary", source)
        self.assertIn("recommendation: compactText(response.recommendation", source)
        self.assertIn("sources: (response.sources ?? [])", source)
        self.assertIn(
            "continuationContext = buildSearchContinuationContext(searchResponse);",
            source,
        )

    def test_app_passes_handler_context_to_tool_continuation(self) -> None:
        source = (ROOT / "src/app/App.tsx").read_text(encoding="utf-8")
        self.assertIn("continuationContext?: string;", source)
        self.assertIn(
            "toolContext: splitCommandResult.continuationContext,",
            source,
        )

    def test_frontend_continuation_request_transports_context(self) -> None:
        source = (ROOT / "src/app/lib/toolContinuation.ts").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("toolContext?: string;"), 2)
        self.assertIn(
            "toolContext: options.toolContext?.trim() || undefined,",
            source,
        )


if __name__ == "__main__":
    unittest.main()
