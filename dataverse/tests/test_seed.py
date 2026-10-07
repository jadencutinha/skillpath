"""Offline tests for the seed script: the CSVs themselves, the payloads built from
them, and the paging / reset logic against a fake Web API."""

import copy

import pytest

import seed_dataverse as seed

API = "https://org.crm.dynamics.com/api/data/v9.2"


@pytest.fixture(scope="module")
def courses():
    return seed.read_csv("courses.csv")


@pytest.fixture(scope="module")
def reqs():
    return seed.read_csv("requests.csv")


# ---------- the seed files ----------


def test_seed_files_are_valid(courses, reqs):
    assert seed.validate_seed(courses, reqs) == []


def test_seed_covers_every_status_and_category(courses, reqs):
    # The dashboard and the app's status colours are only demonstrable if each value appears.
    assert {r["status"] for r in reqs} == seed.STATUSES
    assert {c["category"] for c in courses} == seed.CATEGORIES
    assert any(c["active"] == "false" for c in courses)


def test_seed_exercises_the_second_approval_path(courses, reqs):
    costs = {c["name"]: float(c["cost"]) for c in courses}
    assert any(costs[r["course"]] > seed.JUSTIFICATION_THRESHOLD for r in reqs)


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        ({"course": "No Such Course"}, "is not in courses.csv"),
        ({"status": "Aproved"}, "unknown status"),
        ({"status": "Draft"}, "submitted_on must be set for every status except Draft"),
        ({"status": "Submitted"}, "decision_date must be set only for"),
        ({"decision_date": "2025-01-01T00:00:00Z"}, "decision_date is before submitted_on"),
        ({"submitted_on": "06/01/2026"}, "must look like"),
        ({"status": "Completed"}, "completed_on must be set only for Completed"),
        ({"completed_on": "2026-12-01T00:00:00Z"}, "completed_on must be set only for Completed"),
        ({"title": " "}, "title is empty"),
    ],
)
def test_validation_reports_bad_requests(courses, reqs, change, expected):
    approved = next(r for r in reqs if r["status"] == "Approved")
    broken = {**approved, **change}
    errors = seed.validate_seed(courses, [broken])
    assert any(expected in e for e in errors), errors


def test_validation_requires_justification_for_expensive_courses(courses, reqs):
    costs = {c["name"]: float(c["cost"]) for c in courses}
    expensive = next(r for r in reqs if costs[r["course"]] > seed.JUSTIFICATION_THRESHOLD)
    errors = seed.validate_seed(courses, [{**expensive, "justification": ""}])
    assert any("justification is required" in e for e in errors)


def test_validation_reports_duplicates_and_bad_courses(courses, reqs):
    bad_courses = copy.deepcopy(courses[:2])
    bad_courses[1].update(name=bad_courses[0]["name"], cost="-5", hours="0", active="yes", category="Fun")
    errors = seed.validate_seed(bad_courses, [reqs[0], reqs[0]])
    for expected in (
        "duplicate course name",
        "cost must be",
        "hours must be",
        "active must be",
        "unknown category",
    ):
        assert any(expected in e for e in errors), (expected, errors)
    assert any("duplicate title" in e for e in errors)


# ---------- payloads ----------

STATUS_VALUES = {label: 100 + i for i, label in enumerate(sorted(seed.STATUSES))}


def build(r):
    return seed.request_body(
        r,
        statuses=STATUS_VALUES,
        course_ref="/jc_trainingcourses(c-1)",
        course_cost=165.0,
        course_nav="jc_Course",
        approver_nav="jc_Approver",
        approver_id="u-1",
        approver_email="me@example.com",
        now="2026-10-01T00:00:00Z",
    )


def by_status(reqs, status):
    return next(r for r in reqs if r["status"] == status)


def test_course_body(courses):
    body = seed.course_body(courses[0], {c: i for i, c in enumerate(sorted(seed.CATEGORIES))})
    assert body["jc_name"] == courses[0]["name"]
    assert isinstance(body["jc_cost"], float) and isinstance(body["jc_hours"], int)
    assert body["jc_active"] is True


def test_decided_request_body(reqs):
    r = by_status(reqs, "Completed")
    body = build(r)
    assert body["jc_requeststatus"] == STATUS_VALUES["Completed"]
    assert body["jc_Course@odata.bind"] == "/jc_trainingcourses(c-1)"
    assert body["jc_Approver@odata.bind"] == "/systemusers(u-1)"
    assert body["jc_coursecost"] == 165.0
    assert body["jc_decisiondate"] == r["decision_date"]
    assert body["jc_completedon"] == r["completed_on"]
    assert body["overriddencreatedon"] == r["submitted_on"]
    assert "jc_pendingwith" not in body


def test_draft_body_has_no_approver_or_dates(reqs):
    body = build(by_status(reqs, "Draft"))
    assert "jc_Approver@odata.bind" not in body
    assert not {"jc_submittedon", "jc_decisiondate", "jc_completedon", "jc_pendingwith"} & body.keys()
    assert body["overriddencreatedon"] == "2026-10-01T00:00:00Z"


def test_submitted_body_is_pending_with_the_approver(reqs):
    assert build(by_status(reqs, "Submitted"))["jc_pendingwith"] == "me@example.com"


def test_seeding_never_issues_a_command(reqs):
    # Requested Action is what triggers the flows; seeding must not start approvals.
    assert all("jc_requestedaction" not in build(r) for r in reqs)


# ---------- Web API behaviour ----------


class FakeResponse:
    ok = True
    status_code = 200
    text = ""

    def __init__(self, payload=None, ok=True):
        self._payload = payload or {}
        self.ok = ok
        if not ok:
            self.status_code, self.text = 400, "DeleteRestricted"

    def json(self):
        return self._payload


class FakeSession:
    """Serves two tables, two rows per page, and records deletes."""

    def __init__(self, tables, undeletable=()):
        self.tables = tables
        self.undeletable = set(undeletable)
        self.deleted = []
        self.gets = 0

    def request(self, method, url, **kwargs):
        assert url.startswith(API), url
        assert kwargs.get("timeout"), "every request needs a timeout"
        path = url[len(API) + 1 :]
        if method == "DELETE":
            row_id = path.split("(")[1].rstrip(")")
            if row_id in self.undeletable:
                return FakeResponse(ok=False)
            self.deleted.append(row_id)
            return FakeResponse()
        self.gets += 1
        table, _, query = path.partition("?")
        skip = int(query.split("skip=")[1]) if "skip=" in query else 0
        rows = self.tables[table][skip : skip + 2]
        page = {"value": rows}
        if skip + 2 < len(self.tables[table]):
            page["@odata.nextLink"] = f"{API}/{table}?skip={skip + 2}"
        return FakeResponse(page)


def fake_dataverse(session):
    dv = seed.Dataverse.__new__(seed.Dataverse)
    dv.env, dv.api, dv.session = "https://org.crm.dynamics.com", API, session
    return dv


SETS = {"course": "courses", "request": "requests", "course_id": "id", "request_id": "id"}


def test_get_all_follows_next_links():
    rows = [{"id": str(i)} for i in range(5)]
    session = FakeSession({"requests": rows})
    assert fake_dataverse(session).get_all("requests?$select=id") == rows
    assert session.gets == 3


def test_failed_request_raises_with_status():
    dv = fake_dataverse(FakeSession({}, undeletable={"x"}))
    with pytest.raises(RuntimeError, match="DELETE .* -> 400: DeleteRestricted"):
        dv.delete("courses", "x")


def test_reset_deletes_only_seeded_rows(capsys):
    session = FakeSession(
        {
            "requests": [
                {"id": "r-seed", "jc_title": "Seeded"},
                {"id": "r-seed-dup", "jc_title": "Seeded"},
                {"id": "r-real", "jc_title": "Created in the app"},
            ],
            "courses": [
                {"id": "c-seed", "jc_name": "Seed course"},
                {"id": "c-used", "jc_name": "Seed course in use"},
                {"id": "c-real", "jc_name": "Added by an admin"},
            ],
        },
        undeletable={"c-used"},
    )
    seed.reset(
        fake_dataverse(session),
        "https://org.crm.dynamics.com",
        SETS,
        courses=[{"name": "Seed course"}, {"name": "Seed course in use"}, {"name": "Not loaded yet"}],
        reqs=[{"title": "Seeded"}],
        assume_yes=True,
    )
    assert session.deleted == ["r-seed", "r-seed-dup", "c-seed"]
    out = capsys.readouterr().out
    assert "Deleted 2 requests and 1 courses" in out
    assert "Kept 1 courses" in out


def test_reset_with_nothing_seeded_does_not_prompt(capsys):
    session = FakeSession({"requests": [{"id": "r-real", "jc_title": "Created in the app"}], "courses": []})
    seed.reset(fake_dataverse(session), "https://org.crm.dynamics.com", SETS, [], [{"title": "Seeded"}], False)
    assert session.deleted == []
    assert "Nothing to reset" in capsys.readouterr().out


def test_reset_refuses_without_confirmation_when_not_interactive(monkeypatch):
    class NotATerminal:
        def isatty(self):
            return False

    monkeypatch.setattr(seed.sys, "stdin", NotATerminal())
    with pytest.raises(SystemExit, match="Refusing to delete"):
        seed.confirm_reset("https://org.crm.dynamics.com", 3, 2, assume_yes=False)


def test_reset_confirmation_must_match_the_host(monkeypatch):
    class Terminal:
        def isatty(self):
            return True

    monkeypatch.setattr(seed.sys, "stdin", Terminal())
    monkeypatch.setattr("builtins.input", lambda _: "yes")
    with pytest.raises(SystemExit, match="Host did not match"):
        seed.confirm_reset("https://org.crm.dynamics.com", 3, 2, assume_yes=False)
    monkeypatch.setattr("builtins.input", lambda _: "ORG.crm.dynamics.com ")
    seed.confirm_reset("https://org.crm.dynamics.com", 3, 2, assume_yes=False)


@pytest.mark.parametrize(
    "url", ["http://org.crm.dynamics.com", "org.crm.dynamics.com", "https://org.crm.dynamics.com/api"]
)
def test_env_url_is_validated(url):
    with pytest.raises(SystemExit, match="--env must look like"):
        seed.normalise_env(url)


def test_env_url_is_normalised():
    assert seed.normalise_env("https://Org.crm.dynamics.com/") == "https://org.crm.dynamics.com"
