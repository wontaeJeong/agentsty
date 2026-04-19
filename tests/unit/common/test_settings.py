from agentsty_api.settings import ApiSettings
from agentsty_common.enums import ServiceKind
from agentsty_proxy.settings import ProxySettings


def test_api_settings_defaults() -> None:
    settings = ApiSettings()

    assert settings.service_kind is ServiceKind.API


def test_proxy_settings_defaults() -> None:
    settings = ProxySettings()

    assert settings.service_kind is ServiceKind.PROXY
