"""Headless OpenCode runtime adapter backed by real CLI invocation."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

from .config import (
    OpenCodeGatewayConfig,
    build_managed_env,
    gateway_provider_base_url,
    prompt_from_messages,
    provider_id_for_target,
)
from .parsing import ParsedOpenCodeExport, parse_export_payload
from .process import (
    CommandRunner,
    SubprocessCommandRunner,
    invoke_headless_opencode,
)

OPENCODE_RUNTIME_NAME = "opencode"


class RuntimeSettingsLike(Protocol):
    backend: str


class GatewaySettingsLike(Protocol):
    base_url: str
    request_path: str
    audience: str


class AuthSettingsLike(Protocol):
    required: bool
    allow_anonymous_local: bool


class SettingsLike(Protocol):
    gateway: GatewaySettingsLike
    auth: AuthSettingsLike


class TokenProviderLike(Protocol):
    def issue_token(
        self,
        *,
        tenant_id: object,
        audience: str,
        trace_context: object | None = None,
        metadata: tuple[tuple[str, str], ...] = (),
    ) -> object: ...


class GatewayClientLike(Protocol):
    settings: SettingsLike
    token_provider: TokenProviderLike | None

    def generate(self, request: object) -> object: ...


class GatewayTargetLike(Protocol):
    model: str
    provider: str | None
    label: str


class GatewayMessageLike(Protocol):
    role: object
    content: str
    name: str | None
    metadata: tuple[tuple[str, str], ...]


class GatewayRequestLike(Protocol):
    tenant_id: object
    target: GatewayTargetLike
    messages: tuple[GatewayMessageLike, ...]
    request_timeout_seconds: int | None
    trace_context: object | None


class ExecutionTimeoutsLike(Protocol):
    execution_timeout_seconds: int


class ExecutionRequestLike(Protocol):
    tenant_id: object
    request_id: object
    job_id: object
    payload: GatewayRequestLike
    timeouts: ExecutionTimeoutsLike


class RuntimeSessionLike(Protocol):
    tenant_id: object
    request_id: object
    job_id: object
    session_id: str
    workspace_path: Path


class RuntimePreparationRequestLike(Protocol):
    tenant_id: object
    request_id: object
    job_id: object
    workspace_path: Path
    trace_context: object | None
    metadata: tuple[tuple[str, str], ...]


class RuntimeInvocationRequestLike(Protocol):
    execution: ExecutionRequestLike
    metadata: tuple[tuple[str, str], ...]


class RuntimeCapabilitiesLike(Protocol):
    automation_mode: object


class RuntimeCollectionRequestLike(Protocol):
    tenant_id: object
    request_id: object
    job_id: object
    session_id: str
    metadata: tuple[tuple[str, str], ...]


class RuntimeCancellationRequestLike(Protocol):
    tenant_id: object
    request_id: object
    job_id: object
    session_id: str
    reason: str | None
    requested_at: datetime
    metadata: tuple[tuple[str, str], ...]


class RuntimeCleanupRequestLike(Protocol):
    tenant_id: object
    request_id: object
    job_id: object
    session_id: str
    metadata: tuple[tuple[str, str], ...]


class RuntimeCancellationReceiptLike(Protocol):
    acknowledged: bool
    requested_at: datetime
    error: ErrorDetailsLike | None
    metadata: tuple[tuple[str, str], ...]


class RuntimeInvocationReceiptLike(Protocol):
    accepted_at: datetime
    automation_mode: object
    metadata: tuple[tuple[str, str], ...]


class GatewayUsageLike(Protocol):
    input_tokens: int
    output_tokens: int


class GatewayResponseLike(Protocol):
    target: GatewayTargetLike
    message: GatewayMessageLike
    finish_reason: object
    usage: GatewayUsageLike
    gateway_request_id: str | None
    trace_context: TraceContextLike | None
    completed_at: datetime
    metadata: tuple[tuple[str, str], ...]


class ResultSummaryLike(Protocol):
    output_text: str | None
    duration_seconds: float | None
    artifact_count: int
    metadata: tuple[tuple[str, str], ...]


class ArtifactSummaryLike(Protocol):
    key: str
    media_type: str | None
    size_bytes: int
    sha256: str | None
    redacted: bool
    metadata: tuple[tuple[str, str], ...]


class ErrorDetailsLike(Protocol):
    category: object
    message: str
    code: str | None
    retryable: bool
    metadata: tuple[tuple[str, str], ...]


class ExecutionResultLike(Protocol):
    tenant_id: object
    request_id: ValueLike
    job_id: ValueLike
    status: object
    completed_at: datetime
    payload: GatewayResponseLike | None
    summary: ResultSummaryLike | None
    artifacts: tuple[ArtifactSummaryLike, ...]
    error: ErrorDetailsLike | None


class TraceContextLike(Protocol):
    tenant_id: object | None
    request_id: ValueLike | None
    job_id: ValueLike | None
    correlation_id: str
    trace_id: str | None
    span_id: str | None
    parent_span_id: str | None
    metadata: tuple[tuple[str, str], ...]


class DomainErrorLike(Protocol):
    def as_details(self) -> object: ...


class InternalAuthContextLike(Protocol):
    authorization_header: str | None


class ValueLike(Protocol):
    value: str


def _domain_module() -> Any:
    return import_module("agentsty_platform.domain")


def _gateway_module() -> Any:
    return import_module("agentsty_platform.gateway")


def _observability_module() -> Any:
    return import_module("agentsty_platform.observability")


def _runtimes_module() -> Any:
    return import_module("agentsty_platform.runtimes")


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class OpenCodeRuntimeAdapter:
    """Automation-friendly OpenCode adapter that runs the real CLI headlessly."""

    gateway_client: GatewayClientLike
    runtime_settings: RuntimeSettingsLike
    command_runner: CommandRunner = field(default_factory=SubprocessCommandRunner)

    def __post_init__(self) -> None:
        if self.runtime_settings.backend != OPENCODE_RUNTIME_NAME:
            raise ValueError("runtime settings backend must be 'opencode'")

    @property
    def runtime_name(self) -> str:
        return OPENCODE_RUNTIME_NAME

    @property
    def capabilities(self) -> RuntimeCapabilitiesLike:
        runtimes = _runtimes_module()
        return cast(
            RuntimeCapabilitiesLike,
            runtimes.RuntimeCapabilities(
                automation_mode=runtimes.RuntimeAutomationMode.HEADLESS,
                uses_internal_gateway=True,
                supports_result_collection=True,
                supports_cancellation=True,
                supports_cleanup=True,
            ),
        )

    def prepare(self, request: RuntimePreparationRequestLike) -> object:
        runtimes = _runtimes_module()
        request.workspace_path.mkdir(parents=True, exist_ok=True)
        session = runtimes.RuntimeSession(
            tenant_id=request.tenant_id,
            request_id=request.request_id,
            job_id=request.job_id,
            runtime_name=self.runtime_name,
            session_id=f"{self.runtime_name}-{uuid4().hex}",
            workspace_path=request.workspace_path,
            capabilities=self.capabilities,
            trace_context=request.trace_context,
            metadata=request.metadata
            + (
                ("gateway_routing", "internal"),
                ("runtime_backend", self.runtime_name),
            ),
        )
        state_dir = _runtime_state_dir(session)
        if state_dir.exists():
            shutil.rmtree(state_dir)
        return session

    def invoke(
        self, session: RuntimeSessionLike, request: RuntimeInvocationRequestLike
    ) -> object:
        self._require_execution_match(session, request)
        if _read_invocation_receipt(session) is not None:
            raise _domain_module().RuntimeExecutionError(
                "runtime session has already been invoked"
            )

        accepted_at = _utc_now()
        runtimes = _runtimes_module()
        receipt = runtimes.RuntimeInvocationReceipt(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            session_id=session.session_id,
            accepted_at=accepted_at,
            automation_mode=self.capabilities.automation_mode,
            metadata=request.metadata + (("runtime_backend", self.runtime_name),),
        )
        _write_invocation_receipt(session, receipt)

        cancellation_receipt = _read_cancellation_receipt(session)
        if cancellation_receipt is not None and cancellation_receipt.acknowledged:
            _write_result(
                session,
                _cancelled_result(session, accepted_at, cancellation_receipt),
            )
            return receipt

        _write_result(session, self._execute_invocation(session, request, accepted_at))
        return receipt

    def collect_result(
        self,
        session: RuntimeSessionLike,
        request: RuntimeCollectionRequestLike | None = None,
    ) -> object:
        if request is not None:
            self._require_request_match(session, request)

        metadata = request.metadata if request is not None else ()
        result = _read_result(session)
        return _runtimes_module().RuntimeCollectionResult(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            session_id=session.session_id,
            ready=result is not None,
            result=result,
            metadata=metadata + (("runtime_backend", self.runtime_name),),
        )

    def request_cancellation(
        self,
        session: RuntimeSessionLike,
        request: RuntimeCancellationRequestLike,
    ) -> object:
        self._require_request_match(session, request)
        domain = _domain_module()
        runtimes = _runtimes_module()

        if _read_result(session) is not None:
            return runtimes.RuntimeCancellationReceipt(
                tenant_id=session.tenant_id,
                request_id=session.request_id,
                job_id=session.job_id,
                session_id=session.session_id,
                acknowledged=False,
                requested_at=request.requested_at,
                error=domain.RuntimeExecutionError(
                    "runtime execution already completed before cancellation"
                ).as_details(),
                metadata=request.metadata + (("runtime_backend", self.runtime_name),),
            )

        receipt = runtimes.RuntimeCancellationReceipt(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            session_id=session.session_id,
            acknowledged=True,
            requested_at=request.requested_at,
            metadata=request.metadata + (("runtime_backend", self.runtime_name),),
        )
        _write_cancellation_receipt(session, receipt)
        if _read_invocation_receipt(session) is None:
            _write_result(
                session,
                _cancelled_result(
                    session, request.requested_at, receipt, request.reason
                ),
            )
        return receipt

    def cleanup(
        self,
        session: RuntimeSessionLike,
        request: RuntimeCleanupRequestLike | None = None,
    ) -> object:
        if request is not None:
            self._require_request_match(session, request)
            metadata = request.metadata
        else:
            metadata = ()

        state_dir = _runtime_state_dir(session)
        for path in (
            _invocation_receipt_path(session),
            _cancellation_receipt_path(session),
            _result_path(session),
        ):
            if path.exists():
                path.unlink()
        if state_dir.exists():
            shutil.rmtree(state_dir)
        return _runtimes_module().RuntimeCleanupResult(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            session_id=session.session_id,
            cleaned=True,
            released_paths=(str(session.workspace_path),),
            metadata=metadata + (("runtime_backend", self.runtime_name),),
        )

    def _require_execution_match(
        self,
        session: RuntimeSessionLike,
        request: RuntimeInvocationRequestLike,
    ) -> None:
        execution = request.execution
        if execution.tenant_id != session.tenant_id:
            raise _domain_module().RuntimeExecutionError(
                "execution tenant must match runtime session"
            )
        if execution.request_id != session.request_id:
            raise _domain_module().RuntimeExecutionError(
                "execution request id must match runtime session"
            )
        if execution.job_id != session.job_id:
            raise _domain_module().RuntimeExecutionError(
                "execution job id must match runtime session"
            )

    def _require_request_match(
        self,
        session: RuntimeSessionLike,
        request: RuntimeCollectionRequestLike
        | RuntimeCancellationRequestLike
        | RuntimeCleanupRequestLike,
    ) -> None:
        if request.tenant_id != session.tenant_id:
            raise _domain_module().RuntimeExecutionError(
                "runtime request tenant must match session"
            )
        if request.request_id != session.request_id:
            raise _domain_module().RuntimeExecutionError(
                "runtime request id must match session"
            )
        if request.job_id != session.job_id:
            raise _domain_module().RuntimeExecutionError(
                "runtime request job id must match session"
            )
        if request.session_id != session.session_id:
            raise _domain_module().RuntimeExecutionError(
                "runtime request session id must match session"
            )

    def _execute_invocation(
        self,
        session: RuntimeSessionLike,
        request: RuntimeInvocationRequestLike,
        accepted_at: datetime,
    ) -> ExecutionResultLike:
        domain = _domain_module()
        gateway = _gateway_module()
        runtimes = _runtimes_module()
        try:
            auth_context = cast(
                InternalAuthContextLike,
                gateway.resolve_internal_auth_context(
                    tenant_id=request.execution.tenant_id,
                    audience=self.gateway_client.settings.gateway.audience,
                    token_provider=self.gateway_client.token_provider,
                    trace_context=request.execution.payload.trace_context,
                    allow_anonymous=(
                        not self.gateway_client.settings.auth.required
                        and self.gateway_client.settings.auth.allow_anonymous_local
                    ),
                    metadata=(("runtime_backend", self.runtime_name),),
                ),
            )
            provider_id = provider_id_for_target(
                request.execution.payload.target.provider
            )
            prompt = prompt_from_messages(
                tuple(
                    (_string_value(message.role), message.content)
                    for message in request.execution.payload.messages
                )
            )
            managed_env = build_managed_env(
                OpenCodeGatewayConfig(
                    tenant_id=_string_value(request.execution.tenant_id),
                    provider_id=provider_id,
                    model_id=request.execution.payload.target.model,
                    gateway_base_url=gateway_provider_base_url(
                        self.gateway_client.settings.gateway.base_url,
                        self.gateway_client.settings.gateway.request_path,
                    ),
                    authorization_header=auth_context.authorization_header,
                )
            )
            invocation = invoke_headless_opencode(
                self.command_runner,
                workspace_path=session.workspace_path,
                managed_env=managed_env,
                model=f"{provider_id}/{request.execution.payload.target.model}",
                prompt=prompt,
                execution_timeout_seconds=request.execution.timeouts.execution_timeout_seconds,
            )
            if invocation.run_result.returncode != 0:
                raise domain.RuntimeExecutionError(
                    f"opencode run failed with code {invocation.run_result.returncode}",
                    metadata=(
                        ("stderr", invocation.run_result.stderr.strip() or "none"),
                    ),
                )
            if invocation.export_result.returncode != 0:
                raise domain.RuntimeExecutionError(
                    f"opencode export failed with code {invocation.export_result.returncode}",
                    metadata=(
                        ("stderr", invocation.export_result.stderr.strip() or "none"),
                    ),
                )
            try:
                exported = parse_export_payload(invocation.export_result.stdout)
            except ValueError as error:
                if (
                    str(error) == "OpenCode export did not include assistant text"
                    and invocation.captured_output_text
                ):
                    exported = ParsedOpenCodeExport(
                        session_id=invocation.session_id,
                        output_text=invocation.captured_output_text,
                        finish_reason="stop",
                    )
                else:
                    raise
            finish_reason = _gateway_finish_reason(exported.finish_reason)
            completed_at = _utc_now()
            artifacts = _write_runtime_artifacts(
                session,
                raw_export=invocation.export_result.stdout,
                exported=exported,
            )
            response = gateway.GatewayResponse(
                tenant_id=session.tenant_id,
                target=request.execution.payload.target,
                message=gateway.GatewayMessage(
                    role=gateway.GatewayMessageRole.ASSISTANT,
                    content=exported.output_text,
                ),
                finish_reason=finish_reason,
                usage=gateway.GatewayUsage(
                    input_tokens=_estimate_tokens(prompt),
                    output_tokens=_estimate_tokens(exported.output_text),
                ),
                trace_context=request.execution.payload.trace_context,
                completed_at=completed_at,
                metadata=request.metadata
                + (
                    ("runtime_backend", self.runtime_name),
                    ("opencode_session_id", exported.session_id),
                ),
            )
            return cast(
                ExecutionResultLike,
                domain.ExecutionResult(
                    tenant_id=session.tenant_id,
                    request_id=session.request_id,
                    job_id=session.job_id,
                    status=domain.ExecutionStatus.SUCCEEDED,
                    completed_at=completed_at,
                    payload=response,
                    summary=domain.ResultSummary(
                        output_text=exported.output_text,
                        duration_seconds=max(
                            0.0, (completed_at - accepted_at).total_seconds()
                        ),
                        artifact_count=len(artifacts),
                        metadata=request.metadata
                        + (
                            ("runtime_backend", self.runtime_name),
                            ("finish_reason", _string_value(finish_reason)),
                            ("opencode_session_id", exported.session_id),
                        ),
                    ),
                    artifacts=artifacts,
                ),
            )
        except Exception as error:
            if not hasattr(error, "as_details"):
                error = domain.RuntimeExecutionError(
                    str(error) or "opencode runtime failed"
                )
            details = cast(DomainErrorLike, error).as_details()
            completed_at = _utc_now()
            return cast(
                ExecutionResultLike,
                domain.ExecutionResult(
                    tenant_id=session.tenant_id,
                    request_id=session.request_id,
                    job_id=session.job_id,
                    status=runtimes.status_for_error(details),
                    completed_at=completed_at,
                    summary=domain.ResultSummary(
                        duration_seconds=max(
                            0.0, (completed_at - accepted_at).total_seconds()
                        ),
                        metadata=request.metadata
                        + (("runtime_backend", self.runtime_name),),
                    ),
                    error=details,
                ),
            )


def _gateway_finish_reason(value: str) -> object:
    gateway = _gateway_module()
    normalized = value.strip().lower()
    if normalized == "length":
        return gateway.GatewayFinishReason.LENGTH
    if normalized == "tool_call":
        return gateway.GatewayFinishReason.TOOL_CALL
    if normalized == "error":
        return gateway.GatewayFinishReason.ERROR
    return gateway.GatewayFinishReason.STOP


def _estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def _string_value(value: object) -> str:
    if isinstance(value, str):
        return value
    if hasattr(value, "value"):
        return cast(ValueLike, value).value
    return str(value)


def _cancelled_result(
    session: RuntimeSessionLike,
    completed_at: datetime,
    receipt: RuntimeCancellationReceiptLike,
    reason: str | None = None,
) -> ExecutionResultLike:
    domain = _domain_module()
    message = reason or "runtime execution cancelled before completion"
    error = domain.CancellationError(message).as_details()
    return cast(
        ExecutionResultLike,
        domain.ExecutionResult(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            status=domain.ExecutionStatus.CANCELLED,
            completed_at=completed_at,
            summary=domain.ResultSummary(
                duration_seconds=0.0,
                metadata=receipt.metadata
                + (("runtime_backend", OPENCODE_RUNTIME_NAME),),
            ),
            error=error,
        ),
    )


def _runtime_state_dir(session: RuntimeSessionLike) -> Path:
    return session.workspace_path / ".agentsty-runtime"


def _invocation_receipt_path(session: RuntimeSessionLike) -> Path:
    return _runtime_state_dir(session) / "invocation_receipt.json"


def _cancellation_receipt_path(session: RuntimeSessionLike) -> Path:
    return _runtime_state_dir(session) / "cancellation_receipt.json"


def _result_path(session: RuntimeSessionLike) -> Path:
    return _runtime_state_dir(session) / "result.json"


def _write_invocation_receipt(
    session: RuntimeSessionLike,
    receipt: RuntimeInvocationReceiptLike,
) -> None:
    _write_json(
        _invocation_receipt_path(session),
        {
            "accepted_at": receipt.accepted_at.isoformat(),
            "automation_mode": _string_value(receipt.automation_mode),
            "metadata": _metadata_to_json(receipt.metadata),
        },
    )


def _read_invocation_receipt(session: RuntimeSessionLike) -> object | None:
    payload = _read_json(_invocation_receipt_path(session))
    if payload is None:
        return None
    runtimes = _runtimes_module()
    return cast(
        object,
        runtimes.RuntimeInvocationReceipt(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            session_id=session.session_id,
            accepted_at=datetime.fromisoformat(cast(str, payload["accepted_at"])),
            automation_mode=runtimes.RuntimeAutomationMode(
                cast(str, payload["automation_mode"])
            ),
            metadata=_metadata_from_json(
                cast(list[list[str]], payload.get("metadata", []))
            ),
        ),
    )


def _write_cancellation_receipt(
    session: RuntimeSessionLike,
    receipt: RuntimeCancellationReceiptLike,
) -> None:
    error = receipt.error
    _write_json(
        _cancellation_receipt_path(session),
        {
            "acknowledged": receipt.acknowledged,
            "requested_at": receipt.requested_at.isoformat(),
            "error": None if error is None else _serialize_error_details(error),
            "metadata": _metadata_to_json(receipt.metadata),
        },
    )


def _read_cancellation_receipt(
    session: RuntimeSessionLike,
) -> RuntimeCancellationReceiptLike | None:
    payload = _read_json(_cancellation_receipt_path(session))
    if payload is None:
        return None
    runtimes = _runtimes_module()
    error_payload = cast(dict[str, object] | None, payload.get("error"))
    return cast(
        RuntimeCancellationReceiptLike,
        runtimes.RuntimeCancellationReceipt(
            tenant_id=session.tenant_id,
            request_id=session.request_id,
            job_id=session.job_id,
            session_id=session.session_id,
            acknowledged=cast(bool, payload["acknowledged"]),
            requested_at=datetime.fromisoformat(cast(str, payload["requested_at"])),
            error=(
                None
                if error_payload is None
                else _error_details_from_json(error_payload)
            ),
            metadata=_metadata_from_json(
                cast(list[list[str]], payload.get("metadata", []))
            ),
        ),
    )


def _write_result(session: RuntimeSessionLike, result: ExecutionResultLike) -> None:
    _write_json(_result_path(session), _serialize_execution_result(result))


def _read_result(session: RuntimeSessionLike) -> object | None:
    payload = _read_json(_result_path(session))
    if payload is None:
        return None
    return _execution_result_from_json(payload)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")


def _read_json(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _write_runtime_artifacts(
    session: RuntimeSessionLike,
    *,
    raw_export: str,
    exported: ParsedOpenCodeExport,
) -> tuple[object, ...]:
    domain = _domain_module()
    export_bytes = raw_export.encode("utf-8")
    artifact_key = "opencode/session-export.json"
    artifact_path = _artifact_path(session, artifact_key)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    _ = artifact_path.write_bytes(export_bytes)
    return (
        domain.ArtifactSummary(
            key=artifact_key,
            media_type="application/json",
            size_bytes=len(export_bytes),
            sha256=sha256(export_bytes).hexdigest(),
            metadata=(
                ("artifact_kind", "opencode_session_export"),
                ("opencode_session_id", exported.session_id),
            ),
        ),
    )


def _artifact_path(session: RuntimeSessionLike, artifact_key: str) -> Path:
    artifact_path = Path(artifact_key)
    if artifact_path.is_absolute() or ".." in artifact_path.parts:
        raise ValueError("artifact key must resolve to a safe relative path")
    return _runtime_state_dir(session).joinpath("artifacts", *artifact_path.parts)


def _serialize_execution_result(result: ExecutionResultLike) -> dict[str, object]:
    payload = result.payload
    summary = result.summary
    error = result.error
    return {
        "tenant_id": _string_value(result.tenant_id),
        "request_id": result.request_id.value,
        "job_id": result.job_id.value,
        "status": _string_value(result.status),
        "completed_at": result.completed_at.isoformat(),
        "payload": None if payload is None else _serialize_gateway_response(payload),
        "summary": None if summary is None else _serialize_result_summary(summary),
        "artifacts": [
            _serialize_artifact_summary(artifact) for artifact in result.artifacts
        ],
        "error": None if error is None else _serialize_error_details(error),
    }


def _execution_result_from_json(payload: dict[str, object]) -> object:
    domain = _domain_module()
    tenant_id = domain.TenantId(cast(str, payload["tenant_id"]))
    return domain.ExecutionResult(
        tenant_id=tenant_id,
        request_id=domain.RequestId(
            tenant_id=tenant_id, value=cast(str, payload["request_id"])
        ),
        job_id=domain.JobId(tenant_id=tenant_id, value=cast(str, payload["job_id"])),
        status=domain.ExecutionStatus(cast(str, payload["status"])),
        completed_at=datetime.fromisoformat(cast(str, payload["completed_at"])),
        payload=(
            None
            if payload.get("payload") is None
            else _gateway_response_from_json(
                tenant_id, cast(dict[str, object], payload["payload"])
            )
        ),
        summary=(
            None
            if payload.get("summary") is None
            else _result_summary_from_json(cast(dict[str, object], payload["summary"]))
        ),
        artifacts=tuple(
            _artifact_summary_from_json(cast(dict[str, object], artifact_payload))
            for artifact_payload in cast(list[object], payload.get("artifacts", []))
            if isinstance(artifact_payload, dict)
        ),
        error=(
            None
            if payload.get("error") is None
            else _error_details_from_json(cast(dict[str, object], payload["error"]))
        ),
    )


def _serialize_gateway_response(response: GatewayResponseLike) -> dict[str, object]:
    target = response.target
    message = response.message
    usage = response.usage
    return {
        "target": {
            "model": target.model,
            "provider": target.provider,
        },
        "message": {
            "role": _string_value(message.role),
            "content": message.content,
            "name": message.name,
            "metadata": _metadata_to_json(message.metadata),
        },
        "finish_reason": _string_value(response.finish_reason),
        "usage": {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
        },
        "gateway_request_id": response.gateway_request_id,
        "trace_context": _serialize_trace_context(response.trace_context),
        "completed_at": response.completed_at.isoformat(),
        "metadata": _metadata_to_json(response.metadata),
    }


def _gateway_response_from_json(
    tenant_id: object, payload: dict[str, object]
) -> object:
    gateway = _gateway_module()
    target_payload = cast(dict[str, object], payload["target"])
    message_payload = cast(dict[str, object], payload["message"])
    usage_payload = cast(dict[str, object], payload["usage"])
    return gateway.GatewayResponse(
        tenant_id=tenant_id,
        target=gateway.GatewayModelTarget(
            model=cast(str, target_payload["model"]),
            provider=cast(str | None, target_payload.get("provider")),
        ),
        message=gateway.GatewayMessage(
            role=gateway.GatewayMessageRole(cast(str, message_payload["role"])),
            content=cast(str, message_payload["content"]),
            name=cast(str | None, message_payload.get("name")),
            metadata=_metadata_from_json(
                cast(list[list[str]], message_payload.get("metadata", []))
            ),
        ),
        finish_reason=gateway.GatewayFinishReason(cast(str, payload["finish_reason"])),
        usage=gateway.GatewayUsage(
            input_tokens=cast(int, usage_payload["input_tokens"]),
            output_tokens=cast(int, usage_payload["output_tokens"]),
        ),
        gateway_request_id=cast(str | None, payload.get("gateway_request_id")),
        trace_context=_trace_context_from_json(
            cast(dict[str, object] | None, payload.get("trace_context"))
        ),
        completed_at=datetime.fromisoformat(cast(str, payload["completed_at"])),
        metadata=_metadata_from_json(
            cast(list[list[str]], payload.get("metadata", []))
        ),
    )


def _serialize_result_summary(summary: ResultSummaryLike) -> dict[str, object]:
    return {
        "output_text": summary.output_text,
        "duration_seconds": summary.duration_seconds,
        "artifact_count": summary.artifact_count,
        "metadata": _metadata_to_json(summary.metadata),
    }


def _serialize_artifact_summary(summary: ArtifactSummaryLike) -> dict[str, object]:
    return {
        "key": summary.key,
        "media_type": summary.media_type,
        "size_bytes": summary.size_bytes,
        "sha256": summary.sha256,
        "redacted": summary.redacted,
        "metadata": _metadata_to_json(summary.metadata),
    }


def _artifact_summary_from_json(payload: dict[str, object]) -> object:
    domain = _domain_module()
    return domain.ArtifactSummary(
        key=cast(str, payload["key"]),
        media_type=cast(str | None, payload.get("media_type")),
        size_bytes=cast(int, payload.get("size_bytes", 0)),
        sha256=cast(str | None, payload.get("sha256")),
        redacted=cast(bool, payload.get("redacted", False)),
        metadata=_metadata_from_json(
            cast(list[list[str]], payload.get("metadata", []))
        ),
    )


def _result_summary_from_json(payload: dict[str, object]) -> object:
    domain = _domain_module()
    return domain.ResultSummary(
        output_text=cast(str | None, payload.get("output_text")),
        duration_seconds=cast(float | None, payload.get("duration_seconds")),
        artifact_count=cast(int, payload.get("artifact_count", 0)),
        metadata=_metadata_from_json(
            cast(list[list[str]], payload.get("metadata", []))
        ),
    )


def _serialize_error_details(details: ErrorDetailsLike) -> dict[str, object]:
    return {
        "category": _string_value(details.category),
        "message": details.message,
        "code": details.code,
        "retryable": details.retryable,
        "metadata": _metadata_to_json(details.metadata),
    }


def _error_details_from_json(payload: dict[str, object]) -> object:
    domain = _domain_module()
    return domain.ErrorDetails(
        category=domain.ErrorCategory(cast(str, payload["category"])),
        message=cast(str, payload["message"]),
        code=cast(str | None, payload.get("code")),
        retryable=cast(bool, payload.get("retryable", False)),
        metadata=_metadata_from_json(
            cast(list[list[str]], payload.get("metadata", []))
        ),
    )


def _serialize_trace_context(
    trace_context: TraceContextLike | None,
) -> dict[str, object] | None:
    if trace_context is None:
        return None
    tenant_id = trace_context.tenant_id
    request_id = trace_context.request_id
    job_id = trace_context.job_id
    return {
        "correlation_id": trace_context.correlation_id,
        "tenant_id": None if tenant_id is None else _string_value(tenant_id),
        "request_id": None if request_id is None else request_id.value,
        "job_id": None if job_id is None else job_id.value,
        "trace_id": trace_context.trace_id,
        "span_id": trace_context.span_id,
        "parent_span_id": trace_context.parent_span_id,
        "metadata": _metadata_to_json(trace_context.metadata),
    }


def _trace_context_from_json(payload: dict[str, object] | None) -> object | None:
    if payload is None:
        return None
    observability = _observability_module()
    domain = _domain_module()
    tenant_value = cast(str | None, payload.get("tenant_id"))
    tenant_id = None if tenant_value is None else domain.TenantId(tenant_value)
    request_value = cast(str | None, payload.get("request_id"))
    job_value = cast(str | None, payload.get("job_id"))
    return cast(
        object,
        observability.TraceContext(
            correlation_id=cast(str, payload["correlation_id"]),
            tenant_id=tenant_id,
            request_id=(
                None
                if tenant_id is None or request_value is None
                else domain.RequestId(tenant_id=tenant_id, value=request_value)
            ),
            job_id=(
                None
                if tenant_id is None or job_value is None
                else domain.JobId(tenant_id=tenant_id, value=job_value)
            ),
            trace_id=cast(str | None, payload.get("trace_id")),
            span_id=cast(str | None, payload.get("span_id")),
            parent_span_id=cast(str | None, payload.get("parent_span_id")),
            metadata=_metadata_from_json(
                cast(list[list[str]], payload.get("metadata", []))
            ),
        ),
    )


def _metadata_to_json(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return [[key, value] for key, value in metadata]


def _metadata_from_json(payload: list[list[str]]) -> tuple[tuple[str, str], ...]:
    return tuple((key, value) for key, value in payload)
