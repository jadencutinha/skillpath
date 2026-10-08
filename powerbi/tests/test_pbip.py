"""Checks on the generated Power BI project that don't need Power BI Desktop."""

import json
import re
from pathlib import Path

import pytest

import build_pbip as pbip

HERE = Path(pbip.__file__).parent
MODEL = f"{pbip.NAME}.SemanticModel/definition"


@pytest.fixture(scope="module")
def files() -> dict[str, str]:
    return pbip.build()


def table(files, name: str) -> str:
    return files[f"{MODEL}/tables/{name}.tmdl"]


def test_committed_project_matches_the_source_files(files):
    for path, content in files.items():
        assert (HERE / path).read_text(encoding="utf-8") == content, f"{path} is stale: run powerbi/build_pbip.py"


def test_json_files_parse_and_point_at_each_other(files):
    project = json.loads(files[f"{pbip.NAME}.pbip"])
    report_dir = project["artifacts"][0]["report"]["path"]
    reference = json.loads(files[f"{report_dir}/definition.pbir"])["datasetReference"]["byPath"]["path"]
    assert (HERE / report_dir / reference).resolve() == (HERE / f"{pbip.NAME}.SemanticModel").resolve()
    assert json.loads(files[f"{pbip.NAME}.SemanticModel/definition.pbism"])["version"] == "4.0"
    report = json.loads(files[f"{report_dir}/report.json"])
    json.loads(report["config"])
    assert [s["displayName"] for s in report["sections"]] == ["Overview"]


def test_every_measure_in_measures_dax_is_in_the_model(files):
    source = pbip.parse_measures(pbip.read("measures.dax"))
    assert len(source) == 16
    fact = table(files, "Training Request")
    for name, expression in source.items():
        assert f"\tmeasure '{name}' = ```" in fact or f"\tmeasure {name} = ```" in fact, name
        for line in expression.splitlines():
            assert line.rstrip() in fact, (name, line)
    assert set(pbip.FORMATS) <= source.keys()


def test_measures_only_reference_measures_and_columns_that_exist(files):
    source = pbip.parse_measures(pbip.read("measures.dax"))
    columns = {t: {c for c, *_ in cols} for t, cols in pbip.COLUMNS.items()}
    columns["Date"] = {c for c, *_ in pbip.DATE_COLUMNS}
    for name, expression in source.items():
        code = re.sub(r"//[^\n]*", "", expression)
        for tbl, column in re.findall(r"'([^']+)'\[([^\]]+)\]", code):
            assert column in columns[tbl], f"{name}: {tbl}[{column}]"
        for measure in re.findall(r"(?<![\w'\]])\[([^\]]+)\]", code):
            assert measure in source, f"{name}: [{measure}]"


def test_declared_columns_are_produced_by_the_queries():
    queries = pbip.parse_queries(pbip.read("queries.pq"))
    assert queries.keys() == pbip.COLUMNS.keys()
    for name, columns in pbip.COLUMNS.items():
        for column, *_ in columns:
            assert f'"{column}"' in queries[name], f"{name}: {column}"


def test_date_columns_match_date_table_dax():
    expression = pbip.parse_date_table(pbip.read("date-table.dax"))
    added = re.findall(r'^\s+"(\w+)", ', expression, re.M)
    assert ["Date", *added] == [c for c, *_ in pbip.DATE_COLUMNS]


def test_queries_use_the_parameters_not_a_placeholder_host(files):
    expressions = files[f"{MODEL}/expressions.tmdl"]
    assert "expression DataverseHost = " in expressions
    assert "expression ReportingUtcOffsetHours = -5 meta" in expressions
    for name in pbip.COLUMNS:
        body = table(files, name)
        assert "CommonDataService.Database(DataverseHost)" in body
        assert "<org>" not in body
    assert "ReportingUtcOffsetHours" in table(files, "Training Request")


def test_relationships_join_existing_columns_and_only_one_is_inactive(files):
    columns = {t: {c for c, *_ in cols} for t, cols in pbip.COLUMNS.items()}
    columns["Date"] = {c for c, *_ in pbip.DATE_COLUMNS}
    for _, (many_table, many_column), (one_table, one_column), _ in pbip.RELATIONSHIPS:
        assert many_column in columns[many_table] and one_column in columns[one_table]
    text = files[f"{MODEL}/relationships.tmdl"]
    assert text.count("isActive: false") == 1
    assert "relationship RequestDecisionDay\n\tisActive: false" in text


def test_security_roles(files):
    team = files[f"{MODEL}/roles/Own and team requests.tmdl"]
    assert "tablePermission Requester = ```" in team and "PATHCONTAINS" in team and "USERPRINCIPALNAME" in team
    everything = files[f"{MODEL}/roles/All requests.tmdl"]
    assert "tablePermission" not in everything
    assert "column 'Hierarchy Path' = ```" in table(files, "Requester")
    model = files[f"{MODEL}/model.tmdl"]
    for role in pbip.ROLES:
        assert f"ref role '{role}'" in model


def test_model_references_every_table_file(files):
    model = files[f"{MODEL}/model.tmdl"]
    on_disk = {Path(p).stem for p in files if "/tables/" in p}
    referenced = {m.strip("'") for m in re.findall(r"^ref table (.+)$", model, re.M)}
    assert referenced == on_disk == {*pbip.COLUMNS, "Date"}


def test_tmdl_is_tab_indented_with_balanced_fences(files):
    for path, content in files.items():
        if not path.endswith(".tmdl"):
            continue
        assert content.count("```") % 2 == 0, path
        inside = False
        for line in content.splitlines():
            if line.strip() == "```":
                inside = False
                continue
            if not inside:
                # Structure lines are indented with tabs only.
                assert not re.match(r"\t* +\S", line), (path, line)
            if line.rstrip().endswith("= ```"):
                inside = True


def test_keys_are_hidden_and_date_table_is_marked(files):
    fact = table(files, "Training Request")
    for key in ("Request ID", "Course ID", "Requester ID", "Submitted Date", "Decision Day"):
        assert re.search(rf"\tcolumn '{key}'\n\t\tdataType: \w+\n(?:\t\t.*\n)*?\t\tisHidden", fact), key
    date = table(files, "Date")
    assert "dataCategory: Time" in date and "isKey" in date and "sortByColumn: MonthNum" in date
    assert "partition Date = calculated" in date
