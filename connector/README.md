# Training Estimate custom connector

FastAPI generates **OpenAPI 3**, but custom connectors expect **OpenAPI 2.0 (Swagger)**. So this
folder contains a hand-written Swagger 2.0 definition that matches `api/app/main.py`. The API's
contract tests (`api/tests/test_connector_contract.py`) fail in CI if the two drift apart.

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

**Option B, wizard.** Solution → **New → Automation → Custom connector** → **Create from blank**,
name it `Training Estimate`. Turn on the **Swagger editor** toggle and paste
`apiDefinition.swagger.json`. That brings in the parameter bounds and all seven response fields
exactly as the tests check them.

Then, on the **Test** tab: create a connection (paste the Render `API_KEY`), run with
`cost=2495, hours=24`, and confirm `tier = high` and `high_cost_threshold = 1000`.

Updating later: after changing the API, edit `apiDefinition.swagger.json` until the contract tests
pass, then `pac connector update` with the same three arguments plus `--connector-id`.

## 3. Point the host at the environment variable

Using the environment variable means test and prod environments can use different API hosts
without editing the connector.

- With Option A, the `dynamichosturl` policy in `apiProperties.json` already does this.
- With Option B, go to **Definition → Policies → New policy**, template **Set host URL**, and set
  URL template to `https://@environmentVariables("jc_EstimateApiHost")`.

Check the **Test** tab again after adding the policy. If your tenant rejects the policy template,
hard-code the host for now and record it under *Known limitations* in the root README.

## 4. Using it

- **Canvas app:** add `Training Estimate` as a data source, then call
  `TrainingEstimate.GetEstimate(cost, hours)`. See `powerapps/canvas-app.md`.
- **Flow:** use the `Get cost estimate` action and read `requires_second_approval`. See
  `flow/approval-flow.md`.

The API key lives in the **connection**, not in the app or the flow. Whoever creates the connection
pastes the key once, and it is not shown again.
