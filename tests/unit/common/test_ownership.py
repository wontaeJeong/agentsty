from uuid import uuid4

from agentsty_common.ownership import OwnershipContext


def test_ownership_context_requires_tenant_id() -> None:
    ownership = OwnershipContext(tenant_id=uuid4(), user_id=uuid4())

    assert ownership.tenant_id
    assert ownership.user_id
