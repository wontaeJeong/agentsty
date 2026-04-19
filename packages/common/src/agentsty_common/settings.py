from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .enums import ServiceKind


class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    app_name: str = Field(default="agentsty")
    environment: str = Field(default="development")
    version: str = Field(default="0.1.0")
    service_kind: ServiceKind
