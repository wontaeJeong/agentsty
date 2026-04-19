from agentsty_api.main import app as api_app
from agentsty_proxy.main import app as proxy_app
from fastapi.testclient import TestClient


def create_api_client() -> TestClient:
    return TestClient(api_app)


def create_proxy_client() -> TestClient:
    return TestClient(proxy_app)
