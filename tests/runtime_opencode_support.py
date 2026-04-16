from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false
import json
import socketserver
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def build_guarded_gateway_client(settings: Any, token_provider: Any) -> Any:
    @dataclass(slots=True)
    class GuardedGatewayClient:
        settings: Any
        token_provider: Any
        calls: list[Any] = field(default_factory=list)

        def generate(self, request: Any) -> Any:
            self.calls.append(request)
            raise AssertionError(
                "runtime adapter must not call gateway_client.generate"
            )

    return GuardedGatewayClient(settings=settings, token_provider=token_provider)


@dataclass(slots=True)
class FakeRunningProcess:
    server: socketserver.TCPServer
    thread: threading.Thread
    returncode: int | None = None
    stdout_text: str = ""
    stderr_text: str = ""

    @property
    def stdout(self) -> Any:
        return _StringStream(self.stdout_text)

    @property
    def stderr(self) -> Any:
        return _StringStream(self.stderr_text)

    def poll(self) -> int | None:
        return self.returncode

    def terminate(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.returncode = 0

    def wait(self, timeout: float | None = None) -> int:
        self.thread.join(timeout)
        return 0 if self.returncode is None else self.returncode

    def kill(self) -> None:
        self.terminate()


@dataclass(frozen=True, slots=True)
class RecordedCommand:
    args: tuple[str, ...]
    cwd: Path
    env: dict[str, str]


class _StringStream:
    def __init__(self, content: str) -> None:
        self._content = content

    def read(self) -> str:
        return self._content


class _NoopHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        return


@dataclass(slots=True)
class FakeCommandRunner:
    assistant_text: str | None = None
    finish_reason: str = "stop"
    export_stdout: str | None = None
    session_list_before: tuple[str, ...] = ()
    session_list_after: tuple[str, ...] = ("ses_runtime_test",)
    run_stdout: str | None = None
    start_error: Exception | None = None
    run_error: Exception | None = None
    export_error: Exception | None = None
    serve_calls: list[RecordedCommand] = field(default_factory=list)
    run_calls: list[RecordedCommand] = field(default_factory=list)
    export_calls: list[RecordedCommand] = field(default_factory=list)
    managed_config: dict[str, object] | None = None
    _last_prompt: str = ""

    def start(self, args: tuple[str, ...], *, cwd: Path, env: dict[str, str]) -> Any:
        if self.start_error is not None:
            raise self.start_error
        port = int(args[args.index("--port") + 1])
        server = socketserver.TCPServer(("127.0.0.1", port), _NoopHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.serve_calls.append(RecordedCommand(args=args, cwd=cwd, env=env))
        self.managed_config = json.loads(env["OPENCODE_CONFIG_CONTENT"])
        return FakeRunningProcess(server=server, thread=thread)

    def run(
        self,
        args: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: float,
    ) -> Any:
        from agentsty_runtime_opencode.process import CompletedCommand

        _ = timeout_seconds
        if args[:3] == ("opencode", "session", "list"):
            session_ids = (
                self.session_list_before
                if not self.run_calls
                else self.session_list_after
            )
            return CompletedCommand(
                args=args,
                returncode=0,
                stdout=self._session_list_stdout(session_ids),
                stderr="",
            )
        if args[1] == "run":
            if self.run_error is not None:
                raise self.run_error
            self.run_calls.append(RecordedCommand(args=args, cwd=cwd, env=env))
            self._last_prompt = args[-1]
            return CompletedCommand(
                args=args,
                returncode=0,
                stdout=(self.run_stdout or self._default_run_stdout()),
                stderr="",
            )
        if self.export_error is not None:
            raise self.export_error
        self.export_calls.append(RecordedCommand(args=args, cwd=cwd, env=env))
        return CompletedCommand(
            args=args,
            returncode=0,
            stdout=(self.export_stdout or self._default_export_stdout()),
            stderr="",
        )

    def _resolved_assistant_text(self) -> str:
        if self.assistant_text is not None:
            return self.assistant_text
        prompt = self._last_prompt.rsplit("user:", maxsplit=1)[-1].strip()
        return f"local gateway echo: {prompt}"

    def _default_export_stdout(self) -> str:
        return json.dumps(
            {
                "info": {"id": "ses_runtime_test"},
                "messages": [
                    {
                        "info": {
                            "role": "assistant",
                            "finish": self.finish_reason,
                        },
                        "parts": [
                            {
                                "type": "text",
                                "text": self._resolved_assistant_text(),
                            }
                        ],
                    }
                ],
            }
        )

    def _default_run_stdout(self) -> str:
        return (
            json.dumps(
                {
                    "type": "step_start",
                    "sessionID": "ses_runtime_test",
                    "part": {"type": "step-start"},
                }
            )
            + "\n"
            + json.dumps(
                {
                    "type": "step_finish",
                    "sessionID": "ses_runtime_test",
                    "part": {"type": "step-finish", "reason": self.finish_reason},
                }
            )
            + "\n"
        )

    def _session_list_stdout(self, session_ids: tuple[str, ...]) -> str:
        if not session_ids:
            return "Session ID  Title  Updated\n"
        body = "\n".join(
            f"{session_id}  New session  8:00 AM" for session_id in session_ids
        )
        return f"Session ID  Title  Updated\n────\n{body}\n"
