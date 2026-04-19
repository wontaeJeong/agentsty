from agentsty_common.enums import ServiceKind
from agentsty_common.settings import BaseServiceSettings
from pydantic_settings import SettingsConfigDict


class ApiSettings(BaseServiceSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="API_",
        env_ignore_empty=True,
        extra="ignore",
    )

    service_kind: ServiceKind = ServiceKind.API
