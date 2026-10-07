# Model-driven app: Training Admin

**TrainingRequests → New → App → Model-driven app**, name `Training Admin`.

## Navigation (site map)

| Group | Page | Table | Default view |
|---|---|---|---|
| Catalog | Courses | Training Course | **Active Courses** |
| Requests | Requests | Training Request | **Pending Requests** |
| Requests | Needs attention | Training Request | **Needs Attention** |

Include these views in the app for each table (under each table's **Views** in the app designer):

- Training Course: *Active Courses*, *Active Training Courses* (system default), *Inactive Training Courses*
- Training Request: *Pending Requests*, *Needs Attention*, *Decided This Month*, *Active Training Requests*

View definitions are in `dataverse/schema.md`.

## Forms

**Training Course → Main form:**
- General section: Name, Provider, Category, Cost, Hours, Active
- A second section with a **subgrid** of related Training Requests (relationship
  `jc_trainingcourse_jc_trainingrequest`). Admins can see demand per course.

**Training Request → Main form:**
- Request section: Title, Course, Justification, Owner
- Approval section: Request Status, Requested Action, Approver, Pending With, Approval Link,
  Course Cost
- Timeline section: Submitted On, Decision Date, Completed On, Decision Comments

The Justification business rule runs here too. Clear Justification on a request whose Course Cost
is 2495 and the form shows the error.

## What admins use it for

The approval columns are locked for everyone else. Training Admins hold the *Training - Write
Decision Fields* column security profile, so this form is where exceptions are handled:

| Situation | What to do |
|---|---|
| A request is in **Error** | Read Decision Comments for the reason. Fix the cause (a missing manager, a retired course, the API host), then ask the requester to use **Request again**, or set the status yourself if the decision is already known |
| A row sits on *Submitting…* in the canvas app | It is in **Needs Attention** with Requested Action still set. A flow is off or failing early: check the flow's run history, then clear Requested Action and set it again to re-run the command |
| An approver is unavailable | Set Request Status to Approved or Rejected here and note why in Decision Comments. The approval flow re-reads the row before writing, sees it is no longer Submitted, and leaves your decision in place |

Don't move a finished request back to Draft to "reopen" it. An approval from its first submission
may still be open, and a late answer to that one would be recorded against the new submission.
Start a new request instead.

## Security

In the app's **Share** dialog, give access to **Training Admin** only. Model-driven apps are
role-gated: a user without an assigned role doesn't see the app at all. The canvas app, by contrast,
is shared per user.

**Save → Publish.**

## Why both app types?

| | Canvas | Model-driven |
|---|---|---|
| Built from | Screens you design pixel-by-pixel | The data model (tables, forms, views) |
| Best for | Task-focused UX for employees and approvers | Data-dense back-office admin |
| Effort here | Hours | ~30 minutes |
| Responsive/accessible | You design it | Built-in |
