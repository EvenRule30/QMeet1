from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.agent import sse_event
from app.focus.models import ObserveTurnRequest, ToolName
from app.focus.planner import focus_mode, observe_turn
from app.focus.store import (
    guarded_response_decision_for_turn,
    guarded_tool_response_decision_for_turn,
    record_assistant_reply,
    record_tool_response_candidate,
    record_tool_result,
)
from app.work_context import (
    WorkContextError,
    prepare_background_chat_message,
    record_background_assistant_reply,
)

LOGGER = logging.getLogger("qmeet.focus.middleware")

_MAX_BODY_BYTES = 1_000_000
_OBSERVATION_TASKS: dict[str, asyncio.Task[None]] = {}


def focus_response_mode() -> str:
    value = os.getenv(
        "QMEET_FOCUS_RESPONSE_MODE",
        "shadow",
    ).strip().casefold()
    return "guarded" if value in {"guarded", "active"} else "shadow"


def _guarded_wait_timeout_seconds() -> float:
    raw_value = os.getenv(
        "QMEET_FOCUS_RESPONSE_TIMEOUT_SECONDS",
        "15",
    ).strip()
    try:
        value = float(raw_value)
    except ValueError:
        value = 15.0
    return max(1.0, min(value, 60.0))


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
    """Replay the consumed request body, then restore real disconnect handling.

    StreamingResponse listens for ``http.disconnect`` while it streams. Returning
    synthetic empty request messages forever prevents that listener from waiting
    on the real ASGI connection and can leave the client stuck in its working
    state.
    """

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


def _turn_id(scope: Scope) -> str:
    supplied = _header_value(scope, b"x-qmeet-turn-id").strip()
    return supplied[:120] if supplied else f"focus-turn-{uuid4().hex}"


async def _observe_safely(message: str, source: str, turn_id: str) -> None:
    try:
        await observe_turn(
            ObserveTurnRequest(
                message=message,
                source=source,
                apply=True,
            ),
            turn_id=turn_id,
        )
    except Exception:
        LOGGER.exception(
            "Focus shadow observation failed for turn %s",
            turn_id,
        )


def _start_observation(
    message: str,
    *,
    source: str,
    turn_id: str,
) -> asyncio.Task[None]:
    existing = _OBSERVATION_TASKS.get(turn_id)
    if existing is not None and not existing.done():
        return existing

    task = asyncio.create_task(
        _observe_safely(
            message,
            source=source,
            turn_id=turn_id,
        ),
        name=f"qmeet-focus-observe-{turn_id}",
    )
    _OBSERVATION_TASKS[turn_id] = task

    def remove_completed_task(completed: asyncio.Task[None]) -> None:
        if _OBSERVATION_TASKS.get(turn_id) is completed:
            _OBSERVATION_TASKS.pop(turn_id, None)

    task.add_done_callback(remove_completed_task)
    return task


async def _wait_for_observation(turn_id: str) -> None:
    task = _OBSERVATION_TASKS.get(turn_id)
    if task is None:
        return

    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        raise
    except Exception:
        LOGGER.exception(
            "Focus observation ordering wait failed for turn %s",
            turn_id,
        )


async def _wait_for_guarded_observation(turn_id: str) -> bool:
    """Wait briefly for a candidate, then preserve the legacy fallback."""

    task = _OBSERVATION_TASKS.get(turn_id)
    if task is None:
        return True

    try:
        await asyncio.wait_for(
            asyncio.shield(task),
            timeout=_guarded_wait_timeout_seconds(),
        )
        return True
    except asyncio.TimeoutError:
        LOGGER.warning(
            "Focus guarded response timed out for turn %s; "
            "falling back to legacy chat.",
            turn_id,
        )
        return False
    except asyncio.CancelledError:
        raise
    except Exception:
        LOGGER.exception(
            "Focus guarded response wait failed for turn %s",
            turn_id,
        )
        return False


def _extract_json_reply(payload: dict[str, Any]) -> str:
    for key in ("reply", "response", "message", "text", "content"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    nested = payload.get("data")
    if isinstance(nested, dict):
        return _extract_json_reply(nested)

    return ""


def _extract_sse_reply(body: bytes) -> str:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        return ""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks: list[str] = []

    for raw_event in normalized.split("\n\n"):
        event_name = "message"
        data_lines: list[str] = []

        for raw_line in raw_event.split("\n"):
            line = raw_line.rstrip()
            if not line or line.startswith(":"):
                continue

            field, separator, value = line.partition(":")
            if separator and value.startswith(" "):
                value = value[1:]

            if field == "event":
                event_name = value.strip() or "message"
            elif field == "data":
                data_lines.append(value)

        if event_name != "chunk" or not data_lines:
            continue

        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue

        if not isinstance(payload, dict):
            continue

        chunk = payload.get("text")
        if isinstance(chunk, str):
            chunks.append(chunk)

    return "".join(chunks).strip()


async def _record_assistant_reply_safely(
    *,
    turn_id: str,
    text: str,
    transport: str,
    response_status: int,
    source: str = "chat-visible-response",
    fallback_reason: str = "",
    fallback_details: tuple[str, ...] = (),
) -> None:
    if not text.strip():
        return

    try:
        await _wait_for_observation(turn_id)
        record_assistant_reply(
            text=text,
            source_turn_id=turn_id,
            source=source,
            transport=transport,
            response_status=response_status,
            fallback_reason=fallback_reason,
            fallback_details=fallback_details,
        )
    except Exception:
        LOGGER.exception(
            "Focus could not record assistant reply for turn %s",
            turn_id,
        )


def _prepare_guarded_work_context(
    user_message: str,
    candidate_text: str,
) -> bool:
    try:
        prepare_background_chat_message(user_message)
        record_background_assistant_reply(candidate_text)
        return True
    except WorkContextError:
        LOGGER.exception(
            "Focus guarded response could not update work context."
        )
        return False
    except Exception:
        LOGGER.exception(
            "Focus guarded response hit an unexpected work-context error."
        )
        return False


async def _send_guarded_chat_response(
    *,
    path: str,
    text: str,
    send: Send,
) -> None:
    if path == "/api/chat/stream":
        headers = [
            (b"content-type", b"text/event-stream; charset=utf-8"),
            (b"cache-control", b"no-cache"),
            (b"connection", b"keep-alive"),
            (b"x-accel-buffering", b"no"),
            (b"x-qmeet-response-source", b"focus-guarded"),
        ]
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": headers,
            }
        )

        events = [
            sse_event("start", {"ok": True}),
            sse_event("chunk", {"text": text}),
            sse_event("done", {"ok": True}),
        ]
        for index, event_text in enumerate(events):
            await send(
                {
                    "type": "http.response.body",
                    "body": event_text.encode("utf-8"),
                    "more_body": index < len(events) - 1,
                }
            )
        return

    body = json.dumps(
        {
            "reply": text,
            "state": "speaking",
        }
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"x-qmeet-response-source", b"focus-guarded"),
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


def _search_result_details(
    payload: dict[str, Any],
    query: str,
) -> tuple[
    bool,
    str,
    str,
    list[str],
    list[dict[str, str]],
    list[str],
]:
    success = bool(payload.get("ok", True))
    summary = str(
        payload.get("summary")
        or payload.get("message")
        or ""
    ).strip()
    recommendation = str(payload.get("recommendation") or "").strip()

    if not summary:
        summary = (
            f"Search completed for: {query}."
            if success
            else f"Search failed for: {query}."
        )

    steps: list[str] = []
    raw_steps = payload.get("steps")
    if isinstance(raw_steps, list):
        for raw_step in raw_steps:
            step = " ".join(str(raw_step).split()).strip()
            if step and step not in steps:
                steps.append(step[:500])
            if len(steps) >= 10:
                break

    sources: list[dict[str, str]] = []
    result_ids: list[str] = []
    raw_sources = payload.get("sources")
    if isinstance(raw_sources, list):
        for raw_source in raw_sources:
            if not isinstance(raw_source, dict):
                continue

            url = str(raw_source.get("url") or "").strip()[:1000]
            title = " ".join(
                str(raw_source.get("title") or "").split()
            ).strip()[:240]
            domain = " ".join(
                str(raw_source.get("domain") or "").split()
            ).strip()[:160]
            if not url:
                continue

            if url not in result_ids:
                result_ids.append(url)
            sources.append(
                {
                    "title": title,
                    "url": url,
                    "domain": domain,
                }
            )
            if len(sources) >= 30:
                break

    return (
        success,
        summary[:2200],
        recommendation[:800],
        steps,
        sources,
        result_ids,
    )


def _focus_tool_response_payload(
    candidate_event,
    *,
    turn_id: str,
) -> dict[str, Any]:
    payload = candidate_event.payload
    citations = payload.get("citations", [])
    return {
        "text": str(payload.get("text", "")).strip(),
        "tool": str(
            payload.get("toolEvidence", {}).get("tool", "")
        ),
        "citations": citations if isinstance(citations, list) else [],
        "sourceTurnId": turn_id,
        "responseSource": "focus-tool-guarded",
    }


async def _send_buffered_json_response(
    *,
    status: int,
    headers: list[tuple[bytes, bytes]],
    payload: dict[str, Any],
    send: Send,
    response_source: str = "",
) -> None:
    body = json.dumps(payload).encode("utf-8")
    filtered_headers = [
        (name, value)
        for name, value in headers
        if name.lower() not in {b"content-length", b"content-type"}
    ]
    filtered_headers.extend(
        [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(body)).encode("ascii")),
        ]
    )
    if response_source:
        filtered_headers.append(
            (
                b"x-qmeet-response-source",
                response_source.encode("ascii", errors="ignore"),
            )
        )

    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": filtered_headers,
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        }
    )


async def _record_search_result_safely(
    *,
    turn_id: str,
    success: bool,
    summary: str,
    result_ids: list[str],
) -> None:
    try:
        # A Search response can complete before the separate model planner does.
        # Waiting here keeps the event log ordered as:
        # turn_planned -> tool_requested -> tool_completed.
        # This task runs after the visible Search response has already been sent.
        await _wait_for_observation(turn_id)

        record_tool_result(
            tool=ToolName.SEARCH,
            success=success,
            summary=summary,
            result_ids=result_ids,
            source_turn_id=turn_id,
            source="search-router-result",
        )
    except Exception:
        LOGGER.exception(
            "Focus could not assimilate Search result for turn %s",
            turn_id,
        )


class FocusShadowMiddleware:
    """Observe Focus turns and optionally serve guarded canonical replies.

    QMEET_FOCUS_MODE=off disables all Focus middleware behavior.
    QMEET_FOCUS_RESPONSE_MODE=shadow preserves legacy visible replies.
    QMEET_FOCUS_RESPONSE_MODE=guarded serves only durable, eligible direct
    candidates and falls back to the legacy chat path for everything else.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "http" or focus_mode() == "off":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path not in {
            "/api/command/interpret",
            "/api/search",
            "/api/chat",
            "/api/chat/stream",
        }:
            await self.app(scope, receive, send)
            return

        request_body = await _read_body(receive)
        content_type = _header_value(scope, b"content-type")
        request_payload = _json_payload(request_body, content_type)
        replay_receive = _replay_receive(request_body, receive)
        turn_id = _turn_id(scope)

        if path == "/api/command/interpret":
            user_message = str(
                request_payload.get("message") or ""
            ).strip()

            if user_message:
                # Register the task before the command response can trigger a
                # follow-up Search request carrying the same turn ID.
                _start_observation(
                    user_message,
                    source="command-interpret-shadow",
                    turn_id=turn_id,
                )

            await self.app(scope, replay_receive, send)
            return

        if path in {"/api/chat", "/api/chat/stream"}:
            user_message = str(
                request_payload.get("message") or ""
            ).strip()

            candidate_event = None
            fallback_reason = ""
            fallback_details: tuple[str, ...] = ()
            guarded_mode = focus_response_mode() == "guarded"

            if guarded_mode:
                # A command-interpret request normally created the candidate
                # first. Checking the store before starting a task avoids a
                # duplicate planner call when that observation already ended.
                decision = guarded_response_decision_for_turn(turn_id)
                candidate_event = decision.candidate
                fallback_reason = decision.fallbackReason
                fallback_details = decision.fallbackDetails

            if user_message and candidate_event is None:
                _start_observation(
                    user_message,
                    source="chat-request-shadow",
                    turn_id=turn_id,
                )

            if guarded_mode and candidate_event is None:
                observation_completed = await _wait_for_guarded_observation(
                    turn_id
                )
                if not observation_completed:
                    fallback_reason = "observation_timeout"
                    fallback_details = ()
                else:
                    decision = guarded_response_decision_for_turn(turn_id)
                    candidate_event = decision.candidate
                    fallback_reason = decision.fallbackReason
                    fallback_details = decision.fallbackDetails

            if candidate_event is not None:
                candidate_text = str(
                    candidate_event.payload.get("text", "")
                ).strip()

                if (
                    candidate_text
                    and _prepare_guarded_work_context(
                        user_message,
                        candidate_text,
                    )
                ):
                    await _record_assistant_reply_safely(
                        turn_id=turn_id,
                        text=candidate_text,
                        transport=(
                            "sse"
                            if path == "/api/chat/stream"
                            else "json"
                        ),
                        response_status=200,
                        source="focus-visible-response",
                    )
                    await _send_guarded_chat_response(
                        path=path,
                        text=candidate_text,
                        send=send,
                    )
                    return

                fallback_reason = "work_context_sync_failed"
                fallback_details = ()

            if guarded_mode and not fallback_reason:
                fallback_reason = "missing_candidate"

            response_status = 500
            response_content_type = ""
            response_chunks: list[bytes] = []
            response_size = 0

            async def capture_chat_send(message: Message) -> None:
                nonlocal response_status
                nonlocal response_content_type
                nonlocal response_size

                if message["type"] == "http.response.start":
                    response_status = int(message.get("status", 500))
                    headers = list(message.get("headers", []))
                    for raw_name, raw_value in headers:
                        if raw_name.lower() == b"content-type":
                            response_content_type = raw_value.decode(
                                "latin-1",
                                errors="ignore",
                            )

                    if guarded_mode and fallback_reason:
                        headers.append(
                            (
                                b"x-qmeet-fallback-reason",
                                fallback_reason.encode(
                                    "ascii",
                                    errors="ignore",
                                ),
                            )
                        )
                        message = {**message, "headers": headers}

                elif message["type"] == "http.response.body":
                    chunk = message.get("body", b"")
                    if (
                        chunk
                        and response_size + len(chunk) <= _MAX_BODY_BYTES
                    ):
                        response_chunks.append(chunk)
                        response_size += len(chunk)

                await send(message)

            await self.app(scope, replay_receive, capture_chat_send)

            response_body = b"".join(response_chunks)
            if path == "/api/chat/stream":
                reply_text = _extract_sse_reply(response_body)
                transport = "sse"
            else:
                reply_text = _extract_json_reply(
                    _json_payload(response_body, response_content_type)
                )
                transport = "json"

            if 200 <= response_status < 300 and reply_text:
                asyncio.create_task(
                    _record_assistant_reply_safely(
                        turn_id=turn_id,
                        text=reply_text,
                        transport=transport,
                        response_status=response_status,
                        fallback_reason=(
                            fallback_reason if guarded_mode else ""
                        ),
                        fallback_details=(
                            fallback_details if guarded_mode else ()
                        ),
                    ),
                    name=f"qmeet-focus-assistant-reply-{turn_id}",
                )
            return

        query = str(request_payload.get("query") or "").strip()

        if query:
            # Exact frontend search commands bypass /api/command/interpret.
            # Observe the Search request itself so the turn still receives a
            # structured plan and shares its ID with the eventual tool result.
            _start_observation(
                query,
                source="search-request-shadow",
                turn_id=turn_id,
            )

        response_status = 500
        response_content_type = ""
        response_headers: list[tuple[bytes, bytes]] = []
        response_chunks: list[bytes] = []
        response_size = 0

        async def capture_search_send(message: Message) -> None:
            nonlocal response_status
            nonlocal response_content_type
            nonlocal response_headers
            nonlocal response_size

            if message["type"] == "http.response.start":
                response_status = int(message.get("status", 500))
                response_headers = list(message.get("headers", []))
                for raw_name, raw_value in response_headers:
                    if raw_name.lower() == b"content-type":
                        response_content_type = raw_value.decode(
                            "latin-1",
                            errors="ignore",
                        )

            elif message["type"] == "http.response.body":
                chunk = message.get("body", b"")
                if chunk and response_size + len(chunk) <= _MAX_BODY_BYTES:
                    response_chunks.append(chunk)
                    response_size += len(chunk)

        await self.app(scope, replay_receive, capture_search_send)

        response_body = b"".join(response_chunks)
        response_payload = _json_payload(
            response_body,
            response_content_type,
        )
        (
            success,
            summary,
            recommendation,
            steps,
            sources,
            result_ids,
        ) = _search_result_details(response_payload, query)
        success = success and 200 <= response_status < 300
        guarded_mode = focus_response_mode() == "guarded"

        if guarded_mode and response_payload:
            observation_completed = await _wait_for_guarded_observation(
                turn_id
            )
            if observation_completed:
                try:
                    record_tool_result(
                        tool=ToolName.SEARCH,
                        success=success,
                        summary=summary,
                        result_ids=result_ids,
                        source_turn_id=turn_id,
                        source="search-router-result",
                    )
                    record_tool_response_candidate(
                        tool=ToolName.SEARCH,
                        success=success,
                        query=query,
                        summary=summary,
                        recommendation=recommendation,
                        steps=steps,
                        sources=sources,
                        source_turn_id=turn_id,
                    )
                    decision = guarded_tool_response_decision_for_turn(
                        turn_id,
                        tool=ToolName.SEARCH,
                    )
                    candidate_event = decision.candidate
                except Exception:
                    candidate_event = None
                    LOGGER.exception(
                        "Focus could not build guarded Search response for "
                        "turn %s",
                        turn_id,
                    )

                if candidate_event is not None:
                    focus_response = _focus_tool_response_payload(
                        candidate_event,
                        turn_id=turn_id,
                    )
                    candidate_text = str(
                        focus_response.get("text", "")
                    ).strip()
                    if candidate_text:
                        response_payload["focusResponse"] = focus_response
                        await _record_assistant_reply_safely(
                            turn_id=turn_id,
                            text=candidate_text,
                            transport="search-json",
                            response_status=response_status,
                            source="focus-tool-visible-response",
                        )
                        await _send_buffered_json_response(
                            status=response_status,
                            headers=response_headers,
                            payload=response_payload,
                            send=send,
                            response_source="focus-tool-guarded",
                        )
                        return
            else:
                LOGGER.warning(
                    "Focus guarded Search response timed out for turn %s; "
                    "preserving the original Search payload.",
                    turn_id,
                )

        await _send_buffered_json_response(
            status=response_status,
            headers=response_headers,
            payload=response_payload,
            send=send,
        )

        if not guarded_mode or not response_payload:
            # Shadow mode must not delay the visible Search response while the
            # planner finishes. The background task preserves event ordering.
            asyncio.create_task(
                _record_search_result_safely(
                    turn_id=turn_id,
                    success=success,
                    summary=summary,
                    result_ids=result_ids,
                ),
                name=f"qmeet-focus-search-result-{turn_id}",
            )
