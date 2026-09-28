# Canvas app: Training Portal

Create it inside the solution: **TrainingRequests → New → App → Canvas app**, name it
`Training Portal`, and choose the **Tablet** format. Studio saves it into the solution, so
`pac solution unpack --processCanvasApps` later turns it into readable `.pa.yaml` source.

**Data sources:** Training Requests, Training Courses, Users, Security Roles, and the
Training Estimate connector (after Step 7).

> **Choice syntax.** This file writes Request Status values as
> `'Request Status (Training Requests)'.Submitted`. Studio's IntelliSense may show a slightly
> different name. If so, use what it suggests and keep the rest of the formula.

## App

`App.Formulas` uses named formulas, which are evaluated lazily and cached. Prefer this to
`App.OnStart` (`Set(...)`), which blocks app load.

```powerfx
// The signed-in user's Dataverse row. The Users table is keyed by email.
fxMe = LookUp(Users, 'Primary Email' = User().Email);

// Show the Manager Review screen only to managers or admins.
// UX only. Dataverse security roles enforce who can actually read or write which rows.
fxIsManager =
    !IsEmpty(
        Filter(
            fxMe.'Security Roles (systemuserroles_association)',
            Name in ["Training Manager", "Training Admin", "System Administrator"]
        )
    );
```

> The relationship name `'Security Roles (systemuserroles_association)'` is how IntelliSense shows
> the N:N from Users to Security Roles. The check only sees roles assigned directly to the user. It
> does not see roles inherited through a team. That's fine for this project, and worth mentioning
> if asked.

`App.StartScreen`: `scrHome`

Shared header: add a horizontal container at the top of every screen with 3 buttons.
`btnNavHome`, `btnNavCatalog`, and `btnNavManager` call `Navigate(scrHome)`,
`Navigate(scrCatalog)`, and `Navigate(scrManager)`.

```powerfx
// btnNavManager.Visible
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
| `lblStatus` | Text | `Text(ThisItem.'Request Status')` |
| `lblStatus` | Color | see below |
| `lblDecision` | Text | `ThisItem.'Decision Comments'` |
| `btnNewRequest` | OnSelect | `Set(varPreselectCourse, Blank()); NewForm(frmRequest); Navigate(scrNewRequest, ScreenTransition.Cover)` |
| `lblEmpty` | Visible | `IsEmpty(galMyRequests.AllItems)` |
| `lblEmpty` | Text | `"No requests yet. Browse the catalog to get started."` |

```powerfx
// galMyRequests.Items
Sort(
    Filter('Training Requests', 'Created By'.User = fxMe.User),
    'Created On',
    SortOrder.Descending
)
```

> **Changed from the notes:** `Owner.'Primary Email'` doesn't work, because `Owner` is
> polymorphic (it can be a User or a Team), so you can't dot into its columns directly.
> Comparing `'Created By'` by ID is also **delegable**, so it works beyond the 500/2000-row limit.

```powerfx
// lblStatus.Color
Switch(
    ThisItem.'Request Status',
    'Request Status (Training Requests)'.Approved,  Color.Green,
    'Request Status (Training Requests)'.Completed, Color.DarkGreen,
    'Request Status (Training Requests)'.Rejected,  Color.Red,
    'Request Status (Training Requests)'.Error,     Color.DarkRed,
    'Request Status (Training Requests)'.Submitted, Color.Orange,
    Color.Gray
)
```

---

## 2. scrNewRequest: New Request

Add an **Edit form** `frmRequest`:

- DataSource: `'Training Requests'`
- DefaultMode: `FormMode.New`
- Visible fields: **Title, Course, Justification, Approver**
- Also add **Request Status, Submitted On, Course Cost**, and set each of those cards'
  `Visible` to `false`. A form only writes columns that have a card.

Rename the controls inside the cards: `cmbCourse`, `txtJustification`, and `cmbApprover`.

| Control | Property | Formula |
|---|---|---|
| Course card → `cmbCourse` | Items | `Filter('Training Courses', Active = true)` |
| `cmbCourse` | DefaultSelectedItems | `If(IsBlank(varPreselectCourse), Parent.Default, varPreselectCourse)` |
| `cmbCourse` | OnChange | `Select(btnRefreshEstimate)` |
| Approver card → `cmbApprover` | Items | `Sort(Users, 'Full Name')` |
| Justification card | Required | `cmbCourse.Selected.Cost > 1000` |
| Request Status card | Update | `varSubmitStatus` |
| Submitted On card | Update | `If(varSubmitStatus = 'Request Status (Training Requests)'.Submitted, Now(), Blank())` |
| Course Cost card | Update | `cmbCourse.Selected.Cost` |

The `Justification card.Required` row mirrors the server-side business rule in the UI, so the user
sees the requirement before they submit.

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
)
```

```powerfx
// scrNewRequest.OnVisible
Set(varSubmitStatus, 'Request Status (Training Requests)'.Submitted);
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
estimate is informational only, and the flow makes the authoritative call.

### Submit and Save as draft

```powerfx
// btnSubmit.OnSelect
If(
    IsBlank(cmbCourse.Selected),
        Notify("Please select a course.", NotificationType.Error),
    IsBlank(cmbApprover.Selected),
        Notify("Please select an approver.", NotificationType.Error),
    cmbCourse.Selected.Cost > 1000 && IsBlank(Trim(txtJustification.Text)),
        Notify("Justification is required for courses over $1,000.", NotificationType.Error),
    Set(varSubmitStatus, 'Request Status (Training Requests)'.Submitted);
    SubmitForm(frmRequest)
)

// btnSaveDraft.OnSelect
If(
    IsBlank(cmbCourse.Selected),
    Notify("Please select a course.", NotificationType.Error),
    Set(varSubmitStatus, 'Request Status (Training Requests)'.Draft);
    SubmitForm(frmRequest)
)

// frmRequest.OnSuccess
Notify(
    If(
        varSubmitStatus = 'Request Status (Training Requests)'.Submitted,
        "Request submitted! Your approver has been notified.",
        "Draft saved."
    ),
    NotificationType.Success
);
Set(varPreselectCourse, Blank());
Set(varEstimate, Blank());
ResetForm(frmRequest);
Navigate(scrHome, ScreenTransition.Fade)

// frmRequest.OnFailure
Notify("Submission failed: " & frmRequest.Error, NotificationType.Error)

// btnCancel.OnSelect
ResetForm(frmRequest); Back()
```

`If(cond1, result1, cond2, result2, ..., default)` is Power Fx's multi-branch `If`. The client-side
checks give fast feedback. The business rule is still the real enforcement: if you remove the third
check, the save still fails with the rule's message in `OnFailure`.

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

## 4. scrManager: Manager Review

```powerfx
// scrManager.OnVisible  (UX guard. Security itself lives in Dataverse roles.)
If(!fxIsManager, Navigate(scrHome))
```

| Control | Property | Formula |
|---|---|---|
| `galPending` | Items | see below |
| `lblPendingTitle` (in gallery) | Text | `ThisItem.Title & " — " & ThisItem.'Created By'.'Full Name'` |
| `lblPendingDetail` | Text | `ThisItem.Course.Name & "  ·  " & Text(ThisItem.'Course Cost', "$#,##0") & "  ·  submitted " & Text(ThisItem.'Submitted On', "mmm d")` |
| `lblJustification` (detail pane) | Text | `galPending.Selected.Justification` |
| `txtComments` (multiline input) | Default | `""` |
| `btnApprove`, `btnReject` | DisplayMode | `If(IsBlank(galPending.Selected), DisplayMode.Disabled, DisplayMode.Edit)` |

```powerfx
// galPending.Items. Oldest first, so nothing waits forever.
Sort(
    Filter(
        'Training Requests',
        'Request Status' = 'Request Status (Training Requests)'.Submitted,
        Approver.User = fxMe.User
    ),
    'Submitted On',
    SortOrder.Ascending
)
```

```powerfx
// btnApprove.OnSelect
IfError(
    Patch(
        'Training Requests',
        galPending.Selected,
        {
            'Request Status': 'Request Status (Training Requests)'.Approved,
            'Decision Date': Now(),
            'Decision Comments': txtComments.Text
        }
    );
    Notify("Approved", NotificationType.Success);
    Reset(txtComments),
    Notify("Could not approve: " & FirstError.Message, NotificationType.Error)
)

// btnReject.OnSelect. Rejections must say why.
If(
    IsBlank(Trim(txtComments.Text)),
    Notify("Add a comment explaining the rejection.", NotificationType.Warning),
    IfError(
        Patch(
            'Training Requests',
            galPending.Selected,
            {
                'Request Status': 'Request Status (Training Requests)'.Rejected,
                'Decision Date': Now(),
                'Decision Comments': txtComments.Text
            }
        );
        Notify("Rejected", NotificationType.Success);
        Reset(txtComments),
        Notify("Could not reject: " & FirstError.Message, NotificationType.Error)
    )
)
```

### Two approval channels, one source of truth

Managers can decide either in this screen or in Outlook/Teams (the flow's approval). The flow
**re-reads the row** before writing its outcome and skips the update if the status is no longer
`Submitted` (see `flow/approval-flow.md`). A decision made in the app therefore can't be
overwritten when the stale email approval is answered later.

---

## Publish & share

**File → Save → Publish.** Then share the app with your test users. Sharing a canvas app doesn't
grant data access by itself. Users also need one of the three security roles. The share dialog
prompts you to assign roles for the Dataverse tables.
