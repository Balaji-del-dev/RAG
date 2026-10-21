import pytest

from apps.core import health


@pytest.fixture
def services_up(monkeypatch):
    for name in health.CHECKS:
        monkeypatch.setitem(health.CHECKS, name, lambda: True)


def test_health_is_200_when_every_service_is_up(client, services_up):
    response = client.get("/api/v1/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "services": dict.fromkeys(health.CHECKS, "up")}


def test_health_is_503_and_names_the_service_that_is_down(client, services_up, monkeypatch):
    def broken():
        raise ConnectionError("refused")

    monkeypatch.setitem(health.CHECKS, "qdrant", broken)
    monkeypatch.setitem(health.CHECKS, "opensearch", lambda: False)
    response = client.get("/api/v1/health/")
    assert response.status_code == 503
    services = response.json()["services"]
    assert services["qdrant"] == "down" and services["opensearch"] == "down" and services["postgres"] == "up"


def test_health_needs_no_sign_in(client, services_up):
    assert client.get("/api/v1/health/").status_code == 200
