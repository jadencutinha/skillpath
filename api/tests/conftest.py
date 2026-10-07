import pytest
from fastapi.testclient import TestClient

from app.main import app

API_KEY = "test-key"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Every test starts with a configured key and default thresholds."""
    monkeypatch.setenv("API_KEY", API_KEY)
    for name in ("ALLOW_ANONYMOUS", "HIGH_COST_THRESHOLD", "PREMIUM_COST_PER_HOUR"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def client() -> TestClient:
    """Client that sends the valid key."""
    return TestClient(app, headers={"X-API-Key": API_KEY})


@pytest.fixture
def anonymous() -> TestClient:
    """Client that sends no key."""
    return TestClient(app)
