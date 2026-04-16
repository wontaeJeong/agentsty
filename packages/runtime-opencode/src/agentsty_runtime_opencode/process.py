"""Subprocess helpers for headless OpenCode invocation."""

from __future__ import annotations

import json
import os
import socket
import socketserver
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol, cast

from .gateway_proxy import GatewayCompatibilityProxy


class RunningProcessLike(Protocol):
    stdout: IO[str] | None
    stderr: IO[str] | None

    def poll(self) -> int | None: ...

    def terminate(self) -> None: ...

    def wait(self, timeout: float | None = None) -> int: ...

    def kill(self) -> None: ...


@dataclass(frozen=True, slots=True)
class CompletedCommand:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class OpenCodeInvocationArtifacts:
    attach_url: str
    session_id: str
    run_result: CompletedCommand
    export_result: CompletedCommand
    captured_output_text: str | None = None


class CommandRunner(Protocol):
    def start(
        self,
        args: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
    ) -> RunningProcessLike: ...

    def run(
        self,
        args: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: float,
    ) -> CompletedCommand: ...


@dataclass(slots=True)
class SubprocessCommandRunner:
    def start(
        self,
        args: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
    ) -> RunningProcessLike:
        return subprocess.Popen(
            args,
            cwd=str(cwd),
            env=_merged_env(env),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

    def run(
        self,
        args: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: float,
    ) -> CompletedCommand:
        completed = subprocess.run(
            args,
            cwd=str(cwd),
            env=_merged_env(env),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return CompletedCommand(
            args=args,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass(slots=True)
class _InlineRunningProcess:
    server: socketserver.TCPServer
    thread: threading.Thread
    stdout: IO[str] | None = None
    stderr: IO[str] | None = None
    returncode: int | None = None

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
        self.returncode = 0


@dataclass(slots=True)
class InlineCommandRunner:
    assistant_text: str | None = None
    error_category: str | None = None
    error_message: str | None = None
    _server: socketserver.TCPServer | None = None
    _thread: threading.Thread | None = None
    _last_prompt: str = ""

    @classmethod
    def from_environment(cls, env: dict[str, str]) -> InlineCommandRunner:
        return cls(
            assistant_text=env.get("AGENTSTY_RUNNER_INLINE_ASSISTANT_TEXT"),
            error_category=env.get("AGENTSTY_RUNNER_INLINE_ERROR_CATEGORY"),
            error_message=env.get("AGENTSTY_RUNNER_INLINE_ERROR_MESSAGE"),
        )

    def start(
        self,
        args: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
    ) -> RunningProcessLike:
        _ = (args, cwd, env)

        class _NoopHandler(socketserver.BaseRequestHandler):
            def handle(self) -> None:
                return

        port = int(args[args.index("--port") + 1])
        self._server = socketserver.TCPServer(("127.0.0.1", port), _NoopHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return _InlineRunningProcess(server=self._server, thread=self._thread)

    def run(
        self,
        args: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: float,
    ) -> CompletedCommand:
        _ = (cwd, env, timeout_seconds)
        if args[:3] == ("opencode", "session", "list"):
            return CompletedCommand(
                args=args,
                returncode=0,
                stdout="Session ID  Title  Updated\n────\nses_inline  Inline session  8:00 AM\n",
                stderr="",
            )
        if args[1] == "run":
            if self.error_category is not None:
                raise _inline_error(self.error_category, self.error_message)
            self._last_prompt = args[-1]
            return CompletedCommand(
                args=args,
                returncode=0,
                stdout=json.dumps(
                    {
                        "type": "step_finish",
                        "sessionID": "ses_inline",
                        "part": {"type": "step-finish", "reason": "stop"},
                    }
                )
                + "\n",
                stderr="",
            )
        assistant_text = self.assistant_text or _inline_assistant_text(
            self._last_prompt
        )
        return CompletedCommand(
            args=args,
            returncode=0,
            stdout=json.dumps(
                {
                    "info": {"id": "ses_inline"},
                    "messages": [
                        {
                            "info": {"role": "assistant", "finish": "stop"},
                            "parts": [{"type": "text", "text": assistant_text}],
                        }
                    ],
                }
            ),
            stderr="",
        )


def _inline_assistant_text(prompt: str) -> str:
    return f"local gateway echo: {prompt.rsplit('user:', maxsplit=1)[-1].strip()}"


def _inline_error(category: str, message: str | None) -> Exception:
    domain = __import__("agentsty_platform.domain", fromlist=["DomainError"])
    normalized = category.strip().lower()
    error_message = message or category
    if normalized == "gateway_failure":
        return cast(
            Exception,
            domain.GatewayError(
                error_message,
                retryable=True,
                metadata=(("failure_kind", "unavailable"),),
            ),
        )
    if normalized == "timeout":
        return cast(Exception, domain.TimeoutError(error_message))
    if normalized == "cancellation":
        return cast(Exception, domain.CancellationError(error_message))
    return cast(Exception, domain.RuntimeExecutionError(error_message))


def free_local_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def invoke_headless_opencode(
    runner: CommandRunner,
    *,
    workspace_path: Path,
    managed_env: dict[str, str],
    model: str,
    prompt: str,
    execution_timeout_seconds: int,
    startup_timeout_seconds: float = 10.0,
    port: int | None = None,
) -> OpenCodeInvocationArtifacts:
    selected_port = port if port is not None else free_local_port()
    attach_url = f"http://127.0.0.1:{selected_port}"
    workspace_path.mkdir(parents=True, exist_ok=True)
    runtime_env = dict(managed_env)
    gateway_proxy: GatewayCompatibilityProxy | None = None
    if isinstance(runner, SubprocessCommandRunner):
        upstream_base_url = managed_base_url(runtime_env)
        if upstream_base_url is not None:
            gateway_proxy = GatewayCompatibilityProxy(
                upstream_base_url=upstream_base_url
            )
            gateway_proxy.start()
            runtime_env = with_managed_base_url(runtime_env, gateway_proxy.base_url)
    serve_args = (
        "opencode",
        "serve",
        "--hostname",
        "127.0.0.1",
        "--port",
        str(selected_port),
        "--pure",
    )
    server = runner.start(serve_args, cwd=workspace_path, env=runtime_env)
    try:
        wait_for_server(
            server, port=selected_port, timeout_seconds=startup_timeout_seconds
        )
        before_session_ids = list_session_ids(
            runner,
            cwd=workspace_path,
            env=runtime_env,
            timeout_seconds=float(execution_timeout_seconds),
        )
        run_result = runner.run(
            (
                "opencode",
                "run",
                "--attach",
                attach_url,
                "--format",
                "json",
                "--dir",
                str(workspace_path),
                "--model",
                model,
                "--dangerously-skip-permissions",
                "--pure",
                prompt,
            ),
            cwd=workspace_path,
            env=runtime_env,
            timeout_seconds=float(execution_timeout_seconds),
        )
        session_id = extract_session_id(run_result.stdout)
        if session_id is None:
            after_session_ids = list_session_ids(
                runner,
                cwd=workspace_path,
                env=runtime_env,
                timeout_seconds=float(execution_timeout_seconds),
            )
            session_id = detect_new_session_id(before_session_ids, after_session_ids)
        if session_id is None:
            raise ValueError("OpenCode run output did not include a session id")
        export_result = runner.run(
            (
                "opencode",
                "export",
                session_id,
                "--pure",
            ),
            cwd=workspace_path,
            env=runtime_env,
            timeout_seconds=float(execution_timeout_seconds),
        )
        return OpenCodeInvocationArtifacts(
            attach_url=attach_url,
            session_id=session_id,
            run_result=run_result,
            export_result=export_result,
            captured_output_text=(
                gateway_proxy.captured_text(session_id) if gateway_proxy else None
            ),
        )
    finally:
        terminate_process(server)
        if gateway_proxy is not None:
            gateway_proxy.close()


def wait_for_server(
    process: RunningProcessLike,
    *,
    port: int,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"opencode serve exited before it accepted connections: {read_process_output(process)}"
            )
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                return
        finally:
            probe.close()
        time.sleep(0.05)
    raise RuntimeError(f"timed out waiting for opencode serve on port {port}")


def extract_session_id(stdout: str) -> str | None:
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if '"sessionID"' not in stripped and '"sessionId"' not in stripped:
            continue
        import json

        payload = json.loads(stripped)
        for key in ("sessionID", "sessionId"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def list_session_ids(
    runner: CommandRunner,
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: float,
) -> tuple[str, ...]:
    result = runner.run(
        ("opencode", "session", "list", "--pure"),
        cwd=cwd,
        env=env,
        timeout_seconds=timeout_seconds,
    )
    if result.returncode != 0:
        return ()
    return parse_session_list(result.stdout)


def parse_session_list(stdout: str) -> tuple[str, ...]:
    session_ids: list[str] = []
    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("Session ID"):
            continue
        if set(stripped) == {"─"}:
            continue
        session_id = stripped.split()[0]
        if session_id.startswith("ses_"):
            session_ids.append(session_id)
    return tuple(session_ids)


def detect_new_session_id(
    before_session_ids: tuple[str, ...], after_session_ids: tuple[str, ...]
) -> str | None:
    before = set(before_session_ids)
    for session_id in after_session_ids:
        if session_id not in before:
            return session_id
    if after_session_ids:
        return after_session_ids[0]
    return None


def managed_base_url(env: dict[str, str]) -> str | None:
    config = _managed_config(env)
    if config is None:
        return None
    enabled = config.get("enabled_providers")
    providers = config.get("provider")
    if not isinstance(enabled, list) or not isinstance(providers, dict):
        return None
    for provider_id in enabled:
        provider = providers.get(provider_id)
        if not isinstance(provider, dict):
            continue
        options = provider.get("options")
        if not isinstance(options, dict):
            continue
        base_url = options.get("baseURL")
        if isinstance(base_url, str) and base_url:
            return base_url
    return None


def with_managed_base_url(env: dict[str, str], base_url: str) -> dict[str, str]:
    config = _managed_config(env)
    if config is None:
        return dict(env)
    providers = config.get("provider")
    if isinstance(providers, dict):
        for provider in providers.values():
            if not isinstance(provider, dict):
                continue
            options = provider.get("options")
            if isinstance(options, dict):
                options["baseURL"] = base_url
    updated_env = dict(env)
    updated_env["OPENCODE_CONFIG_CONTENT"] = json.dumps(
        config,
        separators=(",", ":"),
    )
    return updated_env


def _managed_config(env: dict[str, str]) -> dict[str, object] | None:
    raw = env.get("OPENCODE_CONFIG_CONTENT")
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def terminate_process(process: RunningProcessLike) -> None:
    try:
        process.terminate()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2.0)
        return
    except (subprocess.TimeoutExpired, ChildProcessError):
        pass
    try:
        process.kill()
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=2.0)
    except (subprocess.TimeoutExpired, ChildProcessError):
        return


def read_process_output(process: RunningProcessLike) -> str:
    stdout = ""
    stderr = ""
    if process.stdout is not None:
        stdout = process.stdout.read()
    if process.stderr is not None:
        stderr = process.stderr.read()
    return f"stdout={stdout!r} stderr={stderr!r}"


def _merged_env(extra_env: dict[str, str]) -> dict[str, str]:
    env = dict(os.environ)
    env.update(extra_env)
    return env
