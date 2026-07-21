from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.work_context import (
    WorkContextError,
    observe_background_user_message,
    should_keep_focus_message_in_chat,
)

_MAX_OBSERVED_BODY_BYTES = 1_000_000
_OBSERVED_PATHS = {
    "/api/command/interpret",
    "/api/chat",
    "/api/chat/stream",
    "/api/search",
}


def _header_value(scope: Scope, header_name: bytes) -> str:
    for raw_name, raw_value in scope.get("headers", []):
        if raw_name.lower() == header_name:
            return raw_value.decode("latin-1", errors="ignore")
    return ""


def _extract_message(path: str, body: bytes, content_type: str) -> str:
    if not body or "application/json" not in content_type.casefold():
        return ""
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ""
    if not isinstance(payload, dict):
        return ""

    candidate_keys = ("query",) if path == "/api/search" else ("message", "query")
    for key in candidate_keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


class BackgroundWorkContextMiddleware:
    """Observe user text before routing and protect conversational focus requests.

    The frontend asks the command interpreter about natural messages before it sends
    them to chat. Observing at this boundary means the focus grows even when the
    eventual action is Search or another tool. The same middleware also keeps clear
    conversational requests in chat so phrases such as "help me craft the message"
    are not converted into Notes or Memory actions.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        if method not in {"POST", "PUT", "PATCH"} or path not in _OBSERVED_PATHS:
            await self.app(scope, receive, send)
            return

        buffered_messages: list[Message] = []
        body_parts: list[bytes] = []
        body_size = 0

        while True:
            message = await receive()
            buffered_messages.append(message)
            if message.get("type") == "http.request":
                chunk = message.get("body", b"")
                if isinstance(chunk, bytes):
                    body_size += len(chunk)
                    if body_size <= _MAX_OBSERVED_BODY_BYTES:
                        body_parts.append(chunk)
                if not message.get("more_body", False):
                    break
            elif message.get("type") == "http.disconnect":
                break

        replay_index = 0

        async def replay_receive() -> Message:
            nonlocal replay_index
            if replay_index < len(buffered_messages):
                replay_message = buffered_messages[replay_index]
                replay_index += 1
                return replay_message
            return await receive()

        body = b"".join(body_parts) if body_size <= _MAX_OBSERVED_BODY_BYTES else b""
        content_type = _header_value(scope, b"content-type")
        user_message = _extract_message(path, body, content_type)

        if user_message:
            try:
                observe_background_user_message(user_message, source=path)
            except WorkContextError:
                # Background observation must never make the primary request fail.
                pass

        if path == "/api/command/interpret" and user_message:
            try:
                keep_in_chat = should_keep_focus_message_in_chat(user_message)
            except WorkContextError:
                keep_in_chat = False

            if keep_in_chat:
                response = JSONResponse(
                    {
                        "intent": "chat",
                        "action": "none",
                        "confidence": 1.0,
                        "frontendCommand": "",
                        "payload": {},
                        "reason": (
                            "Active-focus conversation guard kept this natural help or "
                            "progress message in normal chat."
                        ),
                    }
                )
                await response(scope, replay_receive, send)
                return

        await self.app(scope, replay_receive, send)
