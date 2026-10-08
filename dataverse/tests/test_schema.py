"""Offline tests for create_schema.py: the model it describes, the payloads it builds,
and its create-unless-exists behaviour against a fake Web API."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import create_schema as schema
import seed_dataverse as seed

DOCS = Path(schema.__file__).parent
API = "https://org.crm.dynamics.com/api/data/v9.2"


def columns(table_schema: str) -> dict[str, dict]:
    table = next(t for t in schema.TABLES if t["schema"] == table_schema)
    return {c["schema"].lower(): c for c in table["columns"]} | {table["primary"]["schema"].lower(): table["primary"]}


COURSE = columns("jc_TrainingCourse")
REQUEST = columns("jc_TrainingRequest")
SECURED = {name for name, c in REQUEST.items() if schema.is_secured(c)}


# ---------- the model agrees with everything else in the repo ----------


def test_seed_script_columns_exist_in_the_model():
    assert set(seed.C.values()) <= COURSE.keys()
    assert set(seed.R.values()) <= REQUEST.keys()
    assert {t["schema"].lower() for t in schema.TABLES} == {seed.COURSE_TABLE, seed.REQUEST_TABLE}


def test_choices_match_the_seed_script():
    assert set(COURSE["jc_category"]["options"]) == seed.CATEGORIES
    assert set(REQUEST["jc_requeststatus"]["options"]) == seed.STATUSES
    assert set(REQUEST["jc_requestedaction"]["options"]) == seed.ACTIONS


def test_secured_columns_match_the_security_doc():
    text = (DOCS / "security-roles.md").read_text(encoding="utf-8")
    listed = text.split("Enable column security**):", 1)[1].split("**Then**", 1)[0]
    assert set(re.findall(r"`(jc_\w+)`", listed)) == SECURED


def test_every_model_column_is_documented_in_schema_md():
    text = (DOCS / "schema.md").read_text(encoding="utf-8")
    for name in COURSE.keys() | REQUEST.keys():
        assert f"`{name}`" in text, name


def test_status_defaults_to_draft_and_command_has_no_default():
    assert REQUEST["jc_requeststatus"]["default"] == "Draft"
    assert "default" not in REQUEST["jc_requestedaction"]


def test_requester_columns_are_not_locked():
    assert not {"jc_title", "jc_justification", "jc_requestedaction"} & SECURED
    assert REQUEST["jc_course"].get("create_only") is True


# ---------- payloads ----------


def test_option_values_follow_the_publisher_prefix():
    body = schema.column_body(REQUEST["jc_requeststatus"], 12345)
    values = [o["Value"] for o in body["OptionSet"]["Options"]]
    assert values == list(range(123450000, 123450008))
    assert body["DefaultFormValue"] == 123450000
    assert body["IsSecured"] is True
    assert "DefaultFormValue" not in schema.column_body(REQUEST["jc_requestedaction"], 12345)


@pytest.mark.parametrize(
    ("column", "odata_type", "expected"),
    [
        ("jc_provider", "StringAttributeMetadata", {"MaxLength": 100, "FormatName": {"Value": "Text"}}),
        ("jc_cost", "MoneyAttributeMetadata", {"MinValue": 0}),
        ("jc_hours", "IntegerAttributeMetadata", {"MinValue": 1, "MaxValue": 10000}),
        ("jc_active", "BooleanAttributeMetadata", {"DefaultValue": True}),
    ],
)
def test_course_column_payloads(column, odata_type, expected):
    body = schema.column_body(COURSE[column], 12345)
    assert body["@odata.type"] == f"Microsoft.Dynamics.CRM.{odata_type}"
    assert body["SchemaName"].lower() == column
    assert body["IsSecured"] is False
    assert expected.items() <= body.items()


def test_required_columns_are_marked_required():
    assert schema.column_body(COURSE["jc_cost"], 1)["RequiredLevel"]["Value"] == "ApplicationRequired"
    assert schema.column_body(COURSE["jc_provider"], 1)["RequiredLevel"]["Value"] == "None"


def test_request_text_and_date_payloads():
    link = schema.column_body(REQUEST["jc_approvallink"], 1)
    assert (link["MaxLength"], link["FormatName"]) == (1000, {"Value": "Url"})
    assert schema.column_body(REQUEST["jc_pendingwith"], 1)["FormatName"] == {"Value": "Email"}
    when = schema.column_body(REQUEST["jc_submittedon"], 1)
    assert when["DateTimeBehavior"] == {"Value": "UserLocal"}
    assert when["IsSecured"] is True


def test_table_payload_is_user_owned_with_a_primary_name():
    body = schema.table_body(schema.TABLES[1])
    assert body["OwnershipType"] == "UserOwned"
    (primary,) = body["Attributes"]
    assert primary["SchemaName"] == "jc_Title" and primary["IsPrimaryName"] is True


def test_lookups_are_built_as_relationships():
    table = schema.TABLES[1]
    course = schema.relationship_body(table, REQUEST["jc_course"])
    assert course["SchemaName"] == "jc_trainingcourse_jc_trainingrequest"
    assert (course["ReferencedEntity"], course["ReferencingEntity"]) == ("jc_trainingcourse", "jc_trainingrequest")
    # A course that has requests can't be deleted.
    assert course["CascadeConfiguration"]["Delete"] == "Restrict"
    assert course["Lookup"]["IsSecured"] is True
    assert course["Lookup"]["RequiredLevel"]["Value"] == "ApplicationRequired"

    approver = schema.relationship_body(table, REQUEST["jc_approver"])
    assert approver["ReferencedEntity"] == "systemuser"
    assert approver["CascadeConfiguration"]["Delete"] == "RemoveLink"


def test_unknown_column_type_is_an_error():
    with pytest.raises(ValueError, match="no payload"):
        schema.column_body({"schema": "jc_X", "display": "X", "type": "image"}, 1)


# ---------- column security ----------


def test_read_profile_lets_requesters_read_everything_and_write_nothing():
    rows = {r["attributelogicalname"]: r for r in schema.permissions(schema.READ_PROFILE)}
    assert rows.keys() == SECURED
    assert all(r["canread"] == schema.ALLOWED and r["canupdate"] == schema.NOT_ALLOWED for r in rows.values())
    # Course is the one column a requester may set, and only when creating the request.
    assert {name for name, r in rows.items() if r["cancreate"] == schema.ALLOWED} == {"jc_course"}


def test_write_profile_allows_everything():
    rows = schema.permissions(schema.WRITE_PROFILE)
    assert len(rows) == len(SECURED)
    assert all(r["canread"] == r["cancreate"] == r["canupdate"] == schema.ALLOWED for r in rows)


def test_plan_lists_every_column():
    plan = "\n".join(schema.plan_lines())
    for name in COURSE.keys() | REQUEST.keys():
        assert name in plan
    assert "set on create only" in plan and "(10 field permissions)" in plan
    assert "Needs Attention" in plan


# ---------- views ----------

CHOICES = {"Request Status": {label: 123450000 + i for i, label in enumerate(REQUEST["jc_requeststatus"]["options"])}}
SYSTEM_COLUMNS = {"ownerid", "modifiedon"}


def parsed(view_name: str) -> tuple[ET.Element, ET.Element]:
    view = next(v for v in schema.VIEWS if v["name"] == view_name)
    body = schema.view_body(view, 10321, CHOICES)
    return ET.fromstring(body["fetchxml"]), ET.fromstring(body["layoutxml"])  # noqa: S314 (our own strings)


def test_views_match_the_ones_schema_md_lists():
    text = (DOCS / "schema.md").read_text(encoding="utf-8")
    for view in schema.VIEWS:
        assert f"**{view['name']}**" in text


@pytest.mark.parametrize("view", schema.VIEWS, ids=lambda v: v["name"])
def test_view_xml_is_well_formed_and_uses_real_columns(view):
    known = (COURSE if view["table"] == "jc_trainingcourse" else REQUEST).keys() | SYSTEM_COLUMNS
    fetch, layout = parsed(view["name"])
    assert fetch.find("entity").get("name") == view["table"]
    fetched = {a.get("name") for a in fetch.iter("attribute")}
    assert set(view["columns"]) <= fetched and f"{view['table']}id" in fetched
    assert fetched - {f"{view['table']}id"} <= known
    assert {c.get("attribute") for c in fetch.iter("condition")} <= known
    assert [c.get("name") for c in layout.iter("cell")] == view["columns"]
    assert layout.get("object") == "10321"
    assert layout.find("row").get("id") == f"{view['table']}id"


def test_pending_view_filters_on_the_submitted_value_oldest_first():
    fetch, _ = parsed("Pending Requests")
    (condition,) = fetch.iter("condition")
    assert (condition.get("attribute"), condition.get("value")) == ("jc_requeststatus", "123450001")
    assert fetch.find("entity/order").get("descending") == "false"


def test_needs_attention_is_error_or_a_stale_command():
    fetch, _ = parsed("Needs Attention")
    top = fetch.find("entity/filter")
    assert top.get("type") == "or"
    assert top.find("condition").get("value") == str(CHOICES["Request Status"]["Error"])
    nested = top.find("filter")
    assert nested.get("type") == "and"
    assert [(c.get("attribute"), c.get("operator"), c.get("value")) for c in nested] == [
        ("jc_requestedaction", "not-null", None),
        ("modifiedon", "olderthan-x-hours", "1"),
    ]


# ---------- create-unless-exists against a fake Web API ----------


class Response:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code, self._payload, self.headers = status, payload or {}, headers or {}
        self.ok = status < 400
        self.text = "" if self.ok else "error"

    def json(self):
        return self._payload


class FakeDataverse:
    """Remembers what has been created, the way the real service would."""

    def __init__(self):
        self.rows = {
            "publishers": [],
            "solutions": [],
            "savedqueries": [],
            "fieldsecurityprofiles": [],
            "fieldpermissions": [],
        }
        self.tables: dict[str, set[str]] = {}
        self.posts: list[tuple[str, dict, dict]] = []

    def request(self, method, url, json=None, headers=None, timeout=None):
        assert url.startswith(API) and timeout
        path = url[len(API) + 1 :]
        if method == "POST":
            return self.post(path, json, headers or {})
        entity = re.match(r"EntityDefinitions\(LogicalName='(\w+)'\)(?:/Attributes\(LogicalName='(\w+)'\))?", path)
        if entity:
            table, column = entity.groups()
            found = table in self.tables and (column is None or column in self.tables[table])
            return Response(200 if found else 404)
        rows = self.rows[path.split("?")[0]]
        wanted = re.search(r"\$filter=(\w+) eq '?([^'&]+)'?", path)
        if wanted:
            key, value = wanted.groups()
            rows = [r for r in rows if str(r.get(key)) == value]
        return Response(payload={"value": list(rows)})

    def post(self, path, body, headers):
        self.posts.append((path, body, headers))
        if path == "EntityDefinitions":
            self.tables[body["SchemaName"].lower()] = {body["Attributes"][0]["SchemaName"].lower()}
        elif path == "RelationshipDefinitions":
            self.tables[body["ReferencingEntity"]].add(body["Lookup"]["SchemaName"].lower())
        elif path.endswith("/Attributes"):
            self.tables[re.search(r"'(\w+)'", path).group(1)].add(body["SchemaName"].lower())
        elif path in self.rows:
            new_id = f"{path}-{len(self.rows[path]) + 1}"
            id_column = {"publishers": "publisherid", "fieldsecurityprofiles": "fieldsecurityprofileid"}.get(path)
            row = body | ({id_column: new_id} if id_column else {})
            if path == "fieldpermissions":
                row["_fieldsecurityprofileid_value"] = body["fieldsecurityprofileid@odata.bind"].split("(")[1][:-1]
            self.rows[path].append(row)
            return Response(headers={"OData-EntityId": f"{API}/{path}({new_id})"})
        return Response()


def run(session, option_prefix=12345) -> schema.Builder:
    dv = seed.Dataverse.__new__(seed.Dataverse)
    dv.env, dv.api, dv.session = "https://org.crm.dynamics.com", API, session
    build = schema.Builder(dv)
    publisher_id, prefix = build.publisher(option_prefix)
    build.solution(publisher_id)
    for table in schema.TABLES:
        build.table(table, prefix)
    return build


def test_first_run_creates_the_whole_model(capsys):
    session = FakeDataverse()
    build = run(session)
    assert session.tables == {"jc_trainingcourse": set(COURSE), "jc_trainingrequest": set(REQUEST)}
    # publisher + solution + 2 tables + every non-primary column
    assert build.created == 4 + len(COURSE) + len(REQUEST) - 2
    assert build.skipped == 0
    assert "created  table jc_trainingrequest" in capsys.readouterr().out


def test_second_run_creates_nothing():
    session = FakeDataverse()
    run(session)
    posts_after_first = len(session.posts)
    again = run(session)
    assert len(session.posts) == posts_after_first
    assert again.created == 0 and again.skipped > 0


def test_interrupted_run_resumes_where_it_stopped():
    session = FakeDataverse()
    run(session)
    session.tables["jc_trainingrequest"] -= {"jc_completedon", "jc_approver"}
    resumed = run(session)
    assert resumed.created == 2
    assert session.tables["jc_trainingrequest"] == set(REQUEST)


def test_components_are_created_inside_the_solution():
    session = FakeDataverse()
    run(session)
    for path, _, headers in session.posts:
        expected = {} if path in ("publishers", "solutions") else {"MSCRM.SolutionUniqueName": "TrainingRequests"}
        assert headers == expected, path


def test_existing_publisher_decides_the_option_prefix():
    session = FakeDataverse()
    session.rows["publishers"].append(
        {
            "publisherid": "p-1",
            "uniquename": "someoneelse",
            "customizationprefix": "jc",
            "customizationoptionvalueprefix": 77777,
        }
    )
    run(session, option_prefix=12345)
    status = next(b for p, b, _ in session.posts if b.get("SchemaName") == "jc_RequestStatus")
    assert status["OptionSet"]["Options"][0]["Value"] == 777770000
    assert not [p for p, _, _ in session.posts if p == "publishers"]


def test_profiles_get_one_permission_per_secured_column():
    session = FakeDataverse()
    build = run(session)
    for name in (schema.READ_PROFILE, schema.WRITE_PROFILE):
        build.profile(name)
    assert [p["name"] for p in session.rows["fieldsecurityprofiles"]] == [schema.READ_PROFILE, schema.WRITE_PROFILE]
    assert len(session.rows["fieldpermissions"]) == 2 * len(SECURED)
    # Running again adds nothing.
    for name in (schema.READ_PROFILE, schema.WRITE_PROFILE):
        build.profile(name)
    assert len(session.rows["fieldpermissions"]) == 2 * len(SECURED)
    assert len(session.rows["fieldsecurityprofiles"]) == 2
    assert all("fieldsecurityprofileid@odata.bind" in p for p in session.rows["fieldpermissions"])


def test_views_are_created_once():
    session = FakeDataverse()
    build = run(session)
    for _ in range(2):
        for view in schema.VIEWS:
            build.view(view, 10321, CHOICES)
    assert [v["name"] for v in session.rows["savedqueries"]] == [v["name"] for v in schema.VIEWS]
    view_posts = [h for p, _, h in session.posts if p == "savedqueries"]
    assert view_posts == [{"MSCRM.SolutionUniqueName": "TrainingRequests"}] * len(schema.VIEWS)


def test_failed_call_stops_with_the_service_message():
    class Broken(FakeDataverse):
        def post(self, path, body, headers):
            return Response(400)

    with pytest.raises(RuntimeError, match="POST publishers -> 400"):
        run(Broken())
