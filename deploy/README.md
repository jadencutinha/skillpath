# Deployment settings

A managed solution carries the *definitions* of its environment variables and connection
references, not their values. Each target environment needs its own values: a different API host,
different approver mailboxes, and connections that exist in that environment. A **deployment
settings file** supplies them at import time, so nobody has to click through the import wizard.

| File | Purpose |
|---|---|
| `settings.sample.json` | Shows the shape. The `LogicalName` and custom `ConnectorId` values are placeholders: the real ones are generated when the solution is first built |
| `settings.<env>.json` | One per target environment (`test`, `prod`). Create with the script below, fill in, commit |

## Create the file for an environment

```bash
./scripts/export-solution.sh                  # once the solution exists in dev
./scripts/create-deployment-settings.sh test  # writes deploy/settings.test.json
```

Then fill in:

- **`EnvironmentVariables[].Value`**: the value for that environment.
- **`ConnectionReferences[].ConnectionId`**: create each connection once in the target environment
  (**make.powerapps.com → Connections → + New connection**), signed in as the service account that
  should own the flows' actions. Open the connection; its ID is the last segment of the URL.

The file contains no secrets. Connection IDs are identifiers, and the estimate API key lives inside
the custom connector's connection, not here. It is safe to commit.

## Use it

```bash
./scripts/pack-solution.sh
pac solution import --path out/pack/TrainingRequests_managed.zip \
  --settings-file deploy/settings.test.json --publish-changes
```

or run the **Deploy solution** workflow, which does the same after a solution-checker pass.

## Two things the import does not carry

Do these once per environment, by hand:

1. **Column security profile membership.** The two profiles are in the solution; who belongs to
   them is not. Add the users' team to *Training - Read Decision Fields* and the flow service
   account to *Training - Write Decision Fields*
   ([`../dataverse/security-roles.md`](../dataverse/security-roles.md)).
2. **Checking the flows are on.** A flow can only run once its connection references resolve. With a
   complete settings file the import normally turns all three on. Confirm it under **Solutions →
   TrainingRequests → Cloud flows**; if one is off, open it, check its connections, and turn it on.
