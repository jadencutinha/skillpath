# Build guide

An ordered checklist for the parts that must be built in the Power Platform maker portal. Each step
links to the spec with exact names, formulas, and expressions. Work in this order, because later
steps depend on names created in earlier ones.

## 0. Setup

- [ ] Sign up for the **Power Apps Developer Plan** with a work or school account.
- [ ] Confirm a **Developer** environment exists: [admin.powerplatform.microsoft.com](https://admin.powerplatform.microsoft.com) → Environments.
      Note its URL (`https://<org>.crm.dynamics.com`).
- [ ] Add a **second, non-admin user** to the tenant. Column security and row security can't be
      seen working as a System Administrator, and the approval tests need a requester who isn't
      also the approver.
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
- [ ] Table **Training Request** (primary column = Title): 3 requester columns and 9 flow-owned columns
- [ ] Set the Course relationship's delete behavior to **Restrict**
- [ ] **Enable column security** on Course and on all 9 flow-owned columns
- [ ] Record the **Request Status** and **Requested Action** choice values in the table in `schema.md`
- [ ] Business rule **Require justification over 1000** (scope **Entity**), then Activate
- [ ] Views: Active Courses, Pending Requests, Decided This Month, Needs Attention
- [ ] Seed: `python dataverse/seed_dataverse.py --env <url> --dry-run`, then run it without `--dry-run`

## 3. Security: [`dataverse/security-roles.md`](../dataverse/security-roles.md)

- [ ] Roles: Training Employee, Training Manager, Training Admin
- [ ] Column security profiles: *Training - Read Decision Fields*, *Training - Write Decision Fields*
- [ ] Add all five to the solution (Add existing → Security)
- [ ] Give the test user Training Employee + the Read profile, and set their **Manager**
- [ ] Run the four checks under *Testing*, including the Web API attempt to self-approve (expect 403)

## 4. API and connector

The flows and the canvas app both call the connector, so it comes before them.

- [ ] Deploy the API: [`api/README.md`](../api/README.md) (Render Blueprint). `curl https://<host>/health`
- [ ] Environment variables: `jc_EstimateApiHost`, `jc_DefaultApproverEmail`, `jc_SecondApproverEmail`,
      `jc_AdminEmail`, `jc_EnvironmentUrl`
- [ ] Custom connector: [`connector/README.md`](../connector/README.md), then test in the wizard

## 5. Flows: [`flow/`](../flow)

Requests can't leave Draft until the approval flow exists, so build the flows before the app.

- [ ] [`approval-flow.md`](../flow/approval-flow.md): Training Request Approval
- [ ] [`commands-flow.md`](../flow/commands-flow.md): Training Request Commands
- [ ] [`reminders-flow.md`](../flow/reminders-flow.md): Training Request Reminders
- [ ] Smoke test before the app exists: in the maker portal, open the Training Request table →
      **Edit data**, add a row, and set Requested Action = Submit. The status should change to
      Submitted within seconds, then an approval should arrive.

## 6. Canvas app: [`powerapps/canvas-app.md`](../powerapps/canvas-app.md)

- [ ] App.Formulas (`fxMe`, `fxIsManager`, `fxFallbackThreshold`)
- [ ] scrHome, scrNewRequest, scrCatalog, scrApprovals
- [ ] Save + Publish, share with the test user

## 7. Model-driven app: [`powerapps/model-driven-app.md`](../powerapps/model-driven-app.md)

## 8. End-to-end tests

- [ ] All 11 tests in [`approval-flow.md`](../flow/approval-flow.md#testing-checklist). Screenshot the Catch run.
- [ ] All 5 tests in [`commands-flow.md`](../flow/commands-flow.md#testing-checklist)
- [ ] The reminder test in [`reminders-flow.md`](../flow/reminders-flow.md#testing)
- [ ] Tick the results table in the README

## 9. Power BI: [`powerbi/model.md`](../powerbi/model.md)

- [ ] Parameter, three queries, Date table, four relationships, measures, visuals
- [ ] Row-level security: Hierarchy Path column, two roles, **View as** the test user
- [ ] Performance Analyzer numbers → README
- [ ] Save `powerbi/TrainingRequests.pbix`

## 10. ALM

- [ ] `./scripts/export-solution.sh`. This writes the unpacked solution to `src/`.
- [ ] Browse `src/`: tables in `src/Entities/`, flow JSON in `src/Workflows/`, canvas app source in `src/CanvasApps/`
- [ ] `./scripts/pack-solution.sh` builds the managed zip from that source
- [ ] *(Optional)* Set up the CI/CD service principal (README), add repo secrets, then run the
      **Export solution** workflow from the Actions tab
- [ ] *(Optional)* A second environment as `test`: [`deploy/README.md`](../deploy/README.md), then the
      **Deploy solution** workflow

## 11. Docs

- [ ] Screenshots in `docs/screenshots/`: `demo.gif` (submit → approve in Teams/Outlook → status
      turns green), `dashboard.png`, `flow-catch.png`
- [ ] Uncomment the three image lines in the README
- [ ] Fill the Performance Analyzer table in the README and the choice values in `schema.md`
- [ ] Update the *Project status* table in the README
