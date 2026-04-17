from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


@pytest.fixture
def live_server() -> Iterator[str]:
    root = Path(__file__).resolve().parents[2]
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"

    env = os.environ.copy()
    python_path_entries = [str(root), str(root / "src")]
    existing_python_path = env.get("PYTHONPATH")
    if existing_python_path:
        python_path_entries.append(existing_python_path)
    env["PYTHONPATH"] = os.pathsep.join(python_path_entries)

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "apps.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        for _ in range(30):
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout is not None else ""
                raise RuntimeError(f"Uvicorn exited early:\n{output}")

            try:
                response = httpx.get(f"{base_url}/health", timeout=1.0)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.2)
        else:
            output = process.stdout.read() if process.stdout is not None else ""
            raise RuntimeError(f"Timed out waiting for live server:\n{output}")

        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_live_health_endpoint(live_server: str) -> None:
    response = httpx.get(f"{live_server}/health", timeout=5.0)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_live_chat_completion_happy_path(live_server: str) -> None:
    response = httpx.post(
        f"{live_server}/v1/chat/completions",
        json={
            "tenant_id": "tenant-demo",
            "message": "hello phase1",
            "metadata": {"trace_id": "demo-1"},
        },
        timeout=5.0,
    )

    body = response.json()
    assert response.status_code == 200
    assert body["status"] == "completed"
    assert body["generated_text"] == "OpenCodeRuntime stub response: hello phase1"
    assert body["runtime_name"] == "opencode"
    assert body["sandbox_execution_id"].startswith("sbx-")
    assert isinstance(body["artifacts"], list)


def test_live_chat_completion_validation_failure(live_server: str) -> None:
    response = httpx.post(f"{live_server}/v1/chat/completions", json={}, timeout=5.0)

    assert response.status_code == 422
