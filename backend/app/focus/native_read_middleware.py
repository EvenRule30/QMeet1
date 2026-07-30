from __future__ import annotations

import json
import os
import re
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.focus.planner import focus_mode
from app.focus.route_bridge import (
    focus_read_intent,
    memory_read_intent,
    visual_read_intent,
)


_MAX_BODY_BYTES = 1_000_000


def native_read_route_mode() -> str:
    """Return the configured native read-route rollout mode.

    shadow preserves the existing command interpreter.
    guarded enables only the conservative read-only allowlist while the overall
    Focus planner is active.
    off disables the middleware explicitly.
    """

    value = os.getenv(
        "QMEET_FOCUS_NATIVE_READ_MODE",
        "shadow",
    ).strip().casefold()
    if value in {"guarded", "active", "on", "enabled", "true", "1"}:
        return "guarded"
    if value in {"off", "disabled", "false", "0"}:
        return "off"
    return "shadow"


def native_read_routes_enabled() -> bool:
    return focus_mode() == "active" and native_read_route_mode() == "guarded"


def _visual_read_intent_with_recipient_alias(message: str):
    """Recognize visual reads that include the natural recipient word ``me``.

    The shared route bridge already recognizes the canonical forms, such as
    ``show my recent visual observations``. This compatibility pass converts
    only a leading read verb followed by ``me`` into that canonical form. It
    does not broaden the supported nouns, operations, or route classes.
    """

    intent = visual_read_intent(message)
    if intent is not None:
        return intent

    canonical_message = re.sub(
        r"\b(show|read|list|display|open)\s+me\s+",
        r"\1 ",
        str(message or ""),
        count=1,
        flags=re.IGNORECASE,
    )
    if canonical_message == message:
        return None
    return visual_read_intent(canonical_message)


def native_read_route_payload(message: str) -> dict[str, Any] | None:
    """Build an existing frontend command payload for safe local reads only.

    This deliberately excludes Calendar, Search, mutations, Focus lifecycle
    actions, camera capture, and every confirmation-gated operation. The
    returned payload uses the same command contract already consumed by the
    frontend, so no frontend command-handler change is required.
    """

    focus_intent = focus_read_intent(message)
    if focus_intent is not None:
        payload: dict[str, str] = {"mode": focus_intent.mode}
        if focus_intent.timeframe:
            payload["timeframe"] = focus_intent.timeframe
        return {
            "intent": "command",
            "action": focus_intent.action,
            "confidence": 0.99,
            "frontendCommand": focus_intent.frontend_command,
            "payload": payload,
            "reason": (
                "Native Focus read routing recognized a safe read of "
                "synchronized Focus memory."
            ),
        }

    memory_intent = memory_read_intent(message)
    if memory_intent is not None:
        return {
            "intent": "command",
            "action": memory_intent.action,
            "confidence": 0.99,
            "frontendCommand": memory_intent.frontend_command,
            "payload": {"surface": memory_intent.surface},
            "reason": (
                "Native Focus read routing recognized a safe read of "
                "synchronized Notes or Tasks memory."
            ),
        }

    visual_intent = _visual_read_intent_with_recipient_alias(message)
    if visual_intent is not None:
        return {
            "intent": "command",
            "action": visual_intent.action,
            "confidence": 0.99,
            "frontendCommand": visual_intent.frontend_command,
            "payload": {"mode": visual_intent.mode},
            "reason": (
                "Native Focus read routing recognized a safe read of already "
                "saved visual context."
            ),
        }

    return None


def _header_value(scope: Scope, name: bytes) -> str:
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.lower() == name:
            return raw_value.decode("latin-1", errors="ignore")
    return ""


async def _read_body(receive: Receive) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        message = await receive()
        if message["type"] != "http.request":
            continue
        chunk = message.get("body", b"")
        if chunk:
            total += len(chunk)
            if total > _MAX_BODY_BYTES:
                return b""
            chunks.append(chunk)
        if not message.get("more_body", False):
            break
    return b"".join(chunks)


def _replay_receive(body: bytes, original_receive: Receive) -> Receive:
    sent = False

    async def receive() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {
                "type": "http.request",
                "body": body,
                "more_body": False,
            }
        return await original_receive()

    return receive


def _json_payload(body: bytes, content_type: str) -> dict[str, Any]:
    if not body or "application/json" not in content_type.casefold():
        return {}
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _send_native_response(payload: dict[str, Any], send: Send) -> None:
    body = json.dumps(payload).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"x-qmeet-command-source", b"focus-native-read"),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        }
    )


class FocusNativeReadRouteMiddleware:
    """Bypass the legacy command model for proven read-only local routes.

    This middleware must sit inside FocusShadowMiddleware. The outer Focus
    middleware still creates the shared turn plan, performs guarded route
    selection, records route telemetry, and falls back normally. This layer
    changes only which downstream component supplies the command payload.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if (
            scope["type"] != "http"
            or scope.get("path", "") != "/api/command/interpret"
            or str(scope.get("method", "GET")).upper() != "POST"
            or not native_read_routes_enabled()
        ):
            await self.app(scope, receive, send)
            return

        body = await _read_body(receive)
        replay_receive = _replay_receive(body, receive)
        request_payload = _json_payload(
            body,
            _header_value(scope, b"content-type"),
        )
        user_message = str(request_payload.get("message") or "").strip()
        native_payload = native_read_route_payload(user_message)
        if native_payload is None:
            await self.app(scope, replay_receive, send)
            return

        await _send_native_response(native_payload, send)
