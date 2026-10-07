# Training Estimate API

FastAPI service behind the `Training Estimate` custom connector.

| Method | Path        | Purpose                                              |
|--------|-------------|------------------------------------------------------|
| GET    | `/health`   | Liveness check (used by Render). No key required     |
| GET    | `/estimate` | `cost` + `hours` → cost per hour, tier, second-approval flag |

```bash
curl "http://localhost:8000/estimate?cost=2495&hours=24" -H "X-API-Key: $API_KEY"
# {"cost":2495.0,"hours":24,"cost_per_hour":103.96,"tier":"high","premium_rate":true,
#  "requires_second_approval":true,"high_cost_threshold":1000.0}
```

| Status | When |
|---|---|
| 200 | Estimate returned |
| 401 | `X-API-Key` missing or wrong |
| 422 | Invalid input: missing parameter, `hours` not a whole number in 1–10,000, `cost` outside 0–1,000,000 |
| 503 | The server has no `API_KEY` configured |

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `API_KEY` | *(none)* | Shared secret the connector sends as `X-API-Key`. **Required.** Without it `/estimate` answers 503 rather than serving everyone |
| `ALLOW_ANONYMOUS` | `false` | Set to `true` to run without a key. Local development only. Ignored when `API_KEY` is set |
| `HIGH_COST_THRESHOLD` | `1000` | Costs **above** this are tier `high` and need a second approval. Returned as `high_cost_threshold` so the canvas app shows the same number |
| `PREMIUM_COST_PER_HOUR` | `100` | Cost per hour above this sets `premium_rate` |

`HIGH_COST_THRESHOLD` is the source of truth for the threshold. The Dataverse business rule keeps a
hand-maintained copy; see "The $1,000 threshold" in
[`../dataverse/schema.md`](../dataverse/schema.md#the-1000-threshold) before changing it.

## Run locally

```bash
cd api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
ruff check . && ruff format --check .
ALLOW_ANONYMOUS=true uvicorn app.main:app --reload     # docs at http://localhost:8000/docs
```

## Tests

- `tests/test_main.py`: tiers, thresholds, input bounds, and every authentication path.
- `tests/test_connector_contract.py`: compares
  [`../connector/apiDefinition.swagger.json`](../connector/apiDefinition.swagger.json) with the
  OpenAPI document this app generates: paths, operation IDs, parameters and their bounds, response
  fields, status codes, and the key header. The Swagger file is written by hand because custom
  connectors don't accept OpenAPI 3, so this is what keeps the two from drifting apart. If you
  change the API and this fails, update the Swagger file and re-import the connector.

## Deploy (Render, free)

`render.yaml` at the repo root is a Render Blueprint. In Render: **New → Blueprint**, pick the
repo, apply. Render generates `API_KEY`. Copy it from the service's **Environment** tab, since the
custom connector needs it. The free tier sleeps after about 15 minutes idle, so the first call can
take around 30 seconds. Call `/health` before a demo to wake it.
