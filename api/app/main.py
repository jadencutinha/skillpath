"""Training cost estimate API.

Called by the Power Platform custom connector (see ../../connector) from the
canvas app and the approval flow. One business endpoint, one health check.

Configuration (environment variables):
    API_KEY                Shared secret the connector sends as X-API-Key. Required.
    ALLOW_ANONYMOUS        Set to "true" to run without API_KEY (local development only).
    HIGH_COST_THRESHOLD    Costs above this are tier "high". Default 1000.
    PREMIUM_COST_PER_HOUR  Cost per hour above this is flagged premium. Default 100.
"""

import os
import secrets
from enum import Enum

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel

DEFAULT_HIGH_COST_THRESHOLD = 1000.0
DEFAULT_PREMIUM_COST_PER_HOUR = 100.0

# Upper bounds keep absurd input out of the arithmetic (and out of approval emails).
MAX_COST = 1_000_000.0
MAX_HOURS = 10_000

app = FastAPI(
    title="Training Estimate API",
    version="1.1.0",
    description="Cost-per-hour and budget tier for training requests.",
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class Tier(str, Enum):
    standard = "standard"
    high = "high"


class Estimate(BaseModel):
    cost: float
    hours: int
    cost_per_hour: float
    tier: Tier
    premium_rate: bool
    requires_second_approval: bool
    high_cost_threshold: float


def _env_number(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be a number, got {raw!r}") from None
    if value < 0 or value != value or value == float("inf"):
        raise RuntimeError(f"{name} must be a finite number >= 0, got {raw!r}")
    return value


def high_cost_threshold() -> float:
    return _env_number("HIGH_COST_THRESHOLD", DEFAULT_HIGH_COST_THRESHOLD)


def premium_cost_per_hour() -> float:
    return _env_number("PREMIUM_COST_PER_HOUR", DEFAULT_PREMIUM_COST_PER_HOUR)


def require_api_key(x_api_key: str | None = Security(api_key_header)) -> None:
    """Reject the request unless it carries the configured API key.

    Fails closed: a host with no API_KEY refuses to serve estimates instead of
    serving them to everyone. ALLOW_ANONYMOUS=true is the explicit opt-out.
    """
    expected = os.getenv("API_KEY")
    if not expected:
        if os.getenv("ALLOW_ANONYMOUS", "").strip().lower() in {"1", "true", "yes"}:
            return
        raise HTTPException(status_code=503, detail="API_KEY is not configured on the server.")
    # compare_digest takes the same time whether the first or the last byte differs.
    if x_api_key is None or not secrets.compare_digest(x_api_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header.")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get(
    "/estimate",
    response_model=Estimate,
    operation_id="GetEstimate",
    summary="Get cost estimate",
    dependencies=[Depends(require_api_key)],
    responses={
        401: {"description": "Invalid or missing API key"},
        503: {"description": "API key not configured on the server"},
    },
)
def estimate(
    cost: float = Query(..., ge=0, le=MAX_COST, allow_inf_nan=False, description="Course cost in USD."),
    hours: int = Query(..., gt=0, le=MAX_HOURS, description="Course length in hours."),
) -> Estimate:
    threshold = high_cost_threshold()
    cost_per_hour = round(cost / hours, 2)
    high = cost > threshold
    return Estimate(
        cost=cost,
        hours=hours,
        cost_per_hour=cost_per_hour,
        tier=Tier.high if high else Tier.standard,
        premium_rate=cost_per_hour > premium_cost_per_hour(),
        requires_second_approval=high,
        high_cost_threshold=threshold,
    )
