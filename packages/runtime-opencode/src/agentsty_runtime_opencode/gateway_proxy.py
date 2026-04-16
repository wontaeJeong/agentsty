"""Local compatibility proxy for OpenCode gateway traffic."""

from __future__ import annotations

import http.client
import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import cast
from urllib.parse import SplitResult, urlsplit


@dataclass(slots=True)
class GatewayCompatibilityProxy:
    upstream_base_url: str
    _server: ThreadingHTTPServer | None = None
    _thread: threading.Thread | None = None
    _captured_text: dict[str, list[str]] = field(default_factory=dict)
    _latest_text: list[str] = field(default_factory=list)
    _latest_sse_body: str | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> None:
        if self._server is not None:
            return

        controller = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_POST(self) -> None:  # noqa: N802
                controller._handle_post(self)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("gateway proxy has not been started")
        host, port = cast(tuple[str, int], self._server.server_address)
        return f"http://{host}:{port}"

    def close(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._server = None
        self._thread = None

    def captured_text(self, session_id: str) -> str | None:
        with self._lock:
            parts = self._captured_text.get(session_id)
            if parts:
                joined = "".join(parts).strip()
                return joined or None
            joined = "".join(self._latest_text).strip()
            if joined:
                return joined
            if self._latest_sse_body is None:
                return None
            return _extract_text_from_sse_body(self._latest_sse_body)

    def _handle_post(self, handler: BaseHTTPRequestHandler) -> None:
        split = urlsplit(self.upstream_base_url)
        upstream = self._open_connection(split)
        try:
            payload = handler.rfile.read(
                int(handler.headers.get("Content-Length", "0"))
            )
            upstream_path = self._upstream_path(split, handler.path)
            headers = {
                key: value
                for key, value in handler.headers.items()
                if key.lower() not in {"host", "content-length", "connection"}
            }
            headers["Connection"] = "close"
            upstream.request("POST", upstream_path, body=payload, headers=headers)
            response = upstream.getresponse()
            content_type = response.getheader(
                "Content-Type", "application/octet-stream"
            )

            if content_type.startswith("text/event-stream"):
                self._stream_sse(handler, response, payload)
                return

            raw_body = response.read()
            handler.send_response(response.status)
            handler.send_header("Content-Type", content_type)
            handler.send_header("Connection", "close")
            handler.send_header("Content-Length", str(len(raw_body)))
            handler.end_headers()
            handler.wfile.write(raw_body)
            handler.wfile.flush()
            handler.close_connection = True
        finally:
            upstream.close()

    def _stream_sse(
        self,
        handler: BaseHTTPRequestHandler,
        response: http.client.HTTPResponse,
        payload: bytes,
    ) -> None:
        request_body = self._decode_json(payload)
        is_title_request = _is_title_request(request_body)
        session_id = handler.headers.get("x-session-affinity")

        handler.send_response(response.status)
        handler.send_header("Content-Type", "text/event-stream")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "close")
        handler.end_headers()

        raw_body = response.read()
        normalized_body = _normalize_sse_body(raw_body)
        handler.wfile.write(normalized_body)
        handler.wfile.flush()

        if not is_title_request:
            with self._lock:
                self._latest_sse_body = normalized_body.decode(
                    "utf-8", errors="replace"
                )

        if session_id is not None and not is_title_request:
            for event in (self._latest_sse_body or "").split("\n\n"):
                stripped = event.strip()
                if not stripped.startswith("data:"):
                    continue
                data = stripped[5:].strip()
                if data == "[DONE]":
                    break
                payload_json = self._decode_json(data.encode("utf-8"))
                text = _extract_stream_text(payload_json)
                if text:
                    with self._lock:
                        self._latest_text.append(text)
                        if session_id is not None:
                            self._captured_text.setdefault(session_id, []).append(text)

        handler.close_connection = True

    def _open_connection(
        self, split: SplitResult
    ) -> http.client.HTTPConnection | http.client.HTTPSConnection:
        if split.hostname is None:
            raise RuntimeError("gateway proxy upstream URL must include a hostname")
        if split.scheme == "https":
            return http.client.HTTPSConnection(split.hostname, split.port, timeout=30)
        return http.client.HTTPConnection(split.hostname, split.port, timeout=30)

    def _upstream_path(self, split: SplitResult, request_path: str) -> str:
        prefix = split.path.rstrip("/")
        suffix = request_path if request_path.startswith("/") else f"/{request_path}"
        suffix_path = suffix.split("?", maxsplit=1)[0]
        if prefix and suffix_path.startswith(prefix):
            combined = suffix_path
        else:
            combined = f"{prefix}{suffix_path}"
        query = (
            f"?{urlsplit(request_path).query}" if urlsplit(request_path).query else ""
        )
        return f"{combined}{query}"

    def _decode_json(self, payload: bytes) -> object | None:
        try:
            return cast(object, json.loads(payload.decode("utf-8")))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None


def _is_title_request(payload: object | None) -> bool:
    if not isinstance(payload, dict):
        return False
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return False
    first = messages[0]
    if not isinstance(first, dict):
        return False
    content = first.get("content")
    return isinstance(content, str) and content.startswith("You are a title generator")


def _extract_stream_text(payload: object | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    choice = choices[0]
    if not isinstance(choice, dict):
        return None
    delta = choice.get("delta")
    if not isinstance(delta, dict):
        return None
    content = delta.get("content")
    if isinstance(content, str) and content:
        return content
    if isinstance(content, list):
        pieces = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        ]
        joined = "".join(cast(list[str], pieces)).strip()
        return joined or None
    return None


def _extract_text_from_sse_body(raw_body: str) -> str | None:
    parts: list[str] = []
    for event in raw_body.split("\n\n"):
        stripped = event.strip()
        if not stripped.startswith("data:"):
            continue
        data = stripped[5:].strip()
        if data == "[DONE]":
            break
        try:
            payload = cast(object, json.loads(data))
        except json.JSONDecodeError:
            continue
        text = _extract_stream_text(payload)
        if text:
            parts.append(text)
    joined = "".join(parts).strip()
    return joined or None


def _normalize_sse_body(raw_body: bytes) -> bytes:
    if b"\n\n" in raw_body:
        return raw_body
    if b"\\n\\n" in raw_body:
        return raw_body.replace(b"\\n", b"\n")
    return raw_body
