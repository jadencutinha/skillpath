"""Load seed courses and requests into Dataverse through the Web API.

Usage:
    pip install -r dataverse/requirements.txt
    python dataverse/seed_dataverse.py --check                                  # validate the CSVs only
    python dataverse/seed_dataverse.py --env https://<org>.crm.dynamics.com --dry-run
    python dataverse/seed_dataverse.py --env https://<org>.crm.dynamics.com
    python dataverse/seed_dataverse.py --env https://<org>.crm.dynamics.com --reset

Sign-in uses the device-code flow with Microsoft's public sample client ID,
so you don't need an app registration. Sign in with your developer environment account.

Choice values, entity set names, and lookup navigation properties are all read
from metadata. The script does not depend on the option values your publisher
prefix generated.

The script is safe to re-run: courses and requests that already exist (matched
by name / title) are left alone. --reset deletes only the rows this script
seeds, never rows people created in the apps.

Seeding writes the flow-owned columns (status, dates, approver) directly, so the
account you sign in with needs System Administrator or the "Training - Write
Decision Fields" column security profile. It does not set Requested Action, so
it never starts an approval.
"""

import argparse
import csv
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import msal
import requests

# Logical names from dataverse/schema.md. If you named anything differently, change it here.
COURSE_TABLE = "jc_trainingcourse"
REQUEST_TABLE = "jc_trainingrequest"
C = {
    "name": "jc_name",
    "provider": "jc_provider",
    "category": "jc_category",
    "cost": "jc_cost",
    "hours": "jc_hours",
    "active": "jc_active",
}
R = {
    "title": "jc_title",
    "course": "jc_course",
    "justification": "jc_justification",
    "status": "jc_requeststatus",
    "action": "jc_requestedaction",
    "approver": "jc_approver",
    "pending_with": "jc_pendingwith",
    "submitted_on": "jc_submittedon",
    "decision_date": "jc_decisiondate",
    "decision_comments": "jc_decisioncomments",
    "completed_on": "jc_completedon",
    "course_cost": "jc_coursecost",
}

CATEGORIES = {"Technical", "Leadership", "Compliance", "Professional Development"}
STATUSES = {"Draft", "Submitted", "Approved", "Rejected", "Completed", "Withdrawn", "Expired", "Error"}
ACTIONS = {"Submit", "Withdraw", "Complete"}
DECIDED = {"Approved", "Rejected", "Completed"}
# Keep in step with the business rule in schema.md: justification is required above this cost.
JUSTIFICATION_THRESHOLD = 1000.0

SAMPLE_CLIENT_ID = "51f81489-12ee-4a9e-aaae-a2591f45987d"
SEED_DIR = Path(__file__).parent / "seed"


class Dataverse:
    def __init__(self, env_url: str):
        self.env = env_url.rstrip("/")
        self.api = f"{self.env}/api/data/v9.2"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self._token()}",
                "OData-MaxVersion": "4.0",
                "OData-Version": "4.0",
                "Accept": "application/json",
                "Content-Type": "application/json; charset=utf-8",
            }
        )

    def _token(self) -> str:
        app = msal.PublicClientApplication(
            SAMPLE_CLIENT_ID, authority="https://login.microsoftonline.com/organizations"
        )
        flow = app.initiate_device_flow(scopes=[f"{self.env}/user_impersonation"])
        if "user_code" not in flow:
            sys.exit(f"Could not start device flow: {flow}")
        print(flow["message"], flush=True)
        result = app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            sys.exit(f"Sign-in failed: {result.get('error_description', result)}")
        return result["access_token"]

    def request(self, method: str, url: str, **kwargs) -> requests.Response:
        if not url.startswith("https://"):
            url = f"{self.api}/{url}"
        resp = self.session.request(method, url, timeout=60, **kwargs)
        if not resp.ok:
            raise RuntimeError(f"{method} {url} -> {resp.status_code}: {resp.text[:500]}")
        return resp

    def get(self, path: str) -> dict:
        return self.request("GET", path).json()

    def get_all(self, path: str) -> list[dict]:
        """GET a collection, following @odata.nextLink until every page is read."""
        rows: list[dict] = []
        url: str | None = path
        while url:
            page = self.get(url)
            rows.extend(page["value"])
            url = page.get("@odata.nextLink")
        return rows

    def entity_set(self, table: str) -> str:
        return self.get(f"EntityDefinitions(LogicalName='{table}')?$select=EntitySetName")["EntitySetName"]

    def primary_id(self, table: str) -> str:
        return self.get(f"EntityDefinitions(LogicalName='{table}')?$select=PrimaryIdAttribute")["PrimaryIdAttribute"]

    def choice_values(self, table: str, column: str) -> dict[str, int]:
        data = self.get(
            f"EntityDefinitions(LogicalName='{table}')/Attributes(LogicalName='{column}')"
            "/Microsoft.Dynamics.CRM.PicklistAttributeMetadata"
            "?$select=LogicalName&$expand=OptionSet($select=Options)"
        )
        return {opt["Label"]["UserLocalizedLabel"]["Label"]: opt["Value"] for opt in data["OptionSet"]["Options"]}

    def nav_property(self, table: str, lookup_column: str) -> str:
        rels = self.get(
            f"EntityDefinitions(LogicalName='{table}')/ManyToOneRelationships"
            "?$select=ReferencingAttribute,ReferencingEntityNavigationPropertyName"
        )["value"]
        for rel in rels:
            if rel["ReferencingAttribute"] == lookup_column:
                return rel["ReferencingEntityNavigationPropertyName"]
        raise RuntimeError(f"No lookup relationship found for {table}.{lookup_column}")

    def ids_by_name(self, entity_set: str, id_column: str, name_column: str) -> dict[str, list[str]]:
        """Map each row's name to the IDs that carry it (names aren't unique in Dataverse)."""
        found: dict[str, list[str]] = {}
        for row in self.get_all(f"{entity_set}?$select={id_column},{name_column}"):
            found.setdefault(row.get(name_column) or "", []).append(row[id_column])
        return found

    def create(self, entity_set: str, body: dict) -> str:
        resp = self.request("POST", entity_set, json=body)
        # OData-EntityId: https://org.crm.dynamics.com/api/data/v9.2/jc_trainingcourses(<guid>)
        return resp.headers["OData-EntityId"].rsplit("(", 1)[1].rstrip(")")

    def delete(self, entity_set: str, row_id: str) -> None:
        self.request("DELETE", f"{entity_set}({row_id})")


def read_csv(name: str) -> list[dict]:
    with open(SEED_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_time(value: str) -> datetime:
    """Parse the seed files' timestamp format, e.g. 2026-01-06T15:10:00Z."""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def validate_seed(courses: list[dict], reqs: list[dict]) -> list[str]:
    """Return every problem in the seed data. An empty list means it is loadable.

    Checked before sign-in so a typo in a CSV fails in a second, not after 20 rows are written.
    """
    errors: list[str] = []
    costs: dict[str, float] = {}

    for line, c in enumerate(courses, start=2):
        where = f"courses.csv line {line}"
        name = c["name"].strip()
        if not name:
            errors.append(f"{where}: name is empty")
        elif name in costs:
            errors.append(f"{where}: duplicate course name {name!r}")
        if c["category"] not in CATEGORIES:
            errors.append(f"{where}: unknown category {c['category']!r}")
        if c["active"].lower() not in {"true", "false"}:
            errors.append(f"{where}: active must be true or false, got {c['active']!r}")
        try:
            cost = float(c["cost"])
            if cost < 0:
                raise ValueError
        except ValueError:
            errors.append(f"{where}: cost must be a number >= 0, got {c['cost']!r}")
            cost = 0.0
        try:
            if int(c["hours"]) < 1:
                raise ValueError
        except ValueError:
            errors.append(f"{where}: hours must be a whole number >= 1, got {c['hours']!r}")
        costs[name] = cost

    titles: set[str] = set()
    for line, r in enumerate(reqs, start=2):
        where = f"requests.csv line {line}"
        title, status = r["title"].strip(), r["status"]
        if not title:
            errors.append(f"{where}: title is empty")
        elif title in titles:
            # Titles are how re-runs and --reset recognise seeded rows.
            errors.append(f"{where}: duplicate title {title!r}")
        titles.add(title)
        if r["course"] not in costs:
            errors.append(f"{where}: course {r['course']!r} is not in courses.csv")
        elif costs[r["course"]] > JUSTIFICATION_THRESHOLD and not r["justification"].strip():
            errors.append(f"{where}: justification is required for courses over ${JUSTIFICATION_THRESHOLD:,.0f}")
        if status not in STATUSES:
            errors.append(f"{where}: unknown status {status!r}")
            continue

        times: dict[str, datetime | None] = {}
        for key in ("submitted_on", "decision_date", "completed_on"):
            try:
                times[key] = parse_time(r[key]) if r[key] else None
            except ValueError:
                errors.append(f"{where}: {key} must look like 2026-01-06T15:10:00Z, got {r[key]!r}")
                times[key] = None
        submitted, decided, completed = times["submitted_on"], times["decision_date"], times["completed_on"]

        if (status == "Draft") == bool(r["submitted_on"]):
            errors.append(f"{where}: submitted_on must be set for every status except Draft")
        if (status in DECIDED) != bool(r["decision_date"]):
            errors.append(f"{where}: decision_date must be set only for Approved, Rejected, Completed")
        if (status == "Completed") != bool(r["completed_on"]):
            errors.append(f"{where}: completed_on must be set only for Completed")
        if submitted and decided and decided < submitted:
            errors.append(f"{where}: decision_date is before submitted_on")
        if decided and completed and completed < decided:
            errors.append(f"{where}: completed_on is before decision_date")
    return errors


def course_body(c: dict, categories: dict[str, int]) -> dict:
    return {
        C["name"]: c["name"],
        C["provider"]: c["provider"],
        C["category"]: categories[c["category"]],
        C["cost"]: float(c["cost"]),
        C["hours"]: int(c["hours"]),
        C["active"]: c["active"].lower() == "true",
    }


def request_body(
    r: dict,
    *,
    statuses: dict[str, int],
    course_ref: str,
    course_cost: float,
    course_nav: str,
    approver_nav: str,
    approver_id: str,
    approver_email: str,
    now: str,
) -> dict:
    """Build the Web API payload for one seed request."""
    body = {
        R["title"]: r["title"],
        f"{course_nav}@odata.bind": course_ref,
        R["status"]: statuses[r["status"]],
        R["course_cost"]: course_cost,
        # Backdate Created On so "newest first" sorting in the app looks realistic.
        "overriddencreatedon": r["submitted_on"] or now,
    }
    if r["status"] != "Draft":
        # The approval flow stamps the approver at submit time, so drafts have none.
        body[f"{approver_nav}@odata.bind"] = f"/systemusers({approver_id})"
    if r["status"] == "Submitted" and approver_email:
        # Makes the seeded pending rows show up in the canvas app's "Waiting on me" queue.
        body[R["pending_with"]] = approver_email
    for key in ("justification", "submitted_on", "decision_date", "decision_comments", "completed_on"):
        if r[key]:
            body[R[key]] = r[key]
    return body


def check_labels(kind: str, used: set[str], available: dict[str, int]) -> None:
    missing = used - available.keys()
    if missing:
        sys.exit(f"{kind} labels missing in Dataverse: {sorted(missing)}. Found: {sorted(available)}")


def normalise_env(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.path.strip("/"):
        sys.exit(f"--env must look like https://<org>.crm.dynamics.com, got {url!r}")
    return f"https://{parsed.hostname}"


def confirm_reset(env: str, n_requests: int, n_courses: int, assume_yes: bool) -> None:
    host = urlparse(env).hostname
    print(f"--reset will delete {n_requests} seeded requests and {n_courses} seeded courses from {host}.")
    if assume_yes:
        return
    if not sys.stdin.isatty():
        sys.exit("Refusing to delete without confirmation. Re-run with --yes to skip the prompt.")
    if input(f"Type the environment host ({host}) to confirm: ").strip().lower() != host:
        sys.exit("Host did not match. Nothing deleted.")


def reset(dv: Dataverse, env: str, sets: dict, courses: list[dict], reqs: list[dict], assume_yes: bool) -> None:
    """Delete the rows this script seeds (matched by title / name) and nothing else."""
    existing_reqs = dv.ids_by_name(sets["request"], sets["request_id"], R["title"])
    existing_courses = dv.ids_by_name(sets["course"], sets["course_id"], C["name"])
    req_ids = [i for r in reqs for i in existing_reqs.get(r["title"], [])]
    course_ids = [i for c in courses for i in existing_courses.get(c["name"], [])]
    if not req_ids and not course_ids:
        print("Nothing to reset.")
        return
    confirm_reset(env, len(req_ids), len(course_ids), assume_yes)

    for row_id in req_ids:
        dv.delete(sets["request"], row_id)
    kept = 0
    for row_id in course_ids:
        try:
            dv.delete(sets["course"], row_id)
        except RuntimeError:
            # Restrict delete: a request someone created in the app still points at this course.
            kept += 1
    print(f"Deleted {len(req_ids)} requests and {len(course_ids) - kept} courses")
    if kept:
        print(f"Kept {kept} courses that non-seed requests still reference")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", help="Environment URL, e.g. https://org.crm.dynamics.com")
    parser.add_argument("--check", action="store_true", help="Validate the seed CSVs and exit (no sign-in)")
    parser.add_argument("--dry-run", action="store_true", help="Resolve metadata and print choice values only")
    parser.add_argument("--reset", action="store_true", help="Delete previously seeded rows first")
    parser.add_argument("--yes", action="store_true", help="Skip the --reset confirmation prompt")
    args = parser.parse_args()

    courses = read_csv("courses.csv")
    reqs = read_csv("requests.csv")
    errors = validate_seed(courses, reqs)
    if errors:
        sys.exit("Seed data is invalid:\n  " + "\n  ".join(errors))
    if args.check:
        print(f"Seed data OK: {len(courses)} courses, {len(reqs)} requests.")
        return
    if not args.env:
        parser.error("--env is required unless --check is given")

    env = normalise_env(args.env)
    dv = Dataverse(env)

    sets = {
        "course": dv.entity_set(COURSE_TABLE),
        "request": dv.entity_set(REQUEST_TABLE),
        "course_id": dv.primary_id(COURSE_TABLE),
        "request_id": dv.primary_id(REQUEST_TABLE),
    }
    categories = dv.choice_values(COURSE_TABLE, C["category"])
    statuses = dv.choice_values(REQUEST_TABLE, R["status"])
    actions = dv.choice_values(REQUEST_TABLE, R["action"])
    course_nav = dv.nav_property(REQUEST_TABLE, R["course"])
    approver_nav = dv.nav_property(REQUEST_TABLE, R["approver"])
    me = dv.get("WhoAmI")["UserId"]
    my_email = dv.get(f"systemusers({me})?$select=internalemailaddress").get("internalemailaddress") or ""

    check_labels("Category", CATEGORIES, categories)
    check_labels("Request Status", STATUSES, statuses)
    check_labels("Requested Action", ACTIONS, actions)
    print(f"Tables: {sets['course']}, {sets['request']}")
    print(f"Category values:         {categories}")
    print(f"Request Status values:   {statuses}")
    print(f"Requested Action values: {actions}")
    print("  -> copy the Status and Action values into the table in dataverse/schema.md;")
    print("     the flow trigger filters and conditions use them.")
    print(f"Lookups: {course_nav}, {approver_nav}")

    if args.dry_run:
        print("Dry run OK. Nothing written.")
        return

    if args.reset:
        reset(dv, env, sets, courses, reqs, args.yes)

    existing_courses = dv.ids_by_name(sets["course"], sets["course_id"], C["name"])
    course_ids: dict[str, str] = {}
    created = 0
    for c in courses:
        if c["name"] in existing_courses:
            course_ids[c["name"]] = existing_courses[c["name"]][0]
        else:
            course_ids[c["name"]] = dv.create(sets["course"], course_body(c, categories))
            created += 1
    print(f"Courses: created {created}, already present {len(courses) - created}")

    existing_reqs = dv.ids_by_name(sets["request"], sets["request_id"], R["title"])
    costs = {c["name"]: float(c["cost"]) for c in courses}
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    created = 0
    for r in reqs:
        if r["title"] in existing_reqs:
            continue
        dv.create(
            sets["request"],
            request_body(
                r,
                statuses=statuses,
                course_ref=f"/{sets['course']}({course_ids[r['course']]})",
                course_cost=costs[r["course"]],
                course_nav=course_nav,
                approver_nav=approver_nav,
                approver_id=me,
                approver_email=my_email,
                now=now,
            ),
        )
        created += 1
    print(f"Requests: created {created}, already present {len(reqs) - created} (approver = you)")


if __name__ == "__main__":
    main()
