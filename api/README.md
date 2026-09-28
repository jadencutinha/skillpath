# Training Estimate API

FastAPI service behind the `Training Estimate` custom connector.

| Method | Path        | Purpose                                              |
|--------|-------------|------------------------------------------------------|
| GET    | `/health`   | Liveness check (used by Render)                      |
| GET    | `/estimate` | `cost` + `hours` → cost per hour, tier, second-approval flag |

```bash
curl "http://localhost:8000/estimate?cost=2495&hours=24" -H "X-API-Key: $API_KEY"
# {"cost":2495.0,"hours":24,"cost_per_hour":103.96,"tier":"high","premium_rate":true,"requires_second_approval":true}
```

Invalid input (`hours=0`, negative cost, missing params) returns **422**. If the `API_KEY`
environment variable is set, requests without a matching `X-API-Key` header return **401**.

## Run locally

```bash
cd api
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
uvicorn app.main:app --reload     # docs at http://localhost:8000/docs
```

## Deploy (Render, free)

`render.yaml` at the repo root is a Render Blueprint. In Render: **New → Blueprint**, pick the
repo, apply. Render generates `API_KEY`. Copy it from the service's **Environment** tab, since the
custom connector needs it. The free tier sleeps after about 15 minutes idle, so the first call can
take around 30 seconds. Call `/health` before a demo to wake it.
