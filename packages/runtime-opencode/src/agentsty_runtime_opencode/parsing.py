"""Parsing helpers for OpenCode JSON event streams and exports."""

from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ParsedOpenCodeExport:
    session_id: str
    output_text: str
    finish_reason: str


def parse_export_payload(raw_export: str) -> ParsedOpenCodeExport:
    payload = json.loads(raw_export)
    if not isinstance(payload, dict):
        raise ValueError("OpenCode export payload must be a JSON object")
    session_id = _extract_session_id(payload)
    assistant_message, output_text = _latest_assistant_text(payload)
    finish_reason = _message_finish_reason(assistant_message)
    return ParsedOpenCodeExport(
        session_id=session_id,
        output_text=output_text,
        finish_reason=finish_reason,
    )


def _extract_session_id(payload: dict[str, object]) -> str:
    info = payload.get("info")
    if isinstance(info, dict):
        session_id = info.get("id")
        if isinstance(session_id, str) and session_id.strip():
            return session_id.strip()
    raise ValueError("OpenCode export did not include a session id")


def _latest_assistant_text(payload: dict[str, object]) -> tuple[dict[str, object], str]:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise ValueError("OpenCode export did not include messages")
    assistants = [
        message
        for message in messages
        if isinstance(message, dict) and _is_assistant_message(message)
    ]
    if not assistants:
        raise ValueError("OpenCode export did not include an assistant message")
    for assistant in reversed(assistants):
        output_text = _message_text(assistant)
        if output_text:
            return assistant, output_text
    raise ValueError("OpenCode export did not include assistant text")


def _is_assistant_message(message: object) -> bool:
    if not isinstance(message, dict):
        return False
    info = message.get("info")
    return isinstance(info, dict) and info.get("role") == "assistant"


def _message_text(message: dict[str, object]) -> str:
    parts = message.get("parts")
    if not isinstance(parts, list):
        return ""
    text_parts: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        part_type = part.get("type")
        text = part.get("text")
        if part_type == "text" and isinstance(text, str) and text.strip():
            text_parts.append(text.strip())
    return "\n".join(text_parts).strip()


def _message_finish_reason(message: dict[str, object]) -> str:
    info = message.get("info")
    if isinstance(info, dict):
        value = info.get("finish")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "stop"
