# Canvas app: Training Portal

The screens are written out in full as pasteable Power Apps YAML in [`source/`](source), with a
visual preview (`source/preview.html`) and step-by-step paste instructions
([`source/README.md`](source/README.md)). This page explains how the app works and why it is built
the way it is; the formulas themselves live in the source files.

**Data sources:** Training Requests, Training Courses, Users, Security Roles, and the
Training Estimate connector.

## What the app is allowed to write

The app writes four columns on a request and nothing else: **Title, Course, Justification, and
Requested Action**. Status, approver, cost, and dates belong to the flows and are locked with column
security ([`../dataverse/security-roles.md`](../dataverse/security-roles.md)). Two consequences shape
the whole app:

- **The app never sets Request Status.** To submit, withdraw, or complete a request it writes a
  *command* into Requested Action, and a flow applies it a few seconds later. While a command is
  outstanding the app shows *Submitting…* in place of the status.
- **It saves with `Patch`, not an Edit form.** A form sends every card it contains; `Patch` sends
  exactly the columns listed. That keeps locked columns out of every write, and lets the edit path
  leave Course out (it can be set on create only). A test in `source/tests` fails if a `Patch` ever
  names a flow-owned column.

## App-level formulas (`App.Formulas.fx`)

Named formulas, which are evaluated lazily and cached, instead of `App.OnStart`, which blocks app
load.

| Formula | Purpose |
|---|---|
| `fxMe` | The signed-in user's Dataverse row, matched on the Entra object ID (matching on email breaks when sign-in name and primary email differ) |
| `fxIsManager` | Shows the Approvals screen. UX only; Dataverse roles decide who can read what. Sees roles assigned directly to the user, not through a team |
| `fxStatus`, `fxAction` | Shorthand for the two choice columns' values. The only place the enum names appear |
| `fxFallbackThreshold` | Used only while the estimate API is unreachable. The API's `high_cost_threshold` is the source of truth |
| `fxKpiInReview`, `fxKpiApproved`, `fxKpiDrafts`, `fxKpiSpend` | The four numbers at the top of the home screen |
| `fxPendingCount` | Badge on the Approvals nav item |
| `fxHex`, `fxTheme` | The palette, as hex text (for the inline SVG icons) and as colours |
| `fxStatusStyles`, `fxCategoryStyles` | Tag colours per status and per course category. Status rows also carry the step on the progress tracker |
| `fxIcon` | Icon shapes, drawn inline as SVG |

## Screens

Every screen shares a left navigation rail (My requests, Course catalog, Approvals) with the
signed-in user at the bottom.

### scrHome: My requests

- **Summary numbers:** in review, approved, drafts, approved spend.
- **List** of the user's own requests, newest first, with a status-coloured edge and tag. Filter
  chips: All, Active, Approved, Closed. The filter is delegable.
- **Detail panel** for the selected request: a four-step tracker (Created → Submitted → Decision →
  Completed), course, cost, submitted date, who it is waiting on, and decision notes.
- **Actions** follow the status, and are hidden while a command is outstanding so a second tap
  can't queue a conflicting one:

  | Status | Actions |
  |---|---|
  | Draft | Edit draft · Discard |
  | Submitted | Withdraw request |
  | Approved | Mark completed |
  | Rejected, Withdrawn, Expired, Error | Request again (starts a new request for the same course) |

- **A timer polls** every 4 seconds while a command is outstanding and stops when the flow has
  handled it, or after a minute. A row stuck on *Submitting…* past that means a flow is off or
  failing; it then shows in the admin's **Needs Attention** view ([`model-driven-app.md`](model-driven-app.md)).

The requester is the row's **owner**, the same definition the security roles, the flows, and the
dashboard use. `Owner` is polymorphic (a User or a Team), so the list filter compares it to the
user's record. For an employee the filter changes nothing, because Dataverse already returns only
their rows; it matters for managers and admins, who can read more than they own.

### scrCatalog: Course catalog

Search box, category chips, and a three-column grid of course cards. **Request** on a card opens the
new-request screen for that course.

Every predicate in the grid's filter (`=`, `StartsWith`, and a blank check against a variable) is
delegable to Dataverse, so search stays correct on a table with 100k rows. Functions like `Len`,
`Mid`, or `EndsWith` are not; with those, Power Apps would only filter the first 500 rows.

### scrNewRequest: New request / Edit draft

One screen for both. A request always starts from a course, so there is no course dropdown: the
course is shown as a card, with *Change course* while the request is still new.

- **Form:** title (defaults to the course name) and business justification, which is marked required
  when the course costs more than the threshold.
- **Cost and approval panel:** cost, cost per hour, tier, and the approval route the request will
  take: manager, then a second approver for a high-tier course, then the outcome.
- **No approver picker.** The flow sends the approval to the requester's manager; the screen only
  says who that is.
- **Submit for approval** and **Save as draft** share one save formula. The only difference is
  whether the Submit command is included.

The live estimate comes from the custom connector, wrapped in `IfError`. If the API is down (for
example, Render is asleep) the panel falls back to the local threshold and says so, and the form
still works. The estimate shown here is informational: the flow makes its own call when the request
is submitted, and that call decides the routing.

The client-side checks give fast feedback. They are not the enforcement: a client that skips them
and submits an expensive course with no justification is stopped by the business rule when the flow
stamps the cost, and the request ends in Error with the rule's message.

### scrApprovals: Waiting on me

A queue, not a decision form. It lists the requests whose approval is currently assigned to the
signed-in user, oldest first, with an age tag that turns red at five days. **Review and respond**
opens that approval.

`Pending With` is written by the approval flow at the start of each stage, so one filter serves both
the manager and the second approver: a high-cost request moves from one person's queue to the
other's when the first approves.

#### Why there is no Approve button here

A `Patch` from this screen would be a second way to decide a request, next to the approval the flow
has already sent to Outlook and Teams. Two channels writing the same decision cannot be made
consistent:

- a `Patch` skips the second approval that a high-cost course requires,
- the requester is never emailed, because the email is sent by the flow,
- the approval left open in Outlook still has to end somehow, and whatever it ends with competes
  with the decision already on the row.

So there is one channel. **Review and respond** opens the approval the flow created, and the
approver's answer travels the same path whether they got there from this app, from Outlook, or
from Teams. The row itself is read-only to managers.

The seeded Submitted rows have no approval behind them, so their Review button is disabled.

## Publish & share

**File → Save → Publish.** Then share the app with your test users. Sharing a canvas app doesn't
grant data access by itself. Users also need a security role **and** the *Training - Read Decision
Fields* column security profile, or the status column will be blank for them.
