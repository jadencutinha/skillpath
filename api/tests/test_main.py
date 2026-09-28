import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_standard_tier():
    body = client.get("/estimate", params={"cost": 450, "hours": 12}).json()
    assert body["cost_per_hour"] == 37.5
    assert body["tier"] == "standard"
    assert body["requires_second_approval"] is False


def test_high_tier_above_threshold():
    body = client.get("/estimate", params={"cost": 2495, "hours": 24}).json()
    assert body["tier"] == "high"
    assert body["requires_second_approval"] is True
    assert body["premium_rate"] is True


def test_threshold_is_exclusive():
    assert client.get("/estimate", params={"cost": 1000, "hours": 10}).json()["tier"] == "standard"


@pytest.mark.parametrize(
    "params",
    [
        {"cost": 100, "hours": 0},
        {"cost": -1, "hours": 5},
        {"cost": 100},
        {"cost": "abc", "hours": 5},
    ],
)
def test_invalid_input_returns_422(params):
    assert client.get("/estimate", params=params).status_code == 422


def test_api_key_enforced_when_configured(monkeypatch):
    monkeypatch.setenv("API_KEY", "secret")
    params = {"cost": 100, "hours": 5}
    assert client.get("/estimate", params=params).status_code == 401
    ok = client.get("/estimate", params=params, headers={"X-API-Key": "secret"})
    assert ok.status_code == 200
