from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTSTY_", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    default_timeout_seconds: int = 30
    default_runtime: str = "opencode"
    sandbox_mode: str = "stub"
    internal_llm_proxy_base_url: str = "https://internal-llm-proxy.example.local"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
