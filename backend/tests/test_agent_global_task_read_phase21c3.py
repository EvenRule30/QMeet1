from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
AGENT_PATH = ROOT / "backend" / "app" / "qmeet_agent_shadow.py"


class AgentGlobalTaskReadPhase21C3Tests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._previous_tool_continuation = sys.modules.get("app.tool_continuation")
        tool_stub = types.ModuleType("app.tool_continuation")
        tool_stub.active_focus_snapshot = lambda: {
            "focusId": "focus-test",
            "title": "Prepare executive presentation",
            "objective": "Clarify project goals for executives",
            "deliverable": "",
            "subject": "presentation",
            "requirements": [],
            "constraints": [],
            "preferences": [],
            "decisions": [],
            "knownFacts": [],
            "milestones": [],
            "completedMilestones": [],
            "nextAction": "",
            "pendingQuestion": None,
            "status": "active",
        }
        sys.modules["app.tool_continuation"] = tool_stub
        cls._module_name = "phase21c3_agent_shadow_isolated"
        spec = importlib.util.spec_from_file_location(cls._module_name, AGENT_PATH)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[cls._module_name] = module
        spec.loader.exec_module(module)
        cls.agent = module

    @classmethod
    def tearDownClass(cls) -> None:
        sys.modules.pop(cls._module_name, None)
        if cls._previous_tool_continuation is None:
            sys.modules.pop("app.tool_continuation", None)
        else:
            sys.modules["app.tool_continuation"] = cls._previous_tool_continuation

    def _request(self, text: str):
        return self.agent.AgentShadowRequest(
            userMessage=text,
            recentConversation=[],
            uiState={},
            clientContext={},
        )

    async def test_global_task_read_is_tasks_owned_even_with_active_focus(self) -> None:
        request = self._request("what tasks do I have?")
        with patch.object(self.agent, "_generate_model_decision", new=AsyncMock(return_value=None)):
            result = await self.agent.decide_agent_shadow(request)
        decision = result.decision
        self.assertEqual(decision.turnOwner, "tasks")
        self.assertFalse(decision.focusRelevant)
        self.assertEqual(decision.disposition, "tool")
        self.assertEqual(decision.proposedCapability, "tasks")
        self.assertEqual(decision.proposedAction, "read-memory")
        self.assertEqual(decision.proposedArguments, {"scope": "global"})

    async def test_bad_conversation_decision_is_repaired_to_global_task_read(self) -> None:
        request = self._request("show my to-do list")
        bad = self.agent.AgentShadowDecision(
            turnOwner="general_chat",
            focusRelevant=False,
            disposition="conversation",
            proposedCapability="none",
            proposedAction="conversation.respond",
            proposedArguments={},
            responsePlan="Answer conversationally.",
            confidence=0.97,
            reason="bad injected decision",
        )
        with patch.object(self.agent, "_generate_model_decision", new=AsyncMock(return_value=bad)):
            result = await self.agent.decide_agent_shadow(request)
        self.assertEqual(result.decision.turnOwner, "tasks")
        self.assertEqual(result.decision.proposedArguments, {"scope": "global"})
        self.assertFalse(result.decision.focusRelevant)

    async def test_focus_linked_task_read_is_not_repaired_to_global_scope(self) -> None:
        request = self._request("what tasks are part of this focus?")
        fallback = self.agent._fallback_shadow_decision(
            request,
            self.agent.active_focus_snapshot(),
        )
        self.assertFalse(
            fallback.turnOwner == "tasks"
            and fallback.proposedAction == "read-memory"
            and fallback.proposedArguments == {"scope": "global"}
        )


if __name__ == "__main__":
    unittest.main()
