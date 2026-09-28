# Model-driven app: Training Admin

**TrainingRequests → New → App → Model-driven app**, name `Training Admin`.

## Navigation (site map)

| Group | Page | Table | Default view |
|---|---|---|---|
| Catalog | Courses | Training Course | **Active Courses** |
| Requests | Requests | Training Request | **Pending Requests** |

Include these views in the app for each table (under each table's **Views** in the app designer):

- Training Course: *Active Courses*, *Active Training Courses* (system default), *Inactive Training Courses*
- Training Request: *Pending Requests*, *Decided This Month*, *Active Training Requests*

View definitions are in `dataverse/schema.md`.

## Forms

**Training Course → Main form:**
- General section: Name, Provider, Category, Cost, Hours, Active
- A second section with a **subgrid** of related Training Requests (relationship
  `jc_trainingcourse_jc_trainingrequest`). Admins can see demand per course.

**Training Request → Main form:**
- Request section: Title, Course, Course Cost, Justification, Approver, Owner
- Decision section: Request Status, Submitted On, Decision Date, Decision Comments

The Justification business rule runs here too. Clear Justification on a request whose Course Cost
is 2495 and the form shows the error.

## Security

In the app's **Share** dialog, give access to **Training Admin** only. Model-driven apps are
role-gated: a user without an assigned role doesn't see the app at all. The canvas app, by contrast,
is shared per user.

**Save → Publish.**

## Why both app types? (interview point)

| | Canvas | Model-driven |
|---|---|---|
| Built from | Screens you design pixel-by-pixel | The data model (tables, forms, views) |
| Best for | Task-focused UX for employees and managers | Data-dense back-office admin |
| Effort here | Hours | ~30 minutes |
| Responsive/accessible | You design it | Built-in |
