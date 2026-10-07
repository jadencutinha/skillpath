import pytest


def estimate(client, **params):
    return client.get("/estimate", params=params)


def test_health_needs_no_key(anonymous):
    resp = anonymous.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_standard_tier(client):
    body = estimate(client, cost=450, hours=12).json()
    assert body == {
        "cost": 450.0,
        "hours": 12,
        "cost_per_hour": 37.5,
        "tier": "standard",
        "premium_rate": False,
        "requires_second_approval": False,
        "high_cost_threshold": 1000.0,
    }


def test_high_tier_above_threshold(client):
    body = estimate(client, cost=2495, hours=24).json()
    assert body["cost_per_hour"] == 103.96
    assert body["tier"] == "high"
    assert body["requires_second_approval"] is True
    assert body["premium_rate"] is True


def test_threshold_is_exclusive(client):
    assert estimate(client, cost=1000, hours=10).json()["tier"] == "standard"
    assert estimate(client, cost=1000.01, hours=10).json()["tier"] == "high"


def test_premium_rate_is_independent_of_tier(client):
    # Cheap but short: standard tier, premium hourly rate.
    body = estimate(client, cost=600, hours=2).json()
    assert body["tier"] == "standard"
    assert body["premium_rate"] is True
    # Expensive but long: high tier, ordinary hourly rate.
    body = estimate(client, cost=1450, hours=40).json()
    assert body["tier"] == "high"
    assert body["premium_rate"] is False


def test_free_course(client):
    body = estimate(client, cost=0, hours=2).json()
    assert body["cost_per_hour"] == 0.0
    assert body["tier"] == "standard"


def test_thresholds_come_from_environment(client, monkeypatch):
    monkeypatch.setenv("HIGH_COST_THRESHOLD", "500")
    monkeypatch.setenv("PREMIUM_COST_PER_HOUR", "20")
    body = estimate(client, cost=600, hours=24).json()
    assert body["tier"] == "high"
    assert body["requires_second_approval"] is True
    assert body["premium_rate"] is True
    assert body["high_cost_threshold"] == 500.0


@pytest.mark.parametrize("value", ["abc", "-1", "nan", "inf"])
def test_bad_threshold_configuration_is_an_error_not_a_default(client, monkeypatch, value):
    monkeypatch.setenv("HIGH_COST_THRESHOLD", value)
    with pytest.raises(RuntimeError, match="HIGH_COST_THRESHOLD"):
        estimate(client, cost=100, hours=5)


@pytest.mark.parametrize(
    "params",
    [
        {"cost": 100, "hours": 0},
        {"cost": 100, "hours": -3},
        {"cost": -1, "hours": 5},
        {"cost": 100},
        {"hours": 5},
        {"cost": "abc", "hours": 5},
        {"cost": 100, "hours": 2.5},
        {"cost": "inf", "hours": 5},
        {"cost": "nan", "hours": 5},
        {"cost": 1_000_000.01, "hours": 5},
        {"cost": 100, "hours": 10_001},
    ],
)
def test_invalid_input_returns_422(client, params):
    assert client.get("/estimate", params=params).status_code == 422


def test_upper_bounds_are_inclusive(client):
    assert estimate(client, cost=1_000_000, hours=10_000).status_code == 200


def test_missing_key_is_rejected(anonymous):
    assert estimate(anonymous, cost=100, hours=5).status_code == 401


@pytest.mark.parametrize("key", ["wrong", "test-ke", "test-key ", "", "tést-key"])
def test_wrong_key_is_rejected(anonymous, key):
    resp = anonymous.get("/estimate", params={"cost": 100, "hours": 5}, headers={"X-API-Key": key.encode()})
    assert resp.status_code == 401


def test_key_is_checked_before_parameters(anonymous):
    # An unauthenticated caller learns nothing about parameter validation.
    assert anonymous.get("/estimate", params={"cost": -1}).status_code == 401


@pytest.mark.parametrize("configured", [None, ""])
def test_unconfigured_key_fails_closed(anonymous, monkeypatch, configured):
    if configured is None:
        monkeypatch.delenv("API_KEY")
    else:
        monkeypatch.setenv("API_KEY", configured)
    resp = estimate(anonymous, cost=100, hours=5)
    assert resp.status_code == 503
    # Sending a key doesn't help: there is nothing to match it against.
    resp = anonymous.get("/estimate", params={"cost": 100, "hours": 5}, headers={"X-API-Key": "anything"})
    assert resp.status_code == 503


def test_anonymous_mode_is_explicit_opt_in(anonymous, monkeypatch):
    monkeypatch.delenv("API_KEY")
    monkeypatch.setenv("ALLOW_ANONYMOUS", "true")
    assert estimate(anonymous, cost=100, hours=5).status_code == 200


def test_anonymous_flag_does_not_override_a_configured_key(anonymous, monkeypatch):
    monkeypatch.setenv("ALLOW_ANONYMOUS", "true")
    assert estimate(anonymous, cost=100, hours=5).status_code == 401
