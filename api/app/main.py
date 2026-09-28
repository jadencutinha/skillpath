"""Training cost estimate API.

Called by the Power Platform custom connector (see ../../connector) from the
canvas app and the approval flow. One business endpoint, one health check.
"""

import os
from enum import Enum

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel

HIGH_COST_THRESHOLD = 1000.0
PREMIUM_COST_PER_HOUR = 100.0

app = FastAPI(
    title="Training Estimate API",
    version="1.0.0",
    description="Cost-per-hour and budget tier for training requests.",
)


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


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Enforce an API key only when API_KEY is configured on the host."""
    expected = os.getenv("API_KEY")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key header.")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get(
    "/estimate",
    response_model=Estimate,
    operation_id="GetEstimate",
    dependencies=[Depends(require_api_key)],
)
def estimate(
    cost: float = Query(..., ge=0, description="Course cost in USD."),
    hours: int = Query(..., gt=0, description="Course length in hours."),
) -> Estimate:
    cost_per_hour = round(cost / hours, 2)
    high = cost > HIGH_COST_THRESHOLD
    return Estimate(
        cost=cost,
        hours=hours,
        cost_per_hour=cost_per_hour,
        tier=Tier.high if high else Tier.standard,
        premium_rate=cost_per_hour > PREMIUM_COST_PER_HOUR,
        requires_second_approval=high,
    )
