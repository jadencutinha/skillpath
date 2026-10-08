# Training Portal: canvas app source

The four screens of the canvas app, written as Power Apps YAML so they can be pasted into Power
Apps Studio instead of being built control by control.

| File | What it is |
|---|---|
| `preview.html` | A static picture of the design with sample data. Open it in a browser to see what you are about to build |
| `App.Formulas.fx` | Named formulas: who is signed in, the colour theme, status colours, icons, the home-screen numbers |
| `scrHome.pa.yaml` | My requests: summary numbers, filterable list, detail panel with a progress tracker and the actions valid for that request |
| `scrCatalog.pa.yaml` | Course catalog: search, category filter, card grid |
| `scrNewRequest.pa.yaml` | New request / edit draft: the form, plus live cost and approval route |
| `scrApprovals.pa.yaml` | Waiting on me: the approvals assigned to the signed-in user |
| `generate.py` | Produces all of the above. Change the design here, then re-run it |
| `tests/` | Checks that need no Power Platform: valid YAML, no dangling references, no overlapping controls |

```bash
python powerapps/source/generate.py                 # rewrite the files above
cd powerapps/source && pip install -r requirements-dev.txt && pytest
```

**Status: not yet pasted into Studio.** The control types, variants, and property names are taken
from real Studio exports, and the tests pass, but that is not the same as Studio accepting every
line. Expect to fix a handful of formula errors on first paste; the section at the end lists the
likeliest ones.

## Before you start

The app reads and writes Dataverse, so the tables must exist first. From a standing start, do
steps 0 to 3 of [`../../docs/BUILD_GUIDE.md`](../../docs/BUILD_GUIDE.md):

1. Sign up for the Power Apps Developer Plan and note your environment URL.
2. Create the solution, tables, and columns in one go:
   `python dataverse/create_schema.py --env https://<org>.crm.dynamics.com`
   (or by hand from [`../../dataverse/schema.md`](../../dataverse/schema.md)).
3. Load the seed data: `python dataverse/seed_dataverse.py --env https://<org>.crm.dynamics.com`
4. Create the security roles.

That is enough to see every screen filled with data. **Submitting** a request also needs the
approval flow (build guide step 5); until it exists, a submitted request stays on *Submitting…*.

## Build the app

1. **Create it.** In the solution: **New → App → Canvas app**, name `Training Portal`, format
   **Tablet**. Leave **Settings → Display → Scale to fit** on. The layout is drawn for 1366 × 768.
2. **Add the data sources** (Data pane → Add data): *Training Requests*, *Training Courses*,
   *Users*, *Security Roles*, and, once it exists, the *Training Estimate* connector.
3. **Paste the named formulas.** Select **App** in the Tree view, choose the **Formulas** property,
   and paste the whole of `App.Formulas.fx`. Set **StartScreen** to `scrHome`.
4. **Paste each screen.** Open a `.pa.yaml` file, copy all of it, then in the Tree view right-click
   an existing screen and choose **Paste code**. A new screen appears with the right name. Do all
   four, then delete the empty `Screen1`.
   - Screens refer to each other (`Navigate(scrCatalog)`), so red error marks are normal until all
     four are in.
   - If Studio will not create a screen from the paste: add a blank screen, rename it to match the
     file, copy the file from the first `- conSidebar…` line to the end, and paste that onto the
     screen. Then set the screen's `Fill` and `OnVisible` from the `Properties` block at the top of
     the file.
5. **Save, then Publish.** Share the app with your test user, who also needs a security role and
   the *Training - Read Decision Fields* column security profile.

## If Studio shows errors after pasting

| Symptom | Likely cause | Fix |
|---|---|---|
| Errors on `fxStatus` or `fxAction` | Studio names your choice columns' enums differently | Type `'Request Status` in the formula bar and let IntelliSense complete the real name. Change it in `fxStatus` and `fxAction` only: every screen goes through those two records |
| `'Azure AD Object ID'` not recognised | The Users column has a different display name in your environment | Replace it in `fxMe` with the name IntelliSense offers for the Entra object ID column |
| `TrainingEstimate` not recognised | The custom connector isn't added yet | Add it as a data source. Until then only the live estimate is missing: the cost, the hourly rate, and the approval route still show, using the fallback threshold |
| `Owner = fxMe` flagged | Comparing the polymorphic Owner column to a record isn't accepted | Replace with `AsType(Owner, Users).User = fxMe.User` |
| A blue delegation warning on the home screen numbers | `CountRows` / `Sum` over a filter on Owner isn't delegated | Safe to ignore: one person's requests are far below the 500-row limit |
| A control looks unstyled or misplaced | A property name wasn't accepted, so the theme default applied | Select the control, find the property with the red mark, and report or fix it in `generate.py` |

After the app works, export the solution (`scripts/export-solution.sh`). From then on the source of
truth is the unpacked app in `src/`, and this folder is the record of how it was first built.

## Design notes

- **One palette.** Every colour comes from `fxTheme`. To rebrand, change the hex values in
  `fxHex` (or `HEX` in `generate.py`) and nothing else.
- **No image files.** Icons are inline SVG built from `fxIcon`, so the app has nothing to upload
  and icons stay sharp at any zoom.
- **Explicit styling.** Each control sets its own fill, text, border, and hover colours. A pasted
  control that leaves one out picks up the app theme's default, which is how stray blue buttons
  appear.
- **No reliance on z-order.** Sibling controls never overlap, so the order Studio assigns when
  pasting can't hide one behind another. The tests enforce this.
- **Status tags are view-mode buttons**, because labels can't have rounded corners.
- **The app writes four columns** (Title, Course, Justification, Requested Action) with `Patch`,
  never a form. A form would send every card on save; `Patch` sends exactly what is listed, which
  is what column security requires. Course is written on create and left out on edit.
