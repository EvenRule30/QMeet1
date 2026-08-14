from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "backend" / "app" / "qmeet_agent_shadow.py"
CAPABILITIES = ROOT / "backend" / "app" / "qmeet_capabilities.py"
APP = ROOT / "src" / "app" / "App.tsx"
PROMOTION = ROOT / "src" / "app" / "lib" / "agentToolPromotion.ts"


class AgentNotesPromotionPhase21C2Tests(unittest.TestCase):
    def test_shared_contract_promotes_notes_save_and_read(self):
        source = CAPABILITIES.read_text(encoding="utf-8")
        self.assertIn('"promotedSaveAction": "save-note"', source)
        self.assertIn('"promotedReadAction": "read-notes"', source)
        self.assertIn('"required": ["content"]', source)

    def test_agent_contract_has_typed_notes_rules(self):
        source = AGENT.read_text(encoding="utf-8")
        self.assertIn("Notes ownership rule:", source)
        self.assertIn('proposedAction=save-note', source)
        self.assertIn('proposedAction=read-notes', source)
        self.assertIn('proposedArguments={}', source)
        self.assertIn("apply_notes_ownership_floor", source)

    def test_frontend_promotes_notes_through_existing_commands(self):
        source = PROMOTION.read_text(encoding="utf-8")
        self.assertIn("resolvePromotedNoteSaveToolCommand", source)
        self.assertIn("resolvePromotedNoteReadToolCommand", source)
        self.assertIn("command: 'save-note'", source)
        self.assertIn("command: 'read-notes'", source)
        self.assertIn("keys.length !== 1 || keys[0] !== 'content'", source)
        self.assertIn("Object.keys(argumentsValue).length === 0", source)

    def test_app_routes_promoted_notes_before_calendar(self):
        source = APP.read_text(encoding="utf-8")
        note_save = source.index("const promotedNoteSaveCandidate")
        note_read = source.index("const promotedNoteReadCandidate")
        calendar_create = source.index("const promotedCalendarCreateCandidate")
        self.assertLess(note_save, note_read)
        self.assertLess(note_read, calendar_create)
        self.assertIn("'Agent-promoted note save'", source)
        self.assertIn("'Agent-promoted note read'", source)

    def test_existing_notes_handler_remains_authoritative(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("const notesCommandResult: SplitCommandResult = handleNotesCommand(commandMatch", source)
        self.assertIn("saveNote,", source)
        self.assertIn("getNotesReadout,", source)

    def test_phase20_confirmed_task_source_seam_remains(self):
        source = APP.read_text(encoding="utf-8")
        self.assertIn("const confirmedTaskCommandMatch: CommandMatch | undefined =", source)
        self.assertIn("confirmedTaskCommandMatch,", source)


if __name__ == "__main__":
    unittest.main()
