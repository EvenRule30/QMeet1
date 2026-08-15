from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "src" / "app" / "App.tsx"
GLOBAL_RESOLVER = ROOT / "src" / "app" / "lib" / "taskCompletionResolver.ts"
FOCUS_RESOLVER = ROOT / "src" / "app" / "lib" / "naturalTaskCompletion.ts"


class AgentTaskCompletionLanguagePhase21C6BTests(unittest.TestCase):
    def test_state_backed_completion_blocks_conversation_before_focus_resolution(self):
        source = APP.read_text(encoding="utf-8")
        gate = source.index("const promotedConversationAllowed")
        focus_resolver = source.index("const naturalTaskCompletionTarget")
        block = source[gate:focus_resolver]

        self.assertIn("!naturalGlobalTaskCompletionRequest", block)
        self.assertNotIn("!naturalGlobalTaskCompletionFallback;", block)

    def test_global_resolver_accepts_passive_completion_language(self):
        source = GLOBAL_RESOLVER.read_text(encoding="utf-8")

        self.assertIn("const passive = trimmed.match(", source)
        self.assertIn("(?:has|have|had)\\s+been", source)
        self.assertIn("(?:was|were|is|are)", source)
        self.assertIn("isCompletionVerbToken(passive[2])", source)

    def test_completion_typo_tolerance_is_generic_not_phrase_specific(self):
        source = GLOBAL_RESOLVER.read_text(encoding="utf-8")

        self.assertIn("function differsByAtMostOneEdit(", source)
        self.assertIn("COMPLETION_VERB_FORMS.some(", source)
        self.assertNotIn("revewed", source)

    def test_focus_linked_resolver_accepts_passive_and_typo_tolerant_language(self):
        source = FOCUS_RESOLVER.read_text(encoding="utf-8")

        self.assertIn("function looksLikeCompletedWorkStatement(", source)
        self.assertIn("canonicalCompletionVerb(passive[2])", source)
        self.assertIn("tolerateCompletionVerbTypos: true", source)
        self.assertIn("openFocusLinkedTasks(tasks, activeSession)", source)

    def test_existing_identity_and_confirmation_architecture_remains(self):
        source = APP.read_text(encoding="utf-8")

        self.assertIn("pendingTaskCompletionTargetsRef", source)
        self.assertIn("confirmedTaskTargets", source)
        self.assertIn("recordVerifiedFocusTaskProgress(", source)
        self.assertIn("focusTaskProgressResult?.verified", source)


if __name__ == "__main__":
    unittest.main()
