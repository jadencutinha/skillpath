# Security

Two layers, both enforced by Dataverse rather than by the apps:

1. **Security roles** decide which *rows* a user can see and edit.
2. **Column security profiles** decide which *columns* they can write. This is what stops a
   requester from approving their own request.

## 1. Security roles (rows)

Create the roles in **Power Platform admin center → Environments → (your env) → Settings → Users +
permissions → Security roles → + New role**. Base each one on the **Basic User** template, so users
can still sign in and open apps. After creating each role, add it to the **TrainingRequests** solution
with **Add existing → Security → Security role**, so it ships with the solution.

| Role | Training Request | Training Course | Intent |
|---|---|---|---|
| **Training Employee** | Create **User** · Read **User** · Write **User** · Append **User** | Read **Organization** · Append To **Organization** | Employees see and edit only their own requests. They can browse the whole catalog |
| **Training Manager** | Read **Business Unit** | Read **Organization** | Managers see the requests in their business unit. They decide through the approval, not by editing the row, so they need no Write |
| **Training Admin** | Create/Read/Write/Delete/Append/Append To/Assign/Share **Organization** | Same, **Organization** | Admins manage the catalog and fix any request |

A manager who also submits requests holds both Training Employee and Training Manager. Roles are
additive: the user gets the union of the two.

Employees have no Delete. An unwanted draft is withdrawn, not deleted, so every request leaves a
record.

### Why Append / Append To?

Setting the `Course` lookup on a request needs **Append** on Training Request (the row that holds
the lookup) and **Append To** on Training Course (the row being pointed at). Without these
privileges, the canvas form fails with a privilege error that names `prvAppendTo…`.

### What row security does and doesn't cover

Row visibility is enforced by Dataverse for every client that signs in **as the user**: the canvas
app, the model-driven app, the Web API, and Excel. The canvas gallery's owner filter is a
convenience, not the boundary.

It does **not** carry over to Power BI. The dashboard imports data with the refresh account's
access, so the report has its own row-level security roles. See
[`../powerbi/model.md`](../powerbi/model.md#5-row-level-security).

Business Unit scope assumes managers and their reports share a business unit. In a developer
environment everyone sits in the root business unit, so a Manager sees every request. For "only my
reports" visibility in production, turn on **hierarchy security** (Manager hierarchy) instead of
widening the role. The approval itself already goes to the requester's manager regardless of
business unit.

## 2. Column security profiles (columns)

Row-level Write lets an employee change any column on their own request. Without a second layer,
that includes Request Status: one Web API call would mark their own request Approved. Column-level
security closes that.

**First**, enable column security on these Training Request columns (column → **Advanced options →
Enable column security**):

`jc_course`, `jc_requeststatus`, `jc_approver`, `jc_pendingwith`, `jc_approvallink`,
`jc_coursecost`, `jc_submittedon`, `jc_decisiondate`, `jc_decisioncomments`, `jc_completedon`

**Then** create two profiles in **admin center → Settings → Users + permissions → Column security
profiles**, and add both to the solution (**Add existing → Security → Column security profile**).

| Profile | Course | The nine flow-owned columns | Members |
|---|---|---|---|
| **Training - Read Decision Fields** | Read ✅ · Create ✅ · Update ❌ | Read ✅ · Create ❌ · Update ❌ | Everyone who uses either app |
| **Training - Write Decision Fields** | Read ✅ · Create ✅ · Update ✅ | Read ✅ · Create ✅ · Update ✅ | The account that owns the flows' Dataverse connection, and Training Admins |

Notes:

- **Everyone needs the Read profile.** A user with no profile cannot even *read* a secured column;
  their status label would be blank. Assign the profile to a team rather than to individuals. A
  Microsoft Entra **security group team** that contains all portal users is the low-maintenance
  choice.
- **System Administrators bypass column security.** In a single-user developer environment you are
  one, so everything works before you create the profiles. Test with a second, non-admin user
  (below) or you will not see the protection working.
- **The flows run as their connection's account.** That account needs organization-level Read and
  Write on Training Request (the Training Admin role) plus the Write profile. In production, use a
  dedicated service account for the connections instead of a person.
- **Course is create-only for requesters.** They pick it when creating the request and can't change
  it later. This keeps an approved request tied to the course that was approved.
- **Title and Justification stay editable by the owner.** The approval email records what the
  approver saw. Turn on **auditing** for the Training Request table (table → Properties → Advanced
  options → Audit changes to its data) if you need a change history.

### What the requester can still do

The only writable control surface is the **Requested Action** command column, and every command is
checked by a flow against the current status:

| Command | Allowed when status is | Result |
|---|---|---|
| Submit | Draft | Approval starts |
| Withdraw | Draft or Submitted | Withdrawn |
| Complete | Approved | Completed |

Any other combination is cleared and ignored. Only the owner (or an admin) can issue a command,
because only they have Write on the row.

## Testing

Use a second licensed user from your developer tenant (**admin center → Users → + Add user**), with
no System Administrator role.

1. Assign **Training Employee** and the **Read** profile. Sign in as them in a private window.
   - They see only the requests they created.
   - Saving a new draft works and the row shows **Draft**. (The app doesn't send Request Status; the
     server applies the default.)
2. As that user, try to approve your own request from the browser console on any
   `<org>.crm.dynamics.com` page:
   ```js
   fetch("/api/data/v9.2/jc_trainingrequests(<request id>)", {
     method: "PATCH",
     headers: { "Content-Type": "application/json" },
     body: JSON.stringify({ jc_requeststatus: <APPROVED> }),
   }).then(r => r.status)   // expect 403
   ```
   Repeat with `jc_coursecost: 1` and with a different course in `jc_Course@odata.bind`. All three
   must be refused.
3. Add **Training Manager**: they now see all requests in the business unit, and the *Approvals*
   screen appears in the canvas app.
4. Remove the Read profile: the status labels go blank. Put it back.
