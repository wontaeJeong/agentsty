from uuid import uuid4

from agentsty_common.ownership import OwnershipContext
from agentsty_sandbox.models import SandboxExecutionRequest
from agentsty_storage.models import SecretReference


def test_sandbox_models_use_secret_reference_contract() -> None:
    request = SandboxExecutionRequest(
        run_id="run-1",
        ownership=OwnershipContext(tenant_id=uuid4()),
        command=("echo", "hello"),
        secret_references=(SecretReference(secret_id="secret-1", purpose="provider-token"),),
    )

    assert request.secret_references[0].secret_id == "secret-1"
