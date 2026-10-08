"""Create the Training Requests data model in Dataverse through the Web API.

Usage:
    pip install -r dataverse/requirements.txt
    python dataverse/create_schema.py --plan                                  # list what would be created (no sign-in)
    python dataverse/create_schema.py --env https://<org>.crm.dynamics.com

It does what steps 1-3 of docs/BUILD_GUIDE.md otherwise have you click through:

    publisher (prefix jc)  ->  solution TrainingRequests  ->  both tables and every column,
    with column security switched on where schema.md says so  ->  the four views  ->  the two
    column security profiles and their permissions  ->  publish.

Safe to re-run: anything that already exists is left alone, so a run that stops half way can
simply be started again. Sign in with an account that has the System Administrator or System
Customizer role in the environment.

Still done by hand afterwards: the justification business rule, the three security roles, and
adding people to the column security profiles. See dataverse/schema.md and
dataverse/security-roles.md.

This file is the executable form of dataverse/schema.md. If you change one, change the other;
a test compares the column names here with the ones the seed script and the docs use.
"""

import argparse
from xml.sax.saxutils import quoteattr

from seed_dataverse import Dataverse, normalise_env

PREFIX = "jc"
PUBLISHER = {"uniquename": "jadencutinha", "friendlyname": "Jaden Cutinha"}
SOLUTION = {"uniquename": "TrainingRequests", "friendlyname": "Training Requests", "version": "1.0.0.0"}
LANGUAGE = 1033

READ_PROFILE = "Training - Read Decision Fields"
WRITE_PROFILE = "Training - Write Decision Fields"

# One entry per column, in the order schema.md lists them.
#   secured=True     column security on; requesters get read only
#   create_only=True column security on; requesters may set it when creating the row, never after
TABLES = [
    {
        "schema": "jc_TrainingCourse",
        "display": "Training Course",
        "plural": "Training Courses",
        "primary": {"schema": "jc_Name", "display": "Name"},
        "columns": [
            {"schema": "jc_Provider", "display": "Provider", "type": "text"},
            {
                "schema": "jc_Category",
                "display": "Category",
                "type": "choice",
                "options": ["Technical", "Leadership", "Compliance", "Professional Development"],
            },
            {"schema": "jc_Cost", "display": "Cost", "type": "money", "required": True},
            {"schema": "jc_Hours", "display": "Hours", "type": "whole", "min": 1, "max": 10000, "required": True},
            {"schema": "jc_Active", "display": "Active", "type": "yesno", "default": True},
        ],
    },
    {
        "schema": "jc_TrainingRequest",
        "display": "Training Request",
        "plural": "Training Requests",
        "primary": {"schema": "jc_Title", "display": "Title"},
        "columns": [
            {
                "schema": "jc_Course",
                "display": "Course",
                "type": "lookup",
                "target": "jc_trainingcourse",
                "relationship": "jc_trainingcourse_jc_trainingrequest",
                "delete": "Restrict",
                "required": True,
                "create_only": True,
            },
            {"schema": "jc_Justification", "display": "Justification", "type": "multiline"},
            {
                "schema": "jc_RequestedAction",
                "display": "Requested Action",
                "type": "choice",
                "options": ["Submit", "Withdraw", "Complete"],
            },
            {
                "schema": "jc_RequestStatus",
                "display": "Request Status",
                "type": "choice",
                "options": [
                    "Draft",
                    "Submitted",
                    "Approved",
                    "Rejected",
                    "Completed",
                    "Error",
                    "Withdrawn",
                    "Expired",
                ],
                "default": "Draft",
                "secured": True,
            },
            {
                "schema": "jc_Approver",
                "display": "Approver",
                "type": "lookup",
                "target": "systemuser",
                "relationship": "jc_systemuser_jc_trainingrequest_approver",
                "delete": "RemoveLink",
                "secured": True,
            },
            {"schema": "jc_PendingWith", "display": "Pending With", "type": "text", "format": "Email", "secured": True},
            {
                "schema": "jc_ApprovalLink",
                "display": "Approval Link",
                "type": "text",
                "format": "Url",
                "length": 1000,
                "secured": True,
            },
            {"schema": "jc_CourseCost", "display": "Course Cost", "type": "money", "secured": True},
            {"schema": "jc_SubmittedOn", "display": "Submitted On", "type": "datetime", "secured": True},
            {"schema": "jc_DecisionDate", "display": "Decision Date", "type": "datetime", "secured": True},
            {"schema": "jc_DecisionComments", "display": "Decision Comments", "type": "multiline", "secured": True},
            {"schema": "jc_CompletedOn", "display": "Completed On", "type": "datetime", "secured": True},
        ],
    },
]

# The views schema.md lists. A condition is (column, operator, value); a value written as
# "Request Status:Submitted" is replaced by that choice's number at run time.
VIEWS = [
    {
        "table": "jc_trainingcourse",
        "name": "Active Courses",
        "columns": ["jc_name", "jc_provider", "jc_category", "jc_cost", "jc_hours"],
        "filter": ("and", [("jc_active", "eq", "1")]),
        "order": ("jc_name", False),
    },
    {
        "table": "jc_trainingrequest",
        "name": "Pending Requests",
        "columns": ["jc_title", "jc_course", "ownerid", "jc_pendingwith", "jc_submittedon", "jc_coursecost"],
        "filter": ("and", [("jc_requeststatus", "eq", "Request Status:Submitted")]),
        "order": ("jc_submittedon", False),  # oldest first
    },
    {
        "table": "jc_trainingrequest",
        "name": "Decided This Month",
        "columns": ["jc_title", "jc_course", "ownerid", "jc_requeststatus", "jc_decisiondate"],
        "filter": ("and", [("jc_decisiondate", "this-month", None)]),
        "order": ("jc_decisiondate", True),
    },
    {
        "table": "jc_trainingrequest",
        "name": "Needs Attention",
        "columns": [
            "jc_title",
            "ownerid",
            "jc_requeststatus",
            "jc_requestedaction",
            "jc_decisioncomments",
            "modifiedon",
        ],
        # Failed requests, or a command no flow has picked up for an hour.
        "filter": (
            "or",
            [
                ("jc_requeststatus", "eq", "Request Status:Error"),
                ("and", [("jc_requestedaction", "not-null", None), ("modifiedon", "olderthan-x-hours", "1")]),
            ],
        ),
        "order": ("modifiedon", False),
    },
]


# ---------- payload builders (pure, tested offline) ----------


def label(text: str) -> dict:
    return {
        "@odata.type": "Microsoft.Dynamics.CRM.Label",
        "LocalizedLabels": [
            {"@odata.type": "Microsoft.Dynamics.CRM.LocalizedLabel", "Label": text, "LanguageCode": LANGUAGE}
        ],
    }


def required_level(required: bool) -> dict:
    return {
        "Value": "ApplicationRequired" if required else "None",
        "CanBeChanged": True,
        "ManagedPropertyLogicalName": "canmodifyrequirementlevelsettings",
    }


def is_secured(column: dict) -> bool:
    return bool(column.get("secured") or column.get("create_only"))


def option_value(option_prefix: int, index: int) -> int:
    """Dataverse numbers choice options from the publisher's option prefix: 12345 -> 123450000, 123450001, ..."""
    return option_prefix * 10000 + index


def column_body(column: dict, option_prefix: int) -> dict:
    """Web API metadata for one non-lookup column."""
    kind = column["type"]
    body = {
        "SchemaName": column["schema"],
        "DisplayName": label(column["display"]),
        "RequiredLevel": required_level(column.get("required", False)),
        "IsSecured": is_secured(column),
    }
    if kind == "text":
        body |= {
            "@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata",
            "MaxLength": column.get("length", 100),
            "FormatName": {"Value": column.get("format", "Text")},
        }
    elif kind == "multiline":
        body |= {
            "@odata.type": "Microsoft.Dynamics.CRM.MemoAttributeMetadata",
            "MaxLength": 2000,
            "Format": "TextArea",
        }
    elif kind == "choice":
        options = column["options"]
        body |= {
            "@odata.type": "Microsoft.Dynamics.CRM.PicklistAttributeMetadata",
            "OptionSet": {
                "@odata.type": "Microsoft.Dynamics.CRM.OptionSetMetadata",
                "IsGlobal": False,
                "OptionSetType": "Picklist",
                "Options": [
                    {"Value": option_value(option_prefix, i), "Label": label(o)} for i, o in enumerate(options)
                ],
            },
        }
        if "default" in column:
            body["DefaultFormValue"] = option_value(option_prefix, options.index(column["default"]))
    elif kind == "money":
        body |= {
            "@odata.type": "Microsoft.Dynamics.CRM.MoneyAttributeMetadata",
            "MinValue": 0,
            "MaxValue": 1_000_000,
            "PrecisionSource": 2,  # use the currency's precision
        }
    elif kind == "whole":
        body |= {
            "@odata.type": "Microsoft.Dynamics.CRM.IntegerAttributeMetadata",
            "Format": "None",
            "MinValue": column["min"],
            "MaxValue": column["max"],
        }
    elif kind == "yesno":
        body |= {
            "@odata.type": "Microsoft.Dynamics.CRM.BooleanAttributeMetadata",
            "DefaultValue": column["default"],
            "OptionSet": {
                "@odata.type": "Microsoft.Dynamics.CRM.BooleanOptionSetMetadata",
                "TrueOption": {"Value": 1, "Label": label("Yes")},
                "FalseOption": {"Value": 0, "Label": label("No")},
            },
        }
    elif kind == "datetime":
        body |= {
            "@odata.type": "Microsoft.Dynamics.CRM.DateTimeAttributeMetadata",
            "Format": "DateAndTime",
            "DateTimeBehavior": {"Value": "UserLocal"},
        }
    else:
        raise ValueError(f"{column['schema']}: no payload for column type {kind!r}")
    return body


def table_body(table: dict) -> dict:
    """Web API metadata for a table and its primary name column."""
    primary = table["primary"]
    return {
        "@odata.type": "Microsoft.Dynamics.CRM.EntityMetadata",
        "SchemaName": table["schema"],
        "DisplayName": label(table["display"]),
        "DisplayCollectionName": label(table["plural"]),
        "Description": label(f"{table['display']} (Training Requests solution)"),
        "OwnershipType": "UserOwned",  # required for User-level security roles
        "HasActivities": False,
        "HasNotes": False,
        "IsActivity": False,
        "Attributes": [
            {
                "@odata.type": "Microsoft.Dynamics.CRM.StringAttributeMetadata",
                "SchemaName": primary["schema"],
                "DisplayName": label(primary["display"]),
                "IsPrimaryName": True,
                "MaxLength": 100,
                "FormatName": {"Value": "Text"},
                "RequiredLevel": required_level(True),
            }
        ],
    }


def relationship_body(table: dict, column: dict) -> dict:
    """Web API metadata for a lookup column, which is created as a one-to-many relationship."""
    return {
        "@odata.type": "Microsoft.Dynamics.CRM.OneToManyRelationshipMetadata",
        "SchemaName": column["relationship"],
        "ReferencedEntity": column["target"],
        "ReferencingEntity": table["schema"].lower(),
        "CascadeConfiguration": {
            "Assign": "NoCascade",
            "Delete": column["delete"],
            "Merge": "NoCascade",
            "Reparent": "NoCascade",
            "Share": "NoCascade",
            "Unshare": "NoCascade",
        },
        "Lookup": {
            "@odata.type": "Microsoft.Dynamics.CRM.LookupAttributeMetadata",
            "SchemaName": column["schema"],
            "DisplayName": label(column["display"]),
            "RequiredLevel": required_level(column.get("required", False)),
            "IsSecured": is_secured(column),
        },
    }


def filter_xml(node: tuple, choices: dict[str, dict[str, int]]) -> str:
    """FetchXML for a filter tree: ("and" | "or", [condition or nested filter, ...])."""
    kind, parts = node
    inner = []
    for part in parts:
        if part[0] in ("and", "or"):
            inner.append(filter_xml(part, choices))
            continue
        column, operator, value = part
        if value is not None and ":" in value:
            choice, option = value.split(":")
            value = str(choices[choice][option])
        attrs = f"attribute={quoteattr(column)} operator={quoteattr(operator)}"
        inner.append(f"<condition {attrs}{'' if value is None else f' value={quoteattr(value)}'}/>")
    return f'<filter type="{kind}">{"".join(inner)}</filter>'


def view_body(view: dict, object_type_code: int, choices: dict[str, dict[str, int]]) -> dict:
    """Web API payload for a public view (a savedquery row) on one table."""
    table = view["table"]
    primary_id = f"{table}id"
    order_by, descending = view["order"]
    attributes = "".join(f"<attribute name={quoteattr(c)}/>" for c in [*view["columns"], primary_id])
    fetch = (
        '<fetch version="1.0" mapping="logical">'
        f"<entity name={quoteattr(table)}>{attributes}"
        f'<order attribute={quoteattr(order_by)} descending="{str(descending).lower()}"/>'
        f"{filter_xml(view['filter'], choices)}"
        "</entity></fetch>"
    )
    cells = "".join(
        f'<cell name={quoteattr(c)} width="{240 if i == 0 else 150}"/>' for i, c in enumerate(view["columns"])
    )
    layout = (
        f'<grid name="resultset" object="{object_type_code}" jump={quoteattr(view["columns"][0])} '
        'select="1" icon="1" preview="1">'
        f'<row name="result" id={quoteattr(primary_id)}>{cells}</row></grid>'
    )
    return {
        "name": view["name"],
        "returnedtypecode": table,
        "querytype": 0,  # a public view
        "fetchxml": fetch,
        "layoutxml": layout,
    }


ALLOWED, NOT_ALLOWED = 4, 0  # field permission values used by Dataverse


def permissions(profile: str) -> list[dict]:
    """One field permission per secured column, for the Read or the Write profile."""
    rows = []
    for table in TABLES:
        for column in table["columns"]:
            if not is_secured(column):
                continue
            write = profile == WRITE_PROFILE
            rows.append(
                {
                    "entityname": table["schema"].lower(),
                    "attributelogicalname": column["schema"].lower(),
                    "canread": ALLOWED,
                    "cancreate": ALLOWED if write or column.get("create_only") else NOT_ALLOWED,
                    "canupdate": ALLOWED if write else NOT_ALLOWED,
                }
            )
    return rows


def plan_lines() -> list[str]:
    lines = [
        f"Publisher  {PUBLISHER['uniquename']} (prefix {PREFIX})",
        f"Solution   {SOLUTION['uniquename']}",
    ]
    for table in TABLES:
        lines.append(f"Table      {table['schema'].lower()}  ({table['display']})")
        lines.append(f"  column   {table['primary']['schema'].lower():<24} primary name")
        for c in table["columns"]:
            notes = [c["type"]]
            if c["type"] == "lookup":
                notes.append(f"-> {c['target']}, delete {c['delete']}")
            if c.get("required"):
                notes.append("required")
            if c.get("create_only"):
                notes.append("column security: set on create only")
            elif c.get("secured"):
                notes.append("column security: flow-owned")
            lines.append(f"  column   {c['schema'].lower():<24} {', '.join(notes)}")
    for view in VIEWS:
        lines.append(f"View       {view['table']}: {view['name']}")
    for profile in (READ_PROFILE, WRITE_PROFILE):
        lines.append(f"Profile    {profile}  ({len(permissions(profile))} field permissions)")
    return lines


# ---------- Web API ----------


class Builder:
    """Creates each component unless it already exists, and counts what it did."""

    def __init__(self, dv: Dataverse):
        self.dv = dv
        self.created = 0
        self.skipped = 0
        self.in_solution = {"MSCRM.SolutionUniqueName": SOLUTION["uniquename"]}

    def exists(self, path: str) -> bool:
        resp = self.dv.session.request("GET", f"{self.dv.api}/{path}", timeout=60)
        if resp.status_code == 404:
            return False
        if not resp.ok:
            raise RuntimeError(f"GET {path} -> {resp.status_code}: {resp.text[:500]}")
        return True

    def post(self, path: str, body: dict, *, in_solution: bool = True) -> str | None:
        """POST and return the new row's ID when the response names one. Metadata calls can take minutes."""
        resp = self.dv.session.request(
            "POST",
            f"{self.dv.api}/{path}",
            json=body,
            headers=self.in_solution if in_solution else None,
            timeout=600,
        )
        if not resp.ok:
            raise RuntimeError(f"POST {path} -> {resp.status_code}: {resp.text[:800]}")
        entity_id = resp.headers.get("OData-EntityId", "")
        return entity_id.rsplit("(", 1)[1].rstrip(")") if "(" in entity_id else None

    def done(self, created: bool, what: str) -> None:
        if created:
            self.created += 1
        else:
            self.skipped += 1
        print(f"  {'created' if created else 'exists '}  {what}", flush=True)

    def publisher(self, option_prefix: int) -> tuple[str, int]:
        """Return the publisher's ID and the option-value prefix choices must use."""
        found = self.dv.get(
            f"publishers?$filter=customizationprefix eq '{PREFIX}'"
            "&$select=publisherid,uniquename,customizationoptionvalueprefix"
        )["value"]
        if found:
            self.done(False, f"publisher {found[0]['uniquename']}")
            return found[0]["publisherid"], found[0]["customizationoptionvalueprefix"]
        publisher_id = self.post(
            "publishers",
            PUBLISHER | {"customizationprefix": PREFIX, "customizationoptionvalueprefix": option_prefix},
            in_solution=False,
        )
        self.done(True, f"publisher {PUBLISHER['uniquename']}")
        return publisher_id, option_prefix

    def solution(self, publisher_id: str) -> None:
        name = SOLUTION["uniquename"]
        if self.dv.get(f"solutions?$filter=uniquename eq '{name}'&$select=solutionid")["value"]:
            return self.done(False, f"solution {name}")
        self.post("solutions", SOLUTION | {"publisherid@odata.bind": f"/publishers({publisher_id})"}, in_solution=False)
        self.done(True, f"solution {name}")

    def table(self, table: dict, option_prefix: int) -> None:
        logical = table["schema"].lower()
        entity = f"EntityDefinitions(LogicalName='{logical}')"
        if self.exists(f"{entity}?$select=LogicalName"):
            self.done(False, f"table {logical}")
        else:
            self.post("EntityDefinitions", table_body(table))
            self.done(True, f"table {logical}")

        for column in table["columns"]:
            name = column["schema"].lower()
            if self.exists(f"{entity}/Attributes(LogicalName='{name}')?$select=LogicalName"):
                self.done(False, f"column {logical}.{name}")
            elif column["type"] == "lookup":
                self.post("RelationshipDefinitions", relationship_body(table, column))
                self.done(True, f"column {logical}.{name} (lookup)")
            else:
                self.post(f"{entity}/Attributes", column_body(column, option_prefix))
                self.done(True, f"column {logical}.{name}")

    def view(self, view: dict, object_type_code: int, choices: dict[str, dict[str, int]]) -> None:
        what = f"view {view['table']}: {view['name']}"
        found = self.dv.get(
            f"savedqueries?$filter=name eq '{view['name']}' and returnedtypecode eq '{view['table']}'"
            "&$select=savedqueryid"
        )["value"]
        if found:
            return self.done(False, what)
        self.post("savedqueries", view_body(view, object_type_code, choices))
        self.done(True, what)

    def views(self) -> None:
        dv = self.dv
        choices = {"Request Status": dv.choice_values("jc_trainingrequest", "jc_requeststatus")}
        for view in VIEWS:
            code = dv.get(f"EntityDefinitions(LogicalName='{view['table']}')?$select=ObjectTypeCode")["ObjectTypeCode"]
            self.view(view, code, choices)

    def profile(self, name: str) -> None:
        found = self.dv.get(f"fieldsecurityprofiles?$filter=name eq '{name}'&$select=fieldsecurityprofileid")["value"]
        if found:
            profile_id = found[0]["fieldsecurityprofileid"]
            self.done(False, f"profile {name}")
        else:
            profile_id = self.post("fieldsecurityprofiles", {"name": name})
            self.done(True, f"profile {name}")

        existing = {
            (row["entityname"], row["attributelogicalname"])
            for row in self.dv.get_all(
                f"fieldpermissions?$filter=_fieldsecurityprofileid_value eq {profile_id}"
                "&$select=entityname,attributelogicalname"
            )
        }
        for permission in permissions(name):
            key = (permission["entityname"], permission["attributelogicalname"])
            if key in existing:
                self.done(False, f"permission {name}: {key[1]}")
                continue
            self.post(
                "fieldpermissions",
                permission | {"fieldsecurityprofileid@odata.bind": f"/fieldsecurityprofiles({profile_id})"},
            )
            self.done(True, f"permission {name}: {key[1]}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env", help="Environment URL, e.g. https://org.crm.dynamics.com")
    parser.add_argument("--plan", action="store_true", help="List what would be created and exit (no sign-in)")
    parser.add_argument(
        "--option-prefix",
        type=int,
        default=12345,
        help="Choice value prefix for a NEW publisher (10000-99999). Ignored if the jc publisher exists.",
    )
    args = parser.parse_args()

    if args.plan:
        print("\n".join(plan_lines()))
        return
    if not args.env:
        parser.error("--env is required unless --plan is given")
    if not 10000 <= args.option_prefix <= 99999:
        parser.error("--option-prefix must be between 10000 and 99999")

    build = Builder(Dataverse(normalise_env(args.env)))
    publisher_id, option_prefix = build.publisher(args.option_prefix)
    build.solution(publisher_id)
    for table in TABLES:
        build.table(table, option_prefix)
    build.views()
    for profile in (READ_PROFILE, WRITE_PROFILE):
        build.profile(profile)

    print("Publishing customizations...", flush=True)
    build.post("PublishAllXml", {}, in_solution=False)
    print(f"Done: {build.created} created, {build.skipped} already present.")
    print("Next, by hand: the business rule (dataverse/schema.md), the security roles and profile")
    print("membership (dataverse/security-roles.md). Then: python dataverse/seed_dataverse.py --env ...")


if __name__ == "__main__":
    main()
