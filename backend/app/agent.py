from __future__ import annotations

import os
import json
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import openai
from openai import AsyncOpenAI


SYSTEM_PROMPT = """
You are QMeet, a concise AI assistant inside a small 1024x600 tablet orb interface.

Behavior:
- Keep answers short enough to read on a small tablet screen.
- Be direct and useful.
- Prefer 1-3 short paragraphs.
- Avoid long lists unless the user asks for detail.
- Do not mention backend, API, provider, or implementation details unless asked.
- If asked what you are, say you are QMeet, the orb assistant.
""".strip()



COMMAND_INTERPRETER_PROMPT = """
You are QMeet's command interpreter. Classify the user's text as either a local UI command or normal chat.

Return JSON only. Do not use markdown. Do not explain. Do not claim that you performed an action.

Allowed JSON shape:
{
  "intent": "command" | "chat",
  "action": "none" | "open_panel" | "close_panel" | "go_home" | "clear_chat" | "end_chat" | "save_note" | "read_notes" | "delete_last_note" | "clear_notes" | "prepare_search" | "clear_search" | "add_calendar_event" | "read_calendar" | "delete_last_calendar_event" | "clear_calendar" | "voice_output_on" | "voice_output_off" | "voice_slower" | "voice_faster" | "voice_normal" | "cancel",
  "confidence": 0.0,
  "frontendCommand": "",
  "payload": {},
  "reason": ""
}

The frontend only executes the exact frontendCommand text. Use these exact frontendCommand forms:
- open menu
- open settings
- show status
- open notes
- open calendar
- open search
- close panel
- go home
- clear chat
- end chat
- note that <note text>
- read my notes
- delete last note
- clear notes
- search for <query>
- clear search
- add event today at <time> called <title>
- add event tomorrow at <time> called <title>
- what's on my calendar
- show today's events
- show tomorrow's events
- delete last event
- clear calendar
- mute voice
- unmute voice
- speak slower
- speak faster
- normal voice
- cancel

Rules:
- Use intent "chat" for normal questions, explanations, coding help, opinions, or anything that should be answered by the AI.
- Use intent "command" only for local QMeet UI/tool control.
- Calendar misspellings like "calender" and "calander" should still map to calendar commands.
- If the user asks to clear/wipe/remove/delete their calendar/schedule/agenda/events, map to "clear calendar".
- If the user asks to stop the current response, stop listening, never mind, forget that, or cancel, map to "cancel".
- If the user asks you to stop talking right now, map to "cancel". If they ask to disable spoken responses in general, map to "mute voice".
- If a command is clear but wording is fuzzy, return confidence 0.80 or higher.
- If command intent is possible but unclear, use intent "command" with confidence between 0.50 and 0.79 and a best frontendCommand.
- If not a command, use intent "chat", action "none", confidence below 0.50, and empty frontendCommand.
""".strip()


ALLOWED_COMMAND_ACTIONS = {
    "none",
    "open_panel",
    "close_panel",
    "go_home",
    "clear_chat",
    "end_chat",
    "save_note",
    "read_notes",
    "delete_last_note",
    "clear_notes",
    "prepare_search",
    "clear_search",
    "add_calendar_event",
    "read_calendar",
    "delete_last_calendar_event",
    "clear_calendar",
    "voice_output_on",
    "voice_output_off",
    "voice_slower",
    "voice_faster",
    "voice_normal",
    "cancel",
}


def _empty_command_intent(reason: str = "") -> dict:
    return {
        "intent": "chat",
        "action": "none",
        "confidence": 0.0,
        "frontendCommand": "",
        "payload": {},
        "reason": reason,
    }


def _extract_json_object(text: str) -> dict:
    stripped = text.strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found.")

    return json.loads(stripped[start : end + 1])


def _normalize_command_intent(raw: dict) -> dict:
    intent = str(raw.get("intent", "chat")).strip().lower()
    if intent not in {"command", "chat"}:
        intent = "chat"

    action = str(raw.get("action", "none")).strip()
    if action not in ALLOWED_COMMAND_ACTIONS:
        action = "none"

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(confidence, 1.0))

    frontend_command = str(raw.get("frontendCommand", "")).strip()

    payload = raw.get("payload", {})
    if not isinstance(payload, dict):
        payload = {}

    reason = str(raw.get("reason", "")).strip()

    if intent == "chat" or action == "none":
        return {
            "intent": "chat",
            "action": "none",
            "confidence": min(confidence, 0.49),
            "frontendCommand": "",
            "payload": {},
            "reason": reason,
        }

    if not frontend_command:
        return _empty_command_intent("Interpreter returned a command without a frontendCommand.")

    return {
        "intent": "command",
        "action": action,
        "confidence": confidence,
        "frontendCommand": frontend_command,
        "payload": payload,
        "reason": reason,
    }


async def interpret_command_intent(message: str) -> dict:
    config = get_agent_config()

    if config.provider == "mock":
        return mock_interpret_command_intent(message)

    if config.provider == "openai":
        return await openai_interpret_command_intent(message, config)

    raise AgentUserFacingError(
        f'Unsupported LLM_PROVIDER="{config.provider}". Use "mock" or "openai".'
    )


def mock_interpret_command_intent(message: str) -> dict:
    text = message.strip()
    lowered = text.lower()

    if not text:
        return _empty_command_intent("Empty input.")

    if re.search(r"\b(clear|wipe|delete|remove|erase)\b.*\b(calendar|calender|calander|schedule|agenda|events?)\b", lowered):
        return {
            "intent": "command",
            "action": "clear_calendar",
            "confidence": 0.95,
            "frontendCommand": "clear calendar",
            "payload": {},
            "reason": "Mock matched calendar clear wording.",
        }

    if re.search(r"\b(open|show|pull up|bring up)\b.*\b(notes?|notepad|notebook)\b", lowered):
        return {
            "intent": "command",
            "action": "open_panel",
            "confidence": 0.9,
            "frontendCommand": "open notes",
            "payload": {"panel": "notes"},
            "reason": "Mock matched notes panel wording.",
        }

    if re.search(r"\b(mute|silence)\b.*\b(voice|speech|yourself|talking)\b", lowered):
        return {
            "intent": "command",
            "action": "voice_output_off",
            "confidence": 0.9,
            "frontendCommand": "mute voice",
            "payload": {},
            "reason": "Mock matched voice mute wording.",
        }

    return _empty_command_intent("Mock did not match a local command.")


async def openai_interpret_command_intent(message: str, config: AgentConfig) -> dict:
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise AgentUserFacingError(
            "OpenAI is selected, but OPENAI_API_KEY is missing in backend/.env."
        )

    client = AsyncOpenAI(api_key=api_key)

    try:
        response = await client.responses.create(
            model=config.model,
            input=[
                {
                    "role": "developer",
                    "content": COMMAND_INTERPRETER_PROMPT,
                },
                {
                    "role": "user",
                    "content": message,
                },
            ],
            max_output_tokens=260,
        )
    except openai.AuthenticationError as exc:
        raise AgentUserFacingError(
            "OpenAI authentication failed. Check backend/.env and verify the API key."
        ) from exc
    except openai.RateLimitError as exc:
        raise AgentUserFacingError(
            "OpenAI rate limit or quota was reached. Check API billing, limits, or try again later."
        ) from exc
    except openai.APIConnectionError as exc:
        raise AgentUserFacingError(
            "Could not connect to OpenAI. Check your internet connection."
        ) from exc
    except openai.APIError as exc:
        raise AgentUserFacingError(
            "OpenAI returned an API error. Try again shortly."
        ) from exc

    raw_text = response.output_text.strip()

    if not raw_text:
        return _empty_command_intent("Interpreter returned empty output.")

    try:
        raw_json = _extract_json_object(raw_text)
    except (json.JSONDecodeError, ValueError):
        return _empty_command_intent("Interpreter returned invalid JSON.")

    return _normalize_command_intent(raw_json)



# Simple in-memory history for the current backend process.
# This resets when the backend restarts.
MESSAGE_HISTORY: list[dict[str, str]] = []


@dataclass
class AgentConfig:
    provider: str
    model: str
    max_output_tokens: int
    has_openai_key: bool


class AgentUserFacingError(Exception):
    """Safe error message that can be shown in the UI."""


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def get_agent_config() -> AgentConfig:
    provider = os.getenv("LLM_PROVIDER", "mock").lower().strip()
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()

    try:
        max_output_tokens = int(os.getenv("OPENAI_MAX_OUTPUT_TOKENS", "300"))
    except ValueError:
        max_output_tokens = 300

    # OpenAI currently documents 16 as the minimum for max_output_tokens.
    max_output_tokens = max(16, min(max_output_tokens, 1200))

    return AgentConfig(
        provider=provider,
        model=model,
        max_output_tokens=max_output_tokens,
        has_openai_key=bool(os.getenv("OPENAI_API_KEY")),
    )


def get_public_status() -> dict:
    config = get_agent_config()

    return {
        "ok": True,
        "provider": config.provider,
        "model": config.model if config.provider == "openai" else "mock",
        "hasOpenAIKey": config.has_openai_key,
        "maxOutputTokens": config.max_output_tokens,
    }


def reset_conversation() -> None:
    global MESSAGE_HISTORY
    MESSAGE_HISTORY.clear()


async def generate_reply(message: str) -> str:
    config = get_agent_config()

    if config.provider == "mock":
        return mock_reply(message)

    if config.provider == "openai":
        return await openai_reply(message, config)

    raise AgentUserFacingError(
        f'Unsupported LLM_PROVIDER="{config.provider}". Use "mock" or "openai".'
    )


async def stream_reply(message: str) -> AsyncGenerator[str, None]:
    config = get_agent_config()

    if config.provider == "mock":
        async for chunk in mock_stream_reply(message):
            yield chunk
        return

    if config.provider == "openai":
        async for chunk in openai_stream_reply(message, config):
            yield chunk
        return

    raise AgentUserFacingError(
        f'Unsupported LLM_PROVIDER="{config.provider}". Use "mock" or "openai".'
    )


async def mock_stream_reply(message: str) -> AsyncGenerator[str, None]:
    import asyncio

    reply = mock_reply(message)

    for word in reply.split(" "):
        yield word + " "
        await asyncio.sleep(0.04)


def mock_reply(message: str) -> str:
    text = message.strip()

    if not text:
        return "I did not receive a message."

    return (
        "QMeet backend is connected. "
        f'You said: "{text}". '
    )


async def openai_reply(message: str, config: AgentConfig) -> str:
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise AgentUserFacingError(
            "OpenAI is selected, but OPENAI_API_KEY is missing in backend/.env."
        )

    client = AsyncOpenAI(api_key=api_key)

    # Keep recent context small for now.
    recent_history = MESSAGE_HISTORY[-10:]

    input_messages = [
        {
            "role": "developer",
            "content": SYSTEM_PROMPT,
        },
        *recent_history,
        {
            "role": "user",
            "content": message,
        },
    ]

    try:
        response = await client.responses.create(
            model=config.model,
            input=input_messages,
            max_output_tokens=config.max_output_tokens,
        )
    except openai.AuthenticationError as exc:
        raise AgentUserFacingError(
            "OpenAI authentication failed. Check backend/.env and verify the API key."
        ) from exc
    except openai.RateLimitError as exc:
        raise AgentUserFacingError(
            "OpenAI rate limit or quota was reached. Check API billing, limits, or try again later."
        ) from exc
    except openai.APIConnectionError as exc:
        raise AgentUserFacingError(
            "Could not connect to OpenAI. Check your internet connection."
        ) from exc
    except openai.APIError as exc:
        raise AgentUserFacingError(
            "OpenAI returned an API error. Try again shortly."
        ) from exc

    reply = response.output_text.strip()

    if not reply:
        raise AgentUserFacingError("The model returned an empty response.")


    MESSAGE_HISTORY.append({"role": "user", "content": message})
    MESSAGE_HISTORY.append({"role": "assistant", "content": reply})

    return reply


async def openai_stream_reply(
    message: str,
    config: AgentConfig,
) -> AsyncGenerator[str, None]:
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise AgentUserFacingError(
            "OpenAI is selected, but OPENAI_API_KEY is missing in backend/.env."
        )

    client = AsyncOpenAI(api_key=api_key)
    recent_history = MESSAGE_HISTORY[-10:]

    input_messages = [
        {
            "role": "developer",
            "content": SYSTEM_PROMPT,
        },
        *recent_history,
        {
            "role": "user",
            "content": message,
        },
    ]

    full_reply = ""

    try:
        stream = await client.responses.create(
            model=config.model,
            input=input_messages,
            max_output_tokens=config.max_output_tokens,
            stream=True,
        )

        async for event in stream:
            if event.type == "response.output_text.delta":
                delta = event.delta
                full_reply += delta
                yield delta

            elif event.type == "response.completed":
                break

            elif event.type == "response.failed":
                raise AgentUserFacingError("The model failed while generating a response.")

    except openai.AuthenticationError as exc:
        raise AgentUserFacingError(
            "OpenAI authentication failed. Check backend/.env and verify the API key."
        ) from exc
    except openai.RateLimitError as exc:
        raise AgentUserFacingError(
            "OpenAI rate limit or quota was reached. Check API billing, limits, or try again later."
        ) from exc
    except openai.APIConnectionError as exc:
        raise AgentUserFacingError(
            "Could not connect to OpenAI. Check your internet connection."
        ) from exc
    except openai.APIError as exc:
        raise AgentUserFacingError(
            "OpenAI returned an API error. Try again shortly."
        ) from exc

    full_reply = full_reply.strip()

    if full_reply:
        MESSAGE_HISTORY.append({"role": "user", "content": message})
        MESSAGE_HISTORY.append({"role": "assistant", "content": full_reply})