# Security roles

Create the roles in **Power Platform admin center → Environments → (your env) → Settings → Users +
permissions → Security roles → + New role**. Base each one on the **Basic User** template, so users
can still sign in and open apps. After creating each role, add it to the **TrainingRequests** solution
with **Add existing → Security → Security role**, so it ships with the solution.

| Role | Training Request | Training Course | Intent |
|---|---|---|---|
| **Training Employee** | Create **User** · Read **User** · Write **User** · Append **User** | Read **Organization** · Append To **Organization** | Employees see and edit only their own requests. They can browse the whole catalog |
| **Training Manager** | Read **Business Unit** · Write **Business Unit** · Append **Business Unit** | Read **Organization** · Append To **Organization** | Managers see and decide all requests in their business unit |
| **Training Admin** | Create/Read/Write/Delete/Append/Append To/Assign/Share **Organization** | Same, **Organization** | Admins manage the catalog and fix any request |

### Why Append / Append To?

Setting the `Course` lookup on a request needs **Append** on Training Request (the row that holds
the lookup) and **Append To** on Training Course (the row being pointed at). The same applies to
the `Approver` lookup. Basic User already grants Append To on User. Without these privileges,
the canvas form fails with a privilege error that names `prvAppendTo…`.

### Why this matters (interview point)

Row-level visibility is enforced by **Dataverse**, not by the app. The canvas gallery's
`Filter(... 'Created By' ...)` is only a UX convenience. If someone opened the table directly
through the Web API, Excel, or Power BI with an Employee role, they still could not read other
people's requests. The app never needs to be "the" security boundary.

Also note:

- Security is **additive**. A user with both Employee and Manager roles gets the union of the two
  (Business Unit read).
- Business Unit scope assumes managers and their reports share a BU. In a dev environment,
  everyone sits in the root BU, so a Manager sees every request. For true "only my direct reports"
  visibility, you would use a manager **hierarchy security** model or teams. That's a good
  follow-up answer if asked.
- Approvals themselves run under the **flow owner's** connection, so the flow can update any
  request no matter which role the approver has.

## Testing roles

1. In the admin center, **Users → + Add user**. Add a second licensed user from your dev tenant, or
   create one in the Microsoft 365 admin center for the dev tenant.
2. Assign that user **Training Employee** only. Sign in as them in a private window: they see only
   the requests they created.
3. Swap to **Training Manager**: they see all BU requests, and the Manager Review screen appears.
