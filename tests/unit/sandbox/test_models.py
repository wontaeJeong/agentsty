from uuid import uuid4

from agentsty_common.ownership import OwnershipContext
from agentsty_sandbox.models import NetworkPolicy, SandboxExecutionRequest


def test_network_policy_defaults_to_deny() -> None:
    policy = NetworkPolicy()

    assert policy.default_deny is True
    assert policy.allowlisted_hosts == ()


def test_sandbox_execution_request_uses_secret_references() -> None:
    request = SandboxExecutionRequest(
        run_id="run-1",
        ownership=OwnershipContext(tenant_id=uuid4()),
        command=("python", "-V"),
    )

    assert request.secret_references == ()
