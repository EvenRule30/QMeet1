from __future__ import annotations

import unittest

from app import qmeet_agent_shadow, qmeet_capabilities


class SharedCapabilityContractPhase21C1Tests(unittest.TestCase):
    def test_agent_uses_shared_contract_objects(self) -> None:
        self.assertIs(
            qmeet_agent_shadow.GLOBAL_CAPABILITY_CONTRACT,
            qmeet_capabilities.GLOBAL_CAPABILITY_CONTRACT,
        )
        self.assertIs(
            qmeet_agent_shadow.CANONICAL_TOOL_ACTIONS_BY_OWNER,
            qmeet_capabilities.CANONICAL_TOOL_ACTIONS_BY_OWNER,
        )
        self.assertEqual(
            qmeet_agent_shadow.ACTION_VOCABULARY_VERSION,
            qmeet_capabilities.ACTION_VOCABULARY_VERSION,
        )

    def test_tasks_contract_promotes_only_create(self) -> None:
        tasks = next(
            item
            for item in qmeet_capabilities.GLOBAL_CAPABILITY_CONTRACT
            if item.get("owner") == "tasks"
        )
        self.assertEqual(tasks.get("promotedCreateAction"), "remember-task")
        self.assertEqual(
            tasks.get("createArgumentSchema", {}).get("required"),
            ["title"],
        )
        constraint = str(tasks.get("promotionConstraint", ""))
        self.assertIn("Only single-task creation", constraint)
        self.assertIn("completion/deletion/clear", constraint)

    def test_capability_digest_keeps_legacy_examples_and_adds_canonical_actions(self) -> None:
        digest = qmeet_capabilities.capability_digest()
        self.assertIn("open_calendar", digest)
        self.assertIn("run_search", digest)
        self.assertIn("Canonical executable actions by owner", digest)
        self.assertIn("remember-task", digest)
        self.assertIn("edit-last-event", digest)


if __name__ == "__main__":
    unittest.main()
