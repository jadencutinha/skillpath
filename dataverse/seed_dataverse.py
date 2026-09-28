"""Load seed courses and requests into Dataverse through the Web API.

Usage:
    pip install -r dataverse/requirements.txt
    python dataverse/seed_dataverse.py --env https://<org>.crm.dynamics.com --dry-run
    python dataverse/seed_dataverse.py --env https://<org>.crm.dynamics.com
    python dataverse/seed_dataverse.py --env https://<org>.crm.dynamics.com --reset

Sign-in uses the device-code flow with Microsoft's public sample client ID,
so you don't need an app registration. Sign in with your developer environment account.

Choice values, entity set names, and lookup navigation properties are all read
from metadata. The script does not depend on the option values your publisher
prefix generated.

Turn the approval flow OFF before seeding. Otherwise every "Submitted" row
starts a real approval.
"""

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

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
    "approver": "jc_approver",
    "submitted_on": "jc_submittedon",
    "decision_date": "jc_decisiondate",
    "decision_comments": "jc_decisioncomments",
    "course_cost": "jc_coursecost",
}

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

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        resp = self.session.request(method, f"{self.api}/{path}", **kwargs)
        if not resp.ok:
            raise RuntimeError(f"{method} {path} -> {resp.status_code}: {resp.text[:500]}")
        return resp

    def get(self, path: str) -> dict:
        return self.request("GET", path).json()

    def entity_set(self, table: str) -> str:
        return self.get(f"EntityDefinitions(LogicalName='{table}')?$select=EntitySetName")["EntitySetName"]

    def primary_id(self, table: str) -> str:
        return self.get(f"EntityDefinitions(LogicalName='{table}')?$select=PrimaryIdAttribute")[
            "PrimaryIdAttribute"
        ]

    def choice_values(self, table: str, column: str) -> dict[str, int]:
        data = self.get(
            f"EntityDefinitions(LogicalName='{table}')/Attributes(LogicalName='{column}')"
            "/Microsoft.Dynamics.CRM.PicklistAttributeMetadata"
            "?$select=LogicalName&$expand=OptionSet($select=Options)"
        )
        return {
            opt["Label"]["UserLocalizedLabel"]["Label"]: opt["Value"]
            for opt in data["OptionSet"]["Options"]
        }

    def nav_property(self, table: str, lookup_column: str) -> str:
        rels = self.get(
            f"EntityDefinitions(LogicalName='{table}')/ManyToOneRelationships"
            "?$select=ReferencingAttribute,ReferencingEntityNavigationPropertyName"
        )["value"]
        for rel in rels:
            if rel["ReferencingAttribute"] == lookup_column:
                return rel["ReferencingEntityNavigationPropertyName"]
        raise RuntimeError(f"No lookup relationship found for {table}.{lookup_column}")

    def create(self, entity_set: str, body: dict) -> str:
        resp = self.request("POST", entity_set, json=body)
        # OData-EntityId: https://org.crm.dynamics.com/api/data/v9.2/jc_trainingcourses(<guid>)
        return resp.headers["OData-EntityId"].rsplit("(", 1)[1].rstrip(")")

    def delete_all(self, entity_set: str, id_column: str) -> int:
        rows = self.get(f"{entity_set}?$select={id_column}")["value"]
        for row in rows:
            self.request("DELETE", f"{entity_set}({row[id_column]})")
        return len(rows)


def read_csv(name: str) -> list[dict]:
    with open(SEED_DIR / name, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check_labels(kind: str, used: set[str], available: dict[str, int]) -> None:
    missing = used - available.keys()
    if missing:
        sys.exit(f"{kind} labels missing in Dataverse: {sorted(missing)}. Found: {sorted(available)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", required=True, help="Environment URL, e.g. https://org.crm.dynamics.com")
    parser.add_argument("--reset", action="store_true", help="Delete existing requests and courses first")
    parser.add_argument("--dry-run", action="store_true", help="Resolve metadata and validate CSVs only")
    args = parser.parse_args()

    courses = read_csv("courses.csv")
    reqs = read_csv("requests.csv")
    dv = Dataverse(args.env)

    course_set = dv.entity_set(COURSE_TABLE)
    request_set = dv.entity_set(REQUEST_TABLE)
    categories = dv.choice_values(COURSE_TABLE, C["category"])
    statuses = dv.choice_values(REQUEST_TABLE, R["status"])
    course_nav = dv.nav_property(REQUEST_TABLE, R["course"])
    approver_nav = dv.nav_property(REQUEST_TABLE, R["approver"])
    me = dv.get("WhoAmI")["UserId"]

    check_labels("Category", {c["category"] for c in courses}, categories)
    check_labels("Request Status", {r["status"] for r in reqs}, statuses)
    print(f"Tables: {course_set}, {request_set}")
    print(f"Category values: {categories}")
    print(f"Status values:   {statuses}   <- note the Submitted value for the flow trigger")
    print(f"Lookups: {course_nav}, {approver_nav}")

    if args.dry_run:
        print("Dry run OK. Nothing written.")
        return

    if args.reset:
        n_req = dv.delete_all(request_set, dv.primary_id(REQUEST_TABLE))
        n_course = dv.delete_all(course_set, dv.primary_id(COURSE_TABLE))
        print(f"Deleted {n_req} requests and {n_course} courses")

    course_ids: dict[str, str] = {}
    course_costs: dict[str, float] = {}
    for c in courses:
        course_ids[c["name"]] = dv.create(
            course_set,
            {
                C["name"]: c["name"],
                C["provider"]: c["provider"],
                C["category"]: categories[c["category"]],
                C["cost"]: float(c["cost"]),
                C["hours"]: int(c["hours"]),
                C["active"]: c["active"].lower() == "true",
            },
        )
        course_costs[c["name"]] = float(c["cost"])
    print(f"Created {len(course_ids)} courses")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for r in reqs:
        body = {
            R["title"]: r["title"],
            f"{course_nav}@odata.bind": f"/{course_set}({course_ids[r['course']]})",
            f"{approver_nav}@odata.bind": f"/systemusers({me})",
            R["status"]: statuses[r["status"]],
            R["course_cost"]: course_costs[r["course"]],
            # Backdate Created On so "newest first" sorting in the app looks realistic.
            "overriddencreatedon": r["submitted_on"] or now,
        }
        for key in ("justification", "submitted_on", "decision_date", "decision_comments"):
            if r[key]:
                body[R[key]] = r[key]
        dv.create(request_set, body)
    print(f"Created {len(reqs)} requests (approver = you)")


if __name__ == "__main__":
    main()
