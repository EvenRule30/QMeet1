from __future__ import annotations

import re
import unittest
from pathlib import Path


class FocusContextAwareTasksAndRenderingPhase20NTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[2]
        cls.context_client = (
            cls.root / "src/app/lib/nativeFocusContext.ts"
        ).read_text(encoding="utf-8")
        cls.native_tasks = (
            cls.root / "src/app/lib/nativeFocusTasks.ts"
        ).read_text(encoding="utf-8")
        cls.chat_panel = (
            cls.root / "src/app/components/ChatPanel.tsx"
        ).read_text(encoding="utf-8")

    def test_canonical_state_reader_carries_stakeholders_into_task_context(self) -> None:
        self.assertIn("stakeholders?: string[]", self.context_client)
        self.assertIn(
            "const stakeholders = normalizeStringList(record.stakeholders) ?? [];",
            self.context_client,
        )
        self.assertIn("stakeholders,", self.context_client)

    def test_task_generation_uses_stakeholders_without_replacing_verified_bridge(self) -> None:
        self.assertIn("buildNativeFocusContextTaskTitles(context)", self.native_tasks)
        self.assertIn("readNativeFocusContext(activeSession.id)", self.native_tasks)
        self.assertIn("(context.stakeholders ?? []).map", self.context_client)
        self.assertIn("`Tailor the result to the Focus audience: ${value}`", self.context_client)
        self.assertIn("selected.length < 3", self.context_client)
        self.assertIn("return uniqueContextTaskTitles(selected).slice(0, 3)", self.context_client)

    def test_actionable_context_task_categories_remain_available(self) -> None:
        for marker in (
            "Check the plan against this constraint:",
            "Make sure the result includes:",
            "Carry out the decision:",
            "Find an option that matches this preference:",
        ):
            self.assertIn(marker, self.context_client)

    def test_known_facts_remain_context_but_are_not_promoted_to_tasks(self) -> None:
        self.assertIn("knownFacts: string[]", self.context_client)
        self.assertIn("section('Known details', context.knownFacts)", self.context_client)
        self.assertNotIn("Use this known detail in the plan:", self.context_client)
        self.assertNotIn("context.knownFacts.map(", self.context_client)

    def test_summary_can_surface_stakeholders(self) -> None:
        self.assertIn("section('Stakeholders', context.stakeholders ?? [])", self.context_client)

    def test_inline_number_normalization_does_not_treat_year_as_list_marker(self) -> None:
        self.assertIn(r".replace(/\s+([1-9]\d?[.)]\s+)/g, '\n$1')", self.chat_panel)
        self.assertNotIn(r".replace(/\s+(\d+[.)]\s+)/g, '\n$1')", self.chat_panel)
        sample = (
            "1. Decide the finished result\n"
            "2. Check the plan by August 8, 2026.\n"
            "3. Tailor the review for the audience\n"
            "4. Write the first concrete step\n"
            "5. Ask QMeet for help"
        )
        normalized = re.sub(r"\s+([1-9]\d?[.)]\s+)", r"\n\1", sample)
        self.assertIn("August 8, 2026.", normalized)
        self.assertNotIn("August 8,\n2026.", normalized)
        self.assertEqual(
            re.findall(r"(?m)^([1-5])[.)]\s", normalized),
            ["1", "2", "3", "4", "5"],
        )


if __name__ == "__main__":
    unittest.main()
