from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")
HELPER = (ROOT / "src" / "app" / "lib" / "verifiedTaskCreate.ts").read_text(encoding="utf-8")


class VerifiedTaskCreatePhase21C4Tests(unittest.TestCase):
    def test_qmeet_task_create_uses_canonical_backend_before_success_receipt(self):
        self.assertIn(
            "import { createVerifiedGlobalTask } from './lib/verifiedTaskCreate';",
            APP,
        )
        self.assertIn("commandMatch.command === 'remember-task'", APP)

        create_call = APP.index(
            "const verifiedTaskCreate = await createVerifiedGlobalTask("
        )
        success_branch = APP.index(
            "continuationContext: verifiedTaskCreate.ok",
            create_call,
        )
        canonical_verification_claim = APP.index(
            "This task creation was verified by the canonical backend task endpoint",
            success_branch,
        )

        self.assertLess(create_call, success_branch)
        self.assertLess(success_branch, canonical_verification_claim)

    def test_verified_create_blocks_legacy_local_remember_task_execution(self):
        verified_result = APP.index("const verifiedTaskCreateCommandResult")
        memory_result = APP.index("const memoryCommandResult")
        legacy_handler = APP.index("await handleMemoryCommand(commandMatch", memory_result)
        self.assertLess(verified_result, memory_result)
        self.assertLess(memory_result, legacy_handler)
        self.assertIn(
            "const memoryCommandResult: SplitCommandResult = verifiedTaskCreateCommandResult.handled",
            APP,
        )
        self.assertIn("? verifiedTaskCreateCommandResult", APP[memory_result:legacy_handler])

    def test_helper_calls_scoped_task_create_endpoint_through_api(self):
        self.assertIn("import { createMemoryTask } from '../api';", HELPER)
        self.assertIn("await createMemoryTask({ title: cleanTitle })", HELPER)
        self.assertIn("const createdTask = tasks[0] ?? null;", HELPER)
        self.assertIn("applyVerifiedTaskProjection(tasks);", HELPER)

    def test_projection_happens_only_after_backend_response_is_validated(self):
        response = HELPER.index("const response = await createMemoryTask")
        validation = HELPER.index("if (\n      !createdTask", response)
        projection = HELPER.index("applyVerifiedTaskProjection(tasks);", validation)
        self.assertLess(response, validation)
        self.assertLess(validation, projection)

    def test_backend_failure_does_not_project_or_claim_success(self):
        request = HELPER.index("const response = await createMemoryTask")
        catch = HELPER.index("} catch (error) {", request)
        failure_tail = HELPER[catch:]
        self.assertIn("no task was added", failure_tail)
        self.assertNotIn("applyVerifiedTaskProjection(tasks);", failure_tail)

    def test_completion_does_not_turn_refresh_failure_into_false_no_match(self):
        self.assertIn("let taskCompletionAuthoritativeRefreshFailed = false;", APP)
        self.assertIn("taskCompletionAuthoritativeRefreshFailed = true;", APP)
        self.assertIn("Task completion state could not be verified", APP)
        self.assertIn("I couldn't verify the current open task list", APP)
        self.assertIn("did not match an open task after authoritative verification", APP)


if __name__ == "__main__":
    unittest.main()
