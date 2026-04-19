from enum import StrEnum


class ServiceKind(StrEnum):
    API = "api"
    PROXY = "proxy"


class RunStatus(StrEnum):
    QUEUED = "queued"
    ADMITTED = "admitted"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED_POLICY = "failed_policy"
    FAILED_RUNTIME = "failed_runtime"
    TIMED_OUT = "timed_out"
    COMPLETED = "completed"


class JobStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
