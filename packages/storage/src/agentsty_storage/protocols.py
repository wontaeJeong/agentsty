from typing import Protocol

from .models import ArtifactRecord, RunRecord, SecretReference


class RunStore(Protocol):
    def create_run(self, record: RunRecord) -> RunRecord: ...

    def get_run(self, run_id: str) -> RunRecord | None: ...


class ArtifactStore(Protocol):
    def put_artifact(self, record: ArtifactRecord) -> ArtifactRecord: ...


class SecretStore(Protocol):
    def get_secret_reference(self, secret_id: str) -> SecretReference | None: ...
