from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
AGENT_PATH = ROOT / "backend" / "app" / "qmeet_agent_shadow.py"
_TEST_MODULE_NAME = "_qmeet_phase21c2_notes_agent_test_module"


def load_agent_module():
    """Load qmeet_agent_shadow for pure ownership-floor tests without replacing app modules.

    These tests only need a callable active_focus_snapshot while importing the
    agent module. The temporary stub is scoped to module execution and is restored
    immediately afterward, so later backend tests continue using the real
    app.tool_continuation and app.qmeet_agent_shadow modules.
    """
    stub = types.ModuleType("app.tool_continuation")
    stub.active_focus_snapshot = lambda: None

    spec = importlib.util.spec_from_file_location(_TEST_MODULE_NAME, AGENT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)

    # Register only the private test module name. Pydantic/dataclass internals may
    # consult sys.modules while the module is executing, but we must never replace
    # the canonical app.qmeet_agent_shadow entry used by the full regression suite.
    sys.modules[_TEST_MODULE_NAME] = module
    try:
        with patch.dict(
            sys.modules,
            {"app.tool_continuation": stub},
            clear=False,
        ):
            spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(_TEST_MODULE_NAME, None)
        raise
    return module


class NotesOwnershipFloorPhase21C2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = load_agent_module()

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop(_TEST_MODULE_NAME, None)

    def request(self, text: str):
        return self.agent.AgentShadowRequest(userMessage=text)

    def conversation_decision(self):
        return self.agent.AgentShadowDecision(
            turnOwner="general_chat",
            focusRelevant=False,
            disposition="conversation",
            proposedCapability="none",
            proposedAction="conversation.respond",
            proposedArguments={},
            responsePlan="Reply conversationally.",
            confidence=0.9,
            reason="bad injected test decision",
        )

    def test_jot_down_note_repairs_bad_conversation_decision(self):
        request = self.request("jot down in my notes that the client prefers the blue version")
        repaired = self.agent.apply_notes_ownership_floor(
            request,
            None,
            self.conversation_decision(),
        )
        self.assertEqual(repaired.turnOwner, "notes")
        self.assertEqual(repaired.disposition, "tool")
        self.assertEqual(repaired.proposedAction, "save-note")
        self.assertEqual(
            repaired.proposedArguments,
            {"content": "the client prefers the blue version"},
        )

    def test_add_to_notes_repairs_bad_conversation_decision(self):
        request = self.request("add the launch checklist needs legal review to my notes")
        repaired = self.agent.apply_notes_ownership_floor(
            request,
            None,
            self.conversation_decision(),
        )
        self.assertEqual(repaired.proposedAction, "save-note")
        self.assertEqual(
            repaired.proposedArguments["content"],
            "the launch checklist needs legal review",
        )

    def test_note_read_repairs_bad_conversation_decision(self):
        request = self.request("what have I written down in my notes?")
        repaired = self.agent.apply_notes_ownership_floor(
            request,
            None,
            self.conversation_decision(),
        )
        self.assertEqual(repaired.turnOwner, "notes")
        self.assertEqual(repaired.proposedAction, "read-notes")
        self.assertEqual(repaired.proposedArguments, {})

    def test_literal_note_fallback_preserves_sentence_punctuation(self):
        content = self.agent._explicit_note_save_content(
            "jot down in my notes that the client prefers the blue version."
        )
        self.assertEqual(content, "the client prefers the blue version.")

    def test_focus_summary_phrase_is_not_literal_note_fallback(self):
        self.assertIsNone(
            self.agent._explicit_note_save_content("save this focus as a note")
        )

    def test_generic_conversation_without_notes_is_untouched(self):
        request = self.request("help me organize this paragraph")
        original = self.conversation_decision()
        repaired = self.agent.apply_notes_ownership_floor(request, None, original)
        self.assertEqual(repaired, original)

    def test_valid_model_note_content_is_preserved(self):
        request = self.request("jot down in my notes that the client prefers the blue version")
        model = self.agent.AgentShadowDecision(
            turnOwner="notes",
            focusRelevant=False,
            disposition="tool",
            proposedCapability="notes",
            proposedAction="save-note",
            proposedArguments={"content": "Client prefers the blue version"},
            responsePlan="Save the note.",
            confidence=0.95,
            reason="typed note proposal",
        )
        repaired = self.agent.apply_notes_ownership_floor(request, None, model)
        self.assertEqual(
            repaired.proposedArguments,
            {"content": "Client prefers the blue version"},
        )


if __name__ == "__main__":
    unittest.main()
