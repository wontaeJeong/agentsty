from agentsty_common.enums import ServiceKind
from agentsty_common.settings import BaseServiceSettings
from pydantic import Field
from pydantic_settings import SettingsConfigDict


class ProxySettings(BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PROXY_",
        env_ignore_empty=True,
        extra="ignore",
    )

    service_kind: ServiceKind = ServiceKind.PROXY
    provider_timeout_seconds: int = Field(default=30)
