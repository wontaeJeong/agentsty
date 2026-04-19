from agentsty_proxy.main import app
from fastapi.testclient import TestClient


def test_proxy_healthcheck() -> None:
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["service"] == "proxy"
