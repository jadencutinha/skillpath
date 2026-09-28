# Training Estimate custom connector

FastAPI generates **OpenAPI 3.0**, but custom connectors expect **OpenAPI 2.0 (Swagger)**. So this
folder contains a hand-written Swagger 2.0 definition that matches `api/app/main.py`.

| File | Purpose |
|------|---------|
| `apiDefinition.swagger.json` | The one action, `GetEstimate` (GET /estimate?cost&hours), plus a hidden `GetHealth` |
| `apiProperties.json` | API-key connection parameter, and a policy that reads the host from the `jc_EstimateApiHost` environment variable |

## 1. Create the environment variable (in the solution)

Solution **TrainingRequests → New → More → Environment variable**

| Field | Value |
|-------|-------|
| Display name | Estimate API Host |
| Schema name | `jc_EstimateApiHost` |
| Data type | Text |
| Current value | `training-estimate-api.onrender.com` (your Render host, without `https://`) |

## 2. Create the connector

**Option A, CLI (fastest).** Run this from the repo root after `pac auth create`:

```bash
pac connector create \
  --api-definition-file connector/apiDefinition.swagger.json \
  --api-properties-file connector/apiProperties.json \
  --solution-unique-name TrainingRequests
```

**Option B, wizard (what the notes describe).** Solution → **New → Automation → Custom connector**
→ **Create from blank**, name it `Training Estimate`.

1. **General:** scheme HTTPS, host = your Render host, base URL `/`.
2. **Security:** API Key, label `API Key`, parameter name `X-API-Key`, location Header.
3. **Definition:** New action, summary `Get cost estimate`, operation ID `GetEstimate`.
   **Request → Import from sample:** GET `https://<host>/estimate?cost=2495&hours=24`.
   **Response → Add default response:** paste the JSON from `curl` (see `api/README.md`).
   Then edit `cost` and `hours` so both are **required**.
4. **Code:** leave off.
5. **Test:** Create connection (paste the Render `API_KEY`), run with `cost=2495, hours=24`, and
   confirm `tier = high`.

Alternatively, turn on the **Swagger editor** toggle and paste `apiDefinition.swagger.json`.

## 3. Point the host at the environment variable

Using the environment variable means test and prod environments can use different API hosts
without editing the connector.

- With Option A, the `dynamichosturl` policy in `apiProperties.json` already does this.
- With Option B, go to **Definition → Policies → New policy**, template **Set host URL**, and set
  URL template to `https://@environmentVariables("jc_EstimateApiHost")`.

Check the **Test** tab again after adding the policy. If your tenant rejects the policy template,
hard-code the host and put the environment-variable approach in the README as a known limitation.

## 4. Using it

- **Canvas app:** add `Training Estimate` as a data source, then call
  `TrainingEstimate.GetEstimate(cost, hours)`. See `powerapps/canvas-app.md`.
- **Flow:** use the `Get cost estimate` action and branch on `tier`. See `flow/approval-flow.md`.
