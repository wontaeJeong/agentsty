from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, Field


class OwnershipContext(BaseModel):
    tenant_id: UUID
    user_id: UUID | None = None
    session_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
