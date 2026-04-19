from agentsty_api.main import app
from fastapi.testclient import TestClient


def test_api_healthcheck() -> None:
    client = TestClient(app)

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["service"] == "api"
