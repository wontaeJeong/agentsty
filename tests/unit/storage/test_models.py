from uuid import uuid4

from agentsty_common.ownership import OwnershipContext
from agentsty_storage.models import ArtifactRecord, RunRecord


def test_run_record_includes_ownership() -> None:
    record = RunRecord(
        run_id="run-1",
        ownership=OwnershipContext(tenant_id=uuid4()),
        agent_backend="stub-agent",
        sandbox_backend="local-stub",
    )

    assert record.ownership.tenant_id


def test_artifact_record_includes_ownership() -> None:
    record = ArtifactRecord(
        artifact_id="artifact-1",
        run_id="run-1",
        ownership=OwnershipContext(tenant_id=uuid4()),
    )

    assert record.ownership.tenant_id
