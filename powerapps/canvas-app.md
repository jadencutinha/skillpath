# Canvas app: Training Portal

Create it inside the solution: **TrainingRequests → New → App → Canvas app**, name it
`Training Portal`, and choose the **Tablet** format. Studio saves it into the solution, so
`pac solution unpack --processCanvasApps` later turns it into readable `.pa.yaml` source.

**Data sources:** Training Requests, Training Courses, Users, Security Roles, and the
Training Estimate connector.

> **Choice syntax.** This file writes choice values as
> `'Request Status (Training Requests)'.Submitted` and
> `'Requested Action (Training Requests)'.Submit`. Studio's IntelliSense may show a slightly
> different name. If so, use what it suggests and keep the rest of the formula.

## What the app is allowed to write

The app writes four columns on a request and nothing else: **Title, Course, Justification, and
Requested Action**. Status, approver, cost, and dates belong to the flows and are locked with column
security ([`../dataverse/security-roles.md`](../dataverse/security-roles.md)). Two consequences shape
every formula below:

- **The app never sets Request Status.** To submit, withdraw, or complete a request it writes a
  *command* into Requested Action, and a flow applies it a few seconds later. While a command is
  outstanding the app shows *Submitting…* in place of the status.
- **Forms must not contain cards for locked columns.** A card sends its value on save, and Dataverse
  rejects a write to a column the user can't update. The form has exactly four cards.

## App

`App.Formulas` uses named formulas, which are evaluated lazily and cached. Prefer this to
`App.OnStart` (`Set(...)`), which blocks app load.

```powerfx
// The signed-in user's Dataverse row, matched on the Entra object ID.
// (Matching on email breaks when a user's sign-in name and primary email differ.)
fxMe = LookUp(Users, 'Azure AD Object ID' = User().EntraObjectId);

// Show the Approvals screen only to managers or admins.
// UX only. Dataverse security roles enforce who can actually read which rows.
fxIsManager =
    !IsEmpty(
        Filter(
            fxMe.'Security Roles (systemuserroles_association)',
            Name in ["Training Manager", "Training Admin", "System Administrator"]
        )
    );

// Used only while the estimate API is unreachable. The API's high_cost_threshold is the
// source of truth; see "The $1,000 threshold" in dataverse/schema.md.
fxFallbackThreshold = 1000;
```

> The relationship name `'Security Roles (systemuserroles_association)'` is how IntelliSense shows
> the N:N from Users to Security Roles. The check only sees roles assigned directly to the user, not
> roles inherited through a team. Give approvers the Training Manager role directly.

`App.StartScreen`: `scrHome`

Shared header: add a horizontal container at the top of every screen with 3 buttons.
`btnNavHome`, `btnNavCatalog`, and `btnNavApprovals` call `Navigate(scrHome)`,
`Navigate(scrCatalog)`, and `Navigate(scrApprovals)`.

```powerfx
// btnNavApprovals.Visible
fxIsManager
```

---

## 1. scrHome: My Requests

| Control | Property | Formula |
|---|---|---|
| `galMyRequests` (vertical gallery) | Items | see below |
| `lblTitle` (in gallery) | Text | `ThisItem.Title` |
| `lblCourse` | Text | `ThisItem.Course.Name` |
| `lblSubmitted` | Text | `If(IsBlank(ThisItem.'Submitted On'), "Not submitted", "Submitted " & Text(ThisItem.'Submitted On', "mmm d, yyyy"))` |
| `lblStatus` | Text, Color | see below |
| `lblWaiting` | Text | `If(ThisItem.'Request Status' = 'Request Status (Training Requests)'.Submitted && !IsBlank(ThisItem.'Pending With'), "Waiting on " & ThisItem.'Pending With')` |
| `lblDecision` | Text | `ThisItem.'Decision Comments'` |
| `btnNewRequest` | OnSelect | `Set(varPreselectCourse, Blank()); NewForm(frmRequest); Navigate(scrNewRequest, ScreenTransition.Cover)` |
| `icoRefresh` | OnSelect | `Refresh('Training Requests')` |
| `lblEmpty` | Visible | `IsEmpty(galMyRequests.AllItems)` |
| `lblEmpty` | Text | `"No requests yet. Browse the catalog to get started."` |

```powerfx
// galMyRequests.Items
Sort(
    Filter('Training Requests', Owner = fxMe),
    'Created On',
    SortOrder.Descending
)
```

The requester is the row's **owner**, the same definition the security roles, the flows, and the
dashboard use. `Owner` is polymorphic (a User or a Team), so you can't dot into its columns, but you
can compare it to a record. For an employee this filter changes nothing, because Dataverse already
returns only their rows. It matters for managers and admins, who can read more than they own.

```powerfx
// lblStatus.Text. An outstanding command takes priority over the stored status.
Switch(
    ThisItem.'Requested Action',
    'Requested Action (Training Requests)'.Submit,   "Submitting…",
    'Requested Action (Training Requests)'.Withdraw, "Withdrawing…",
    'Requested Action (Training Requests)'.Complete, "Updating…",
    Text(ThisItem.'Request Status')
)

// lblStatus.Color
If(
    !IsBlank(ThisItem.'Requested Action'), Color.Gray,
    Switch(
        ThisItem.'Request Status',
        'Request Status (Training Requests)'.Approved,  Color.Green,
        'Request Status (Training Requests)'.Completed, Color.DarkGreen,
        'Request Status (Training Requests)'.Rejected,  Color.Red,
        'Request Status (Training Requests)'.Error,     Color.DarkRed,
        'Request Status (Training Requests)'.Expired,   Color.DarkOrange,
        'Request Status (Training Requests)'.Submitted, Color.Orange,
        Color.Gray   // Draft, Withdrawn
    )
)
```

### Row actions

Each gallery row shows the one or two actions that make sense for its status. All of them are
hidden while a command is outstanding (`IsBlank(ThisItem.'Requested Action')` in every `Visible`),
so a second tap can't queue a conflicting command.

| Button | Visible when status is | OnSelect |
|---|---|---|
| `btnEdit` | Draft | `Set(varPreselectCourse, Blank()); Set(varEditRequest, ThisItem); EditForm(frmRequest); Navigate(scrNewRequest, ScreenTransition.Cover)` |
| `btnWithdraw` (text: `If(status = Draft, "Discard", "Withdraw")`) | Draft, Submitted | command `Withdraw`, below |
| `btnComplete` (text: `"Mark completed"`) | Approved | command `Complete`, below |
| `btnAgain` (text: `"Request again"`) | Rejected, Withdrawn, Expired, Error | see below |

```powerfx
// btnWithdraw.OnSelect. btnComplete is the same with .Complete and its own messages.
IfError(
    Patch(
        'Training Requests',
        ThisItem,
        { 'Requested Action': 'Requested Action (Training Requests)'.Withdraw }
    );
    Set(varPolling, true),
    Notify("Could not withdraw: " & FirstError.Message, NotificationType.Error)
)

// btnAgain.OnSelect. A finished request can't be reopened, so start a new one for the same course.
// The LookUp returns blank if the course has since been retired from the catalog.
Set(
    varPreselectCourse,
    LookUp('Training Courses', 'Training Course' = ThisItem.Course.'Training Course' && Active = true)
);
NewForm(frmRequest);
Navigate(scrNewRequest, ScreenTransition.Cover)
```

### Picking up the flow's result

A command is applied by a flow, so the new status arrives a few seconds after the tap. A timer
refreshes the gallery until nothing is outstanding, then stops.

| Control | Property | Formula |
|---|---|---|
| `scrHome` | OnVisible | `Refresh('Training Requests')` |
| `tmrPoll` (hidden timer) | Duration | `4000` |
| `tmrPoll` | Start, Repeat | `varPolling` |
| `tmrPoll` | OnTimerEnd | `Refresh('Training Requests'); If(IsEmpty(Filter(galMyRequests.AllItems, !IsBlank('Requested Action'))), Set(varPolling, false))` |

If a row stays on *Submitting…* for more than a minute, a flow is off or failing. That is what the
admin's **Needs Attention** view is for ([`model-driven-app.md`](model-driven-app.md)).

---

## 2. scrNewRequest: New Request / Edit Draft

Add an **Edit form** `frmRequest`:

- DataSource: `'Training Requests'`
- Item: `varEditRequest`
- DefaultMode: `FormMode.New`
- Cards: **Title, Course, Justification, Requested Action**, and no others. Set the Requested
  Action card's `Visible` to `false`. A form only writes columns that have a card, which is exactly
  what's wanted here.

The same form creates a request (`NewForm`, from *New request*, the catalog, or *Request again*) and
edits a saved draft (`EditForm`, from `btnEdit`).

Rename the controls inside the cards: `cmbCourse` and `txtJustification`.

| Control | Property | Formula |
|---|---|---|
| Course card | DisplayMode | `If(frmRequest.Mode = FormMode.New, DisplayMode.Edit, DisplayMode.View)` |
| Course card → `cmbCourse` | Items | `Filter('Training Courses', Active = true)` |
| `cmbCourse` | DefaultSelectedItems | `If(IsBlank(varPreselectCourse), Parent.Default, varPreselectCourse)` |
| `cmbCourse` | OnChange | `Select(btnRefreshEstimate)` |
| Justification card | Required | `cmbCourse.Selected.Cost > varThreshold` |
| Requested Action card | Update | `If(varSubmitIntent, 'Requested Action (Training Requests)'.Submit, Blank())` |
| `lblApprover` | Text | `"Approver: " & Coalesce(fxMe.Manager.'Full Name', "assigned by the training team")` |

- **Course is locked once the draft exists.** Column security lets the requester set Course when
  creating a request but not change it afterwards. To request a different course, discard the draft
  and start a new one. This is what keeps an approved request tied to the course that was approved.
- **There is no approver picker.** The flow sends the approval to the requester's manager.
  `lblApprover` only tells the user who that will be.
- **Justification card.Required** mirrors the server-side business rule in the UI, so the user sees
  the requirement before they submit.

### Cost estimate (custom connector)

`btnRefreshEstimate` is a hidden button (Visible = `false`) that holds the estimate logic. Both
`cmbCourse.OnChange` and `scrNewRequest.OnVisible` call it, so a course preselected from the
catalog also gets an estimate.

```powerfx
// btnRefreshEstimate.OnSelect
If(
    IsBlank(cmbCourse.Selected),
    Set(varEstimate, Blank()),
    IfError(
        Set(
            varEstimate,
            TrainingEstimate.GetEstimate(cmbCourse.Selected.Cost, cmbCourse.Selected.Hours)
        ),
        Set(varEstimate, Blank());
        Notify("Cost estimate is unavailable right now. You can still submit.", NotificationType.Warning)
    )
);
// The API owns the threshold. Fall back to the local constant only when it didn't answer.
Set(varThreshold, Coalesce(varEstimate.high_cost_threshold, fxFallbackThreshold))
```

```powerfx
// scrNewRequest.OnVisible
Set(varSubmitIntent, false);
Set(varThreshold, fxFallbackThreshold);
Select(btnRefreshEstimate)
```

```powerfx
// lblEstimate.Text
If(
    IsBlank(varEstimate),
    "",
    Text(varEstimate.cost_per_hour, "$#,##0.00") & " per hour  ·  " &
    Upper(varEstimate.tier) & " tier" &
    If(varEstimate.requires_second_approval, "  ·  requires a second approval", "")
)

// lblEstimate.Color
If(varEstimate.tier = "high", Color.OrangeRed, Color.DarkGreen)
```

If the API fails (for example, Render is asleep), `IfError` means the form still works. The
estimate shown here is informational. The flow makes its own call when the request is submitted, and
that call decides the routing.

### Submit and Save as draft

```powerfx
// btnSubmit.OnSelect
If(
    IsBlank(cmbCourse.Selected),
        Notify("Please select a course.", NotificationType.Error),
    cmbCourse.Selected.Cost > varThreshold && IsBlank(Trim(txtJustification.Text)),
        Notify(
            "Justification is required for courses over " & Text(varThreshold, "$#,##0") & ".",
            NotificationType.Error
        ),
    Set(varSubmitIntent, true);
    SubmitForm(frmRequest)
)

// btnSaveDraft.OnSelect
If(
    IsBlank(cmbCourse.Selected),
    Notify("Please select a course.", NotificationType.Error),
    Set(varSubmitIntent, false);
    SubmitForm(frmRequest)
)

// frmRequest.OnSuccess
Notify(
    If(varSubmitIntent, "Request sent for approval.", "Draft saved."),
    NotificationType.Success
);
Set(varPolling, varSubmitIntent);
Set(varPreselectCourse, Blank());
Set(varEstimate, Blank());
ResetForm(frmRequest);
Navigate(scrHome, ScreenTransition.Fade)

// frmRequest.OnFailure
Notify("Could not save: " & frmRequest.Error, NotificationType.Error)

// btnCancel.OnSelect
ResetForm(frmRequest); Back()
```

`If(cond1, result1, cond2, result2, ..., default)` is Power Fx's multi-branch `If`. The client-side
checks give fast feedback. They are not the enforcement: a client that skips them and submits an
expensive course with no justification is stopped by the business rule when the flow stamps the
cost, and the request ends in Error with the rule's message.

---

## 3. scrCatalog: Course Catalog

| Control | Property | Formula |
|---|---|---|
| `txtSearch` (text input) | HintText | `"Search courses by name..."` |
| `ddCategory` (dropdown) | Items | `Choices('Category (Training Courses)')` |
| `ddCategory` | AllowEmptySelection | `true` |
| `galCourses` | Items | see below |
| `lblCourseName` (in gallery) | Text | `ThisItem.Name` |
| `lblCourseMeta` | Text | `ThisItem.Provider & "  ·  " & Text(ThisItem.Category) & "  ·  " & ThisItem.Hours & " hrs"` |
| `lblCourseCost` | Text | `Text(ThisItem.Cost, "$#,##0")` |
| `btnRequestCourse` (in gallery) | OnSelect | `Set(varPreselectCourse, ThisItem); NewForm(frmRequest); Navigate(scrNewRequest, ScreenTransition.Cover)` |

```powerfx
// galCourses.Items
Filter(
    'Training Courses',
    Active = true,
    StartsWith(Name, txtSearch.Text),
    IsBlank(ddCategory.Selected) || Category = ddCategory.Selected.Value
)
```

**Delegation:** every predicate here (`=`, `StartsWith`, and a blank check against a
constant) is delegable to Dataverse. The server does the filtering, so search stays correct on a
table with 100k rows. `Search()` and `in` on text columns are also delegable to Dataverse, but
functions like `Len`, `Mid`, or `EndsWith` are not. With those, Power Apps would only filter the first
500 rows (up to 2000 if you raise the limit) and show a blue delegation warning.

---

## 4. scrApprovals: Waiting on me

A queue, not a decision form. It lists the requests whose approval is currently assigned to the
signed-in user and opens that approval.

```powerfx
// scrApprovals.OnVisible  (UX guard. Security itself lives in Dataverse roles.)
If(!fxIsManager, Navigate(scrHome), Refresh('Training Requests'))
```

| Control | Property | Formula |
|---|---|---|
| `galPending` | Items | see below |
| `lblPendingTitle` (in gallery) | Text | `ThisItem.Title` |
| `lblPendingDetail` | Text | `ThisItem.Course.Name & "  ·  " & Text(ThisItem.'Course Cost', "$#,##0") & "  ·  submitted " & Text(ThisItem.'Submitted On', "mmm d")` |
| `lblPendingAge` | Text | `DateDiff(ThisItem.'Submitted On', Now(), TimeUnit.Days) & " days waiting"` |
| `lblJustification` (detail pane) | Text | `galPending.Selected.Justification` |
| `btnReview` | Text | `"Review and respond"` |
| `btnReview` | DisplayMode | `If(IsBlank(galPending.Selected.'Approval Link'), DisplayMode.Disabled, DisplayMode.Edit)` |
| `btnReview` | OnSelect | `Launch(galPending.Selected.'Approval Link')` |
| `icoRefreshPending` | OnSelect | `Refresh('Training Requests')` |

```powerfx
// galPending.Items. Oldest first, so nothing waits forever.
Sort(
    Filter(
        'Training Requests',
        'Request Status' = 'Request Status (Training Requests)'.Submitted,
        'Pending With' = fxMe.'Primary Email'
    ),
    'Submitted On',
    SortOrder.Ascending
)
```

`Pending With` is written by the approval flow at the start of each stage, so this one filter serves
both the manager and the second approver: a high-cost request moves from one person's queue to the
other's when the first approves.

### Why there is no Approve button here

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

---

## Publish & share

**File → Save → Publish.** Then share the app with your test users. Sharing a canvas app doesn't
grant data access by itself. Users also need a security role **and** the *Training - Read Decision
Fields* column security profile, or the status column will be blank for them.
