from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent

OBSERVER = ROOT / "src" / "app" / "lib" / "agentShadowObserver.ts"
AGENT = ROOT / "backend" / "app" / "qmeet_agent_shadow.py"

HISTORICAL_TESTS = (
    ROOT / "backend" / "tests" / "test_agent_first_single_intent_ownership_phase21b.py",
    ROOT / "backend" / "tests" / "test_agent_calendar_edit_tool_promotion_phase21b_wait_fix.py",
    ROOT / "backend" / "tests" / "test_agent_calendar_edit_tool_promotion_phase21b_nullable_normalization.py",
)

OUTPUTS = {
    OBSERVER: ROOT / "src" / "app" / "lib" / "agentShadowObserver_phase21e5.ts",
    AGENT: ROOT / "backend" / "app" / "qmeet_agent_shadow_phase21e5.py",
    HISTORICAL_TESTS[0]: ROOT / "backend" / "tests" / "test_agent_first_single_intent_ownership_phase21b_phase21e5.py",
    HISTORICAL_TESTS[1]: ROOT / "backend" / "tests" / "test_agent_calendar_edit_tool_promotion_phase21b_wait_fix_phase21e5.py",
    HISTORICAL_TESTS[2]: ROOT / "backend" / "tests" / "test_agent_calendar_edit_tool_promotion_phase21b_nullable_normalization_phase21e5.py",
}

NEW_REGRESSION = (
    ROOT / "backend" / "tests" / "test_agent_first_reliability_phase21e5.py"
)


def require_file(path: Path) -> str:
    if not path.exists():
        raise SystemExit(f"Required current-main file is missing: {path}")
    return path.read_text(encoding="utf-8")


def require_count(text: str, needle: str, expected: int, label: str) -> None:
    actual = text.count(needle)
    if actual != expected:
        raise SystemExit(
            f"{label}: expected {expected} occurrence(s) of {needle!r}, found {actual}. "
            "Refusing to generate a replacement against an unexpected source shape."
        )


def update_observer(source: str) -> str:
    require_count(
        source,
        "const AGENT_FIRST_SINGLE_INTENT_WAIT_MS = 2500;",
        1,
        "agentShadowObserver timeout",
    )
    source = source.replace(
        "const AGENT_FIRST_SINGLE_INTENT_WAIT_MS = 2500;",
        "const AGENT_FIRST_SINGLE_INTENT_WAIT_MS = 7000;",
        1,
    )

    timeout_anchor = """function waitForTimeout(milliseconds: number): Promise<null> {
  return new Promise((resolve) => {
    globalThis.setTimeout(() => resolve(null), milliseconds);
  });
}
"""
    require_count(source, timeout_anchor, 1, "agentShadowObserver timeout helper")
    timeout_replacement = timeout_anchor + """
const AGENT_FIRST_SINGLE_INTENT_TIMEOUT = Symbol(
  'agent-first-single-intent-timeout',
);

function waitForSingleIntentTimeout(
  milliseconds: number,
): Promise<typeof AGENT_FIRST_SINGLE_INTENT_TIMEOUT> {
  return new Promise((resolve) => {
    globalThis.setTimeout(
      () => resolve(AGENT_FIRST_SINGLE_INTENT_TIMEOUT),
      milliseconds,
    );
  });
}
"""
    source = source.replace(timeout_anchor, timeout_replacement, 1)

    race_anchor = """    const shadow = await Promise.race([
      options.shadowTurn,
      waitForTimeout(timeoutMs),
    ]);
    if (!shadow?.decision) return null;
"""
    require_count(source, race_anchor, 1, "single-intent timeout race")
    race_replacement = """    const shadowOrTimeout = await Promise.race([
      options.shadowTurn,
      waitForSingleIntentTimeout(timeoutMs),
    ]);
    if (shadowOrTimeout === AGENT_FIRST_SINGLE_INTENT_TIMEOUT) {
      console.warn('[QMeet agent-first timeout]', {
        timeoutMs,
        outcome: 'timed-out-before-promoted-decision',
      });
      return null;
    }

    const shadow = shadowOrTimeout;
    if (!shadow?.decision) return null;
"""
    source = source.replace(race_anchor, race_replacement, 1)

    observation_start_anchor = """  const userMessage = options.userMessage.trim();
  if (!userMessage) return null;
  const requestBody = {
"""
    require_count(source, observation_start_anchor, 1, "agent observation start")
    source = source.replace(
        observation_start_anchor,
        """  const userMessage = options.userMessage.trim();
  if (!userMessage) return null;

  const startedAt = Date.now();
  const requestBody = {
""",
        1,
    )

    debug_anchor = """      proposedAction: payload.decision?.proposedAction,
      confidence: payload.decision?.confidence,
    });
"""
    require_count(source, debug_anchor, 1, "agent observation debug log")
    source = source.replace(
        debug_anchor,
        """      proposedAction: payload.decision?.proposedAction,
      confidence: payload.decision?.confidence,
      latencyMs: Date.now() - startedAt,
    });
""",
        1,
    )

    return source


def update_agent(source: str) -> str:
    schema_anchor = 'AGENT_SHADOW_SCHEMA_VERSION = "phase21b-v1"\n'
    require_count(source, schema_anchor, 1, "agent schema anchor")

    cache_block = r"""
_AGENT_OPENAI_CLIENT: Any | None = None
_AGENT_OPENAI_CLIENT_API_KEY: str | None = None
_AGENT_OPENAI_CLIENT_FACTORY: Any | None = None


def _get_agent_openai_client() -> Any | None:
    # Reuse the client while API key and factory identity remain stable.
    # Tracking the factory keeps monkeypatched tests isolated.
    global _AGENT_OPENAI_CLIENT
    global _AGENT_OPENAI_CLIENT_API_KEY
    global _AGENT_OPENAI_CLIENT_FACTORY

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or AsyncOpenAI is None:
        return None

    if (
        _AGENT_OPENAI_CLIENT is None
        or _AGENT_OPENAI_CLIENT_API_KEY != api_key
        or _AGENT_OPENAI_CLIENT_FACTORY is not AsyncOpenAI
    ):
        _AGENT_OPENAI_CLIENT = AsyncOpenAI(api_key=api_key)
        _AGENT_OPENAI_CLIENT_API_KEY = api_key
        _AGENT_OPENAI_CLIENT_FACTORY = AsyncOpenAI

    return _AGENT_OPENAI_CLIENT

"""
    source = source.replace(schema_anchor, schema_anchor + cache_block, 1)

    construction_anchor = """    try:
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = await client.chat.completions.create(
"""
    require_count(source, construction_anchor, 1, "per-decision OpenAI construction")
    source = source.replace(
        construction_anchor,
        """    try:
        client = _get_agent_openai_client()
        if client is None:
            return None
        response = await client.chat.completions.create(
""",
        1,
    )
    return source


def update_historical_test(path: Path, source: str) -> str:
    if path.name == "test_agent_first_single_intent_ownership_phase21b.py":
        require_count(
            source,
            'AGENT_FIRST_SINGLE_INTENT_WAIT_MS = 2500',
            1,
            path.name,
        )
        return source.replace(
            'AGENT_FIRST_SINGLE_INTENT_WAIT_MS = 2500',
            'AGENT_FIRST_SINGLE_INTENT_WAIT_MS = 7000',
            1,
        )

    require_count(
        source,
        'const AGENT_FIRST_SINGLE_INTENT_WAIT_MS = 2500;',
        1,
        path.name,
    )
    source = source.replace(
        'const AGENT_FIRST_SINGLE_INTENT_WAIT_MS = 2500;',
        'const AGENT_FIRST_SINGLE_INTENT_WAIT_MS = 7000;',
        1,
    )

    old_name = (
        "def test_explicit_calendar_write_waits_for_agent_beyond_default_budget"
        "(self) -> None:"
    )
    new_name = (
        "def test_explicit_calendar_write_wait_matches_standard_agent_budget"
        "(self) -> None:"
    )
    if old_name in source:
        source = source.replace(old_name, new_name, 1)

    return source


def regression_source() -> str:
    return r"""from __future__ import annotations

from pathlib import Path
import os
import re
import unittest
from unittest.mock import patch

from app import qmeet_agent_shadow as shadow


ROOT = Path(__file__).resolve().parents[2]
OBSERVER = (
    ROOT / "src" / "app" / "lib" / "agentShadowObserver.ts"
).read_text(encoding="utf-8")
AGENT = (
    ROOT / "backend" / "app" / "qmeet_agent_shadow.py"
).read_text(encoding="utf-8")
APP = (ROOT / "src" / "app" / "App.tsx").read_text(encoding="utf-8")


class AgentFirstReliabilityPhase21E5Tests(unittest.TestCase):
    def test_standard_promoted_wait_includes_a_three_second_decision(self) -> None:
        match = re.search(
            r"AGENT_FIRST_SINGLE_INTENT_WAIT_MS\s*=\s*(\d+)",
            OBSERVER,
        )
        self.assertIsNotNone(match)
        assert match is not None
        wait_ms = int(match.group(1))

        self.assertGreater(wait_ms, 3000)
        self.assertEqual(wait_ms, 7000)

    def test_single_intent_timeout_is_distinct_from_missing_agent_result(self) -> None:
        start = OBSERVER.index(
            "export async function resolvePromotedSingleIntentDecision"
        )
        end = OBSERVER.index(
            "export type AgentShadowFocusMutationGuardResult",
            start,
        )
        block = OBSERVER[start:end]

        self.assertIn("Promise.race", block)
        self.assertIn("waitForSingleIntentTimeout(timeoutMs)", block)
        self.assertIn("AGENT_FIRST_SINGLE_INTENT_TIMEOUT", block)
        self.assertIn("[QMeet agent-first timeout]", block)
        self.assertIn("timed-out-before-promoted-decision", block)
        self.assertNotIn("waitForTimeout(timeoutMs)", block)

    def test_agent_observation_logs_end_to_end_latency(self) -> None:
        start = OBSERVER.index("export async function observeAgentShadowTurn")
        end = OBSERVER.index(
            "export async function reportAgentShadowLegacyRoute",
            start,
        )
        block = OBSERVER[start:end]

        self.assertIn("const startedAt = Date.now();", block)
        self.assertIn("latencyMs: Date.now() - startedAt", block)

    def test_agent_client_is_reused_instead_of_constructed_per_decision(self) -> None:
        self.assertIn("def _get_agent_openai_client()", AGENT)
        self.assertIn("_AGENT_OPENAI_CLIENT_FACTORY is not AsyncOpenAI", AGENT)

        start = AGENT.index("async def _generate_model_decision(")
        end = AGENT.index("def _infer_legacy_owner(", start)
        block = AGENT[start:end]

        self.assertIn("client = _get_agent_openai_client()", block)
        self.assertNotIn(
            'client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))',
            block,
        )

    def test_agent_client_cache_reuses_stable_configuration_and_rotates_on_key_change(self) -> None:
        original_client = shadow._AGENT_OPENAI_CLIENT
        original_key = shadow._AGENT_OPENAI_CLIENT_API_KEY
        original_factory = shadow._AGENT_OPENAI_CLIENT_FACTORY
        try:
            shadow._AGENT_OPENAI_CLIENT = None
            shadow._AGENT_OPENAI_CLIENT_API_KEY = None
            shadow._AGENT_OPENAI_CLIENT_FACTORY = None

            with patch.object(shadow, "AsyncOpenAI") as factory:
                with patch.dict(os.environ, {"OPENAI_API_KEY": "phase21e5-key-a"}):
                    first = shadow._get_agent_openai_client()
                    second = shadow._get_agent_openai_client()

                self.assertIs(first, second)
                factory.assert_called_once_with(api_key="phase21e5-key-a")

                with patch.dict(os.environ, {"OPENAI_API_KEY": "phase21e5-key-b"}):
                    third = shadow._get_agent_openai_client()

                self.assertIsNot(third, first)
                self.assertEqual(factory.call_count, 2)
                factory.assert_called_with(api_key="phase21e5-key-b")
        finally:
            shadow._AGENT_OPENAI_CLIENT = original_client
            shadow._AGENT_OPENAI_CLIENT_API_KEY = original_key
            shadow._AGENT_OPENAI_CLIENT_FACTORY = original_factory

    def test_phase21e4_direct_device_ui_promotion_remains_before_fallback(self) -> None:
        promoted = APP.index("const promotedDeviceUiCandidate =")
        fallback = APP.index("const promotedNonFocusToolOwner =", promoted)
        block = APP[promoted:fallback]

        self.assertIn(
            "resolvePromotedDeviceUiToolCommand(promotedSingleIntent)",
            block,
        )
        self.assertIn("return handleSend(", block)
        self.assertIn("promotedDeviceUiTool.commandMatch", block)
        self.assertNotIn("/api/command/interpret", block)

    def test_calendar_write_explicit_budget_remains_compatible(self) -> None:
        self.assertIn(
            "const AGENT_FIRST_EXPLICIT_CALENDAR_WRITE_WAIT_MS = 7000;",
            APP,
        )


if __name__ == "__main__":
    unittest.main()
"""


def main() -> None:
    originals = {
        path: require_file(path)
        for path in (OBSERVER, AGENT, *HISTORICAL_TESTS)
    }

    generated: dict[Path, str] = {}
    generated[OUTPUTS[OBSERVER]] = update_observer(originals[OBSERVER])
    generated[OUTPUTS[AGENT]] = update_agent(originals[AGENT])

    for test_path in HISTORICAL_TESTS:
        generated[OUTPUTS[test_path]] = update_historical_test(
            test_path,
            originals[test_path],
        )

    generated[NEW_REGRESSION] = regression_source()

    for path, content in generated.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")

    print("Phase 21E5 comparison files generated:")
    for path in generated:
        print(f"  {path.relative_to(ROOT)}")

    print()
    print("Replace the originals with these generated comparison files:")
    for original, generated_path in OUTPUTS.items():
        print(
            f"  {original.relative_to(ROOT)}"
            f" <- {generated_path.relative_to(ROOT)}"
        )
    print(
        "Keep backend/tests/test_agent_first_reliability_phase21e5.py "
        "as a new regression."
    )


if __name__ == "__main__":
    main()
