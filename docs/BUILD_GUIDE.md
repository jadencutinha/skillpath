# Build guide

An ordered checklist for the parts that must be built in the Power Platform maker portal. Each step
links to the spec with exact names, formulas, and expressions. Work in this order, because later
steps depend on names created in earlier ones.

## 0. Setup

- [ ] Sign up for the **Power Apps Developer Plan** with your **Princeton** (work/school) account.
- [ ] Confirm a **Developer** environment exists: [admin.powerplatform.microsoft.com](https://admin.powerplatform.microsoft.com) → Environments.
      Note its URL (`https://<org>.crm.dynamics.com`).
- [ ] Install **VS Code** + **Power Platform Tools** extension. It bundles `pac`. Check with `pac help`.
      On macOS without the extension: install the .NET 8 SDK, then run `dotnet tool install --global Microsoft.PowerApps.CLI.Tool`.
- [ ] Power BI Desktop: Windows VM or Cloud PC (see `powerbi/model.md`).
- [ ] `pac auth create --environment https://<org>.crm.dynamics.com`

## 1. Solution

- [ ] make.powerapps.com → select your dev environment → **Solutions → New solution**
  - Display name `Training Requests`, name **`TrainingRequests`**
  - Publisher → **+ New publisher**: display `Jaden Cutinha`, name `jadencutinha`, prefix **`jc`**.
    Note the generated **choice value prefix**.
- [ ] From now on, create **everything** from inside this solution.

## 2. Data model: [`dataverse/schema.md`](../dataverse/schema.md)

- [ ] Table **Training Course** + 5 columns
- [ ] Table **Training Request** (primary column = Title) + 8 columns, including the extra **Course Cost**
- [ ] Set the Course relationship's delete behavior to **Restrict**
- [ ] Record the **Request Status** choice values in the table in `schema.md`
- [ ] Business rule **Require justification over 1000** (scope **Entity**), then Activate
- [ ] Views: Active Courses, Pending Requests, Decided This Month
- [ ] Seed: `python dataverse/seed_dataverse.py --env <url> --dry-run`, then run it without `--dry-run`

## 3. Security roles: [`dataverse/security-roles.md`](../dataverse/security-roles.md)

- [ ] Training Employee, Training Manager, Training Admin
- [ ] Add all three to the solution (Add existing → Security role)

## 4. Canvas app: [`powerapps/canvas-app.md`](../powerapps/canvas-app.md)

- [ ] App.Formulas (`fxMe`, `fxIsManager`)
- [ ] scrHome, scrNewRequest, scrCatalog, scrManager
- [ ] Save + Publish

## 5. Model-driven app: [`powerapps/model-driven-app.md`](../powerapps/model-driven-app.md)

## 6–7. API, connector, flow

The flow uses the connector, so build Step 7's API and connector **before** the flow.

- [ ] Deploy the API: [`api/README.md`](../api/README.md) (Render Blueprint). `curl https://<host>/health`
- [ ] Environment variables: `jc_EstimateApiHost`, `jc_SecondApproverEmail`, `jc_AdminEmail`, `jc_EnvironmentUrl`
- [ ] Custom connector: [`connector/README.md`](../connector/README.md), then test in the wizard
- [ ] Add the connector to the canvas app (the estimate label)
- [ ] Flow: [`flow/approval-flow.md`](../flow/approval-flow.md)
- [ ] Run all 7 tests in the flow's testing checklist. Screenshot the Catch run.

## 8. Power BI: [`powerbi/model.md`](../powerbi/model.md)

- [ ] Queries, Date table, relationships, measures, visuals
- [ ] Performance Analyzer numbers → README
- [ ] Save `powerbi/TrainingRequests.pbix`

## 9. ALM

- [ ] `./scripts/export-solution.sh`. This writes the unpacked solution to `src/`.
- [ ] Browse `src/`: tables in `src/Entities/`, flow JSON in `src/Workflows/`, canvas app source in `src/CanvasApps/`
- [ ] *(Extra credit)* Set up the CI/CD service principal (README), add repo secrets, then run the
      **Export solution** workflow from the Actions tab

## 10. Docs

- [ ] Screenshots in `docs/screenshots/` (see list in README)
- [ ] Demo GIF: submit → approve in Teams/Outlook → status turns green
- [ ] Fill the Performance Analyzer table and the choice values in the README
