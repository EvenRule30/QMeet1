from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP = REPO_ROOT / "src" / "app" / "App.tsx"
OBSERVER = REPO_ROOT / "src" / "app" / "lib" / "agentShadowObserver.ts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_active_focus_start_replacement_requires_explicit_focus_language() -> None:
    text = _read(OBSERVER)
    assert "options.semanticKind === 'start'" in text
    assert "hasExplicitFocusStartIntent(options.userMessage)" in text
    assert "active Focus cannot be started over" in text


def test_start_with_content_is_not_treated_as_explicit_focus_start() -> None:
    text = _read(OBSERVER)
    explicit_pattern = "(?:focus(?:\\s+session)?|session)(?:\\b|:)"
    assert explicit_pattern in text
    assert "(?:start|begin|create|open)" in text
    assert "start with" not in text[text.index("function hasExplicitFocusStartIntent"):text.index("function hasExplicitFocusTitleUpdateIntent")]


def test_explicit_focus_start_remains_eligible_for_verified_executor() -> None:
    text = _read(OBSERVER)
    assert "The user used explicit Focus lifecycle/title mutation language" in text
    assert "verified canonical executor remains authoritative" in text


def test_only_title_changing_updates_use_replacement_gate() -> None:
    observer = _read(OBSERVER)
    app = _read(APP)
    assert "(options.semanticKind === 'update' && options.mutationChangesTitle)" in observer
    assert "Boolean(semanticFocusLifecycle.commandMatch.focusSession?.title)" in app


def test_goal_mode_objective_and_context_updates_remain_eligible() -> None:
    text = _read(OBSERVER)
    assert "Goal, mode, objective, and typed Focus-context updates remain eligible" in text


def test_active_focus_safety_gate_does_not_wait_for_shadow_model() -> None:
    text = _read(OBSERVER)
    guard_start = text.index("export function shouldGuardInferredActiveFocusReplacement")
    guard_end = text.index("// Compatibility export", guard_start)
    block = text[guard_start:guard_end]
    assert "Promise.race" not in block
    assert "decision.turnOwner" not in block
    assert "decision.confidence" not in block


def test_app_routes_guarded_replacement_to_conversation_before_executor() -> None:
    text = _read(APP)
    lifecycle = text.index("const semanticFocusLifecycle =")
    guard = text.index("const inferredFocusMutationGuard =", lifecycle)
    guarded = text.index("if (inferredFocusMutationGuard.guarded)", guard)
    mutation = text.index("semanticFocusLifecycle.kind === 'update'", guarded)
    assert lifecycle < guard < guarded < mutation
    block = text[guarded:mutation]
    assert "await sendNormalChat(trimmed, visibleUserText);" in block
    assert "handleSend(" not in block
    assert "apply semantic focus start" not in block
    assert "apply semantic focus update" not in block


def test_guarded_route_remains_visible_in_shadow_comparison_telemetry() -> None:
    app = _read(APP)
    assert "'Deterministic active-Focus mutation safety gate'" in app
    assert "'focus',\n        'conversation'," in app


def test_shadow_remains_observational_after_safety_gate_change() -> None:
    observer = _read(OBSERVER)
    assert "Shadow remains observational for comparison and future promotion." in observer
    assert "reportAgentShadowLegacyRoute" in observer


def test_old_shadow_wait_constants_are_removed_from_live_guard() -> None:
    text = _read(OBSERVER)
    assert "AGENT_SHADOW_FOCUS_MUTATION_GUARD_WAIT_MS" not in text
    assert "AGENT_SHADOW_FOCUS_MUTATION_GUARD_CONFIDENCE" not in text
