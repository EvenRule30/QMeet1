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

    def test_tasks_contract_exposes_current_promoted_actions(self) -> None:
        tasks = next(
            item
            for item in qmeet_capabilities.GLOBAL_CAPABILITY_CONTRACT
            if item.get("owner") == "tasks"
        )

        self.assertEqual(tasks.get("promotedCreateAction"), "remember-task")
        self.assertEqual(tasks.get("promotedReadAction"), "read-memory")
        self.assertEqual(tasks.get("promotedCompleteAction"), "mark-task-done")
        self.assertEqual(tasks.get("promotedDeleteAction"), "delete-task")

        self.assertEqual(
            tasks.get("createArgumentSchema", {}).get("required"),
            ["title"],
        )
        self.assertEqual(
            tasks.get("readArgumentSchema", {}).get("required"),
            ["scope"],
        )
        self.assertEqual(
            tasks.get("completeArgumentSchema", {}).get("required"),
            ["scope", "query"],
        )
        self.assertEqual(
            tasks.get("deleteArgumentSchema", {}).get("required"),
            ["scope", "query"],
        )

        self.assertEqual(
            tasks.get("readArgumentSchema", {})
            .get("properties", {})
            .get("scope", {})
            .get("enum"),
            ["global"],
        )
        self.assertEqual(
            tasks.get("deleteArgumentSchema", {})
            .get("properties", {})
            .get("scope", {})
            .get("enum"),
            ["global"],
        )

        constraint = str(tasks.get("promotionConstraint", ""))
        self.assertIn("Single-task creation", constraint)
        self.assertIn("one named/referenced completion", constraint)
        self.assertIn("one targeted GLOBAL task deletion", constraint)
        self.assertIn("Delete-last and clear-completed", constraint)

    def test_capability_digest_keeps_legacy_examples_and_adds_canonical_actions(self) -> None:
        digest = qmeet_capabilities.capability_digest()
        self.assertIn("open_calendar", digest)
        self.assertIn("run_search", digest)
        self.assertIn("Canonical executable actions by owner", digest)
        self.assertIn("remember-task", digest)
        self.assertIn("mark-task-done", digest)
        self.assertIn("delete-task", digest)
        self.assertIn("edit-last-event", digest)


if __name__ == "__main__":
    unittest.main()
