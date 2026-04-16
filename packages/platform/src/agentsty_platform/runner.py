"""Runnable sandbox entrypoint used by local development execution."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime
from importlib import import_module
from pathlib import Path
from typing import Any, cast


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentsty-platform-runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser(
        "serve",
        help="hold a local-development sandbox process open until terminated",
    )
    serve.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=0.1,
        help="sleep interval while waiting for termination",
    )

    subparsers.add_parser(
        "execute",
        help="run the prepared runtime invocation inside the sandbox boundary",
    )

    smoke = subparsers.add_parser(
        "smoke",
        help="emit a direct smoke-test message and exit successfully",
    )
    smoke.add_argument(
        "--message",
        default="agentsty local runner ready",
        help="message to print during smoke verification",
    )
    return parser


def _serve(heartbeat_seconds: float) -> int:
    running = True

    def _stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    while running:
        time.sleep(max(0.01, heartbeat_seconds))
    return 0


def _execute() -> int:
    config = import_module("agentsty_platform.config")
    gateway = import_module("agentsty_platform.gateway")
    observability = import_module("agentsty_platform.observability")
    runtimes = import_module("agentsty_platform.runtimes")

    settings = config.PlatformSettings.from_env()
    payload = _runner_payload_from_env()
    session = _session_from_payload(runtimes, observability, payload)
    invocation = _invocation_from_payload(
        gateway=gateway,
        observability=observability,
        runtimes=runtimes,
        payload=payload,
    )
    gateway_client = gateway.InternalGatewayClient(
        settings=settings,
        transport=(
            gateway.LocalGatewayTransport()
            if getattr(settings.profile, "value", settings.profile) == "local"
            else gateway.HTTPGatewayTransport()
        ),
        token_provider=(
            gateway.StaticInternalAuthTokenProvider()
            if getattr(settings.profile, "value", settings.profile) == "local"
            else gateway.ServiceGatewayTokenProvider.from_settings(settings)
        ),
    )
    adapter = runtimes.build_runtime_adapter_from_env(
        settings,
        gateway_client,
        environ=os.environ,
    )
    _ = adapter.invoke(session, invocation)
    return 0


def _runner_payload_from_env() -> dict[str, object]:
    raw = os.environ.get("AGENTSTY_RUNNER_PAYLOAD")
    if raw is None:
        raise ValueError("missing AGENTSTY_RUNNER_PAYLOAD")
    return cast(dict[str, object], json.loads(raw))


def _session_from_payload(
    runtimes: Any, observability: Any, payload: dict[str, object]
) -> object:
    session_payload = payload["session"]
    assert isinstance(session_payload, dict)
    trace_context = _trace_context_from_json(
        observability, payload.get("trace_context")
    )
    return runtimes.RuntimeSession(
        tenant_id=_tenant_id(payload),
        request_id=_request_id(payload),
        job_id=_job_id(payload),
        runtime_name=str(session_payload["runtime_name"]),
        session_id=str(session_payload["session_id"]),
        workspace_path=Path(str(session_payload["workspace_path"])),
        trace_context=trace_context,
        metadata=_metadata_from_json(session_payload.get("metadata", [])),
    )


def _invocation_from_payload(
    *,
    gateway: Any,
    observability: Any,
    runtimes: Any,
    payload: dict[str, object],
) -> object:
    execution_payload = payload["execution"]
    assert isinstance(execution_payload, dict)
    gateway_request_payload = execution_payload["payload"]
    assert isinstance(gateway_request_payload, dict)
    trace_context = _trace_context_from_json(
        observability, gateway_request_payload.get("trace_context")
    )
    execution = import_module("agentsty_platform.domain").ExecutionRequest(
        tenant_id=_tenant_id(payload),
        request_id=_request_id(payload),
        job_id=_job_id(payload),
        idempotency_key=import_module("agentsty_platform.domain").IdempotencyKey(
            str(execution_payload["idempotency_key"])
        ),
        payload=gateway.GatewayRequest(
            tenant_id=_tenant_id(payload),
            target=gateway.GatewayModelTarget(
                provider=_optional_str(gateway_request_payload.get("provider")),
                model=str(gateway_request_payload["model"]),
            ),
            messages=tuple(
                gateway.GatewayMessage(
                    role=gateway.GatewayMessageRole(str(message["role"])),
                    content=str(message["content"]),
                    name=_optional_str(message.get("name")),
                    metadata=_metadata_from_json(message.get("metadata", [])),
                )
                for message in gateway_request_payload["messages"]
            ),
            allowlist=gateway.GatewayAllowlist(
                allowed_providers=tuple(
                    gateway_request_payload["allowlist"]["allowed_providers"]
                ),
                allowed_models=tuple(
                    gateway_request_payload["allowlist"]["allowed_models"]
                ),
            ),
            sampling=gateway.GatewaySampling(
                temperature=gateway_request_payload["sampling"].get("temperature"),
                max_output_tokens=gateway_request_payload["sampling"].get(
                    "max_output_tokens"
                ),
                stop_sequences=tuple(
                    gateway_request_payload["sampling"]["stop_sequences"]
                ),
            ),
            request_timeout_seconds=gateway_request_payload.get(
                "request_timeout_seconds"
            ),
            trace_context=trace_context,
            metadata=_metadata_from_json(gateway_request_payload.get("metadata", [])),
        ),
        submitted_at=datetime.fromisoformat(str(execution_payload["submitted_at"])),
        timeouts=import_module("agentsty_platform.domain").ExecutionTimeouts(
            request_timeout_seconds=int(
                execution_payload["timeouts"]["request_timeout_seconds"]
            ),
            execution_timeout_seconds=int(
                execution_payload["timeouts"]["execution_timeout_seconds"]
            ),
            cancellation_grace_period_seconds=int(
                execution_payload["timeouts"]["cancellation_grace_period_seconds"]
            ),
        ),
        metadata=_metadata_from_json(execution_payload.get("metadata", [])),
    )
    return runtimes.RuntimeInvocationRequest(
        execution=execution,
        metadata=_metadata_from_json(payload.get("invocation_metadata", [])),
    )


def _trace_context_from_json(observability: Any, payload: object) -> object | None:
    if payload is None:
        return None
    assert isinstance(payload, dict)
    tenant_id = (
        None
        if payload.get("tenant_id") is None
        else import_module("agentsty_platform.domain").TenantId(
            str(payload["tenant_id"])
        )
    )
    request_id = (
        None
        if payload.get("request_id") is None or tenant_id is None
        else import_module("agentsty_platform.domain").RequestId(
            tenant_id=tenant_id,
            value=str(payload["request_id"]),
        )
    )
    job_id = (
        None
        if payload.get("job_id") is None or tenant_id is None
        else import_module("agentsty_platform.domain").JobId(
            tenant_id=tenant_id,
            value=str(payload["job_id"]),
        )
    )
    return cast(
        object,
        observability.TraceContext(
            correlation_id=str(payload["correlation_id"]),
            tenant_id=tenant_id,
            request_id=request_id,
            job_id=job_id,
            trace_id=_optional_str(payload.get("trace_id")),
            span_id=_optional_str(payload.get("span_id")),
            parent_span_id=_optional_str(payload.get("parent_span_id")),
            metadata=_metadata_from_json(payload.get("metadata", [])),
        ),
    )


def _tenant_id(payload: dict[str, object]) -> object:
    return import_module("agentsty_platform.domain").TenantId(str(payload["tenant_id"]))


def _request_id(payload: dict[str, object]) -> object:
    tenant_id = _tenant_id(payload)
    return import_module("agentsty_platform.domain").RequestId(
        tenant_id=tenant_id,
        value=str(payload["request_id"]),
    )


def _job_id(payload: dict[str, object]) -> object:
    tenant_id = _tenant_id(payload)
    return import_module("agentsty_platform.domain").JobId(
        tenant_id=tenant_id,
        value=str(payload["job_id"]),
    )


def _metadata_from_json(payload: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(payload, list):
        return ()
    return tuple((str(entry[0]), str(entry[1])) for entry in payload)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "serve":
        return _serve(args.heartbeat_seconds)
    if args.command == "execute":
        return _execute()
    if args.command == "smoke":
        print(args.message)
        return 0
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
