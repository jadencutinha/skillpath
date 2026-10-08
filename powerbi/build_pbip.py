"""Assemble a Power BI Project (.pbip) from the query, measure and security files in this folder.

    python powerbi/build_pbip.py

Writes TrainingRequests.pbip plus the TrainingRequests.SemanticModel and TrainingRequests.Report
folders. Open the .pbip in Power BI Desktop and the model is already there: three queries, the
Date table, four relationships, every measure with its format, the hierarchy column, and both
row-level security roles. What is left is entering your environment host, refreshing, and laying
out the visuals (model.md, section 3).

The .pq and .dax files stay the single source: this script reads them, it does not copy them by
hand. Edit a measure in measures.dax, run this again, and the project follows.

The semantic model is written in TMDL, the text format Desktop uses for projects.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).parent
NAME = "TrainingRequests"
TAB = "\t"

CURRENCY = r"\$#,0;(\$#,0);\$#,0"

# Columns each query produces, as (name, TMDL data type, extra property lines).
HIDDEN_KEY = ["isHidden", "summarizeBy: none"]
TEXT = ["summarizeBy: none"]
COLUMNS = {
    "Training Request": [
        ("Request ID", "string", HIDDEN_KEY),
        ("Title", "string", TEXT),
        ("Course ID", "string", HIDDEN_KEY),
        ("Requester ID", "string", HIDDEN_KEY),
        ("Request Status", "string", TEXT),
        ("Pending With", "string", TEXT),
        ("Submitted On", "dateTime", ["formatString: General Date", "summarizeBy: none"]),
        ("Decision Date", "dateTime", ["formatString: General Date", "summarizeBy: none"]),
        ("Completed On", "dateTime", ["formatString: General Date", "summarizeBy: none"]),
        ("Course Cost", "decimal", [f"formatString: {CURRENCY}", "summarizeBy: sum"]),
        ("Submitted Date", "dateTime", ["formatString: Short Date", *HIDDEN_KEY]),
        ("Decision Day", "dateTime", ["formatString: Short Date", *HIDDEN_KEY]),
    ],
    "Training Course": [
        ("Course ID", "string", HIDDEN_KEY),
        ("Course", "string", TEXT),
        ("Provider", "string", TEXT),
        ("Category", "string", TEXT),
        ("Cost", "decimal", [f"formatString: {CURRENCY}", "summarizeBy: none"]),
        ("Hours", "int64", ["formatString: 0", "summarizeBy: none"]),
        ("Active", "boolean", TEXT),
    ],
    "Requester": [
        ("User ID", "string", HIDDEN_KEY),
        ("Requester", "string", TEXT),
        ("UPN", "string", HIDDEN_KEY),
        ("Manager ID", "string", HIDDEN_KEY),
    ],
}

# Columns of the calculated Date table, in the order date-table.dax adds them.
DATE_COLUMNS = [
    ("Date", "dateTime", ["isKey", "formatString: Short Date", "summarizeBy: none"]),
    ("Year", "int64", ["formatString: 0", "summarizeBy: none"]),
    ("Quarter", "string", TEXT),
    ("Month", "string", ["summarizeBy: none", "sortByColumn: MonthNum"]),
    ("MonthNum", "int64", ["isHidden", "formatString: 0", "summarizeBy: none"]),
    ("Weekday", "string", TEXT),
]

FORMATS = {
    "Approval Rate": "0%",
    "Completion Rate": "0%",
    "Approval Rate vs Prior Month": "+0%;-0%;0%",
    "Approved Spend": CURRENCY,
    "Pending Spend": CURRENCY,
    "Avg Days to Decision": "0.0",
}
DEFAULT_FORMAT = "#,0"  # every other measure is a count

# (name, many side, one side, active)
RELATIONSHIPS = [
    ("RequestCourse", ("Training Request", "Course ID"), ("Training Course", "Course ID"), True),
    ("RequestRequester", ("Training Request", "Requester ID"), ("Requester", "User ID"), True),
    ("RequestSubmittedDate", ("Training Request", "Submitted Date"), ("Date", "Date"), True),
    ("RequestDecisionDay", ("Training Request", "Decision Day"), ("Date", "Date"), False),
]

ROLES = ["Own and team requests", "All requests"]
HOST_PLACEHOLDER = '"<org>.crm.dynamics.com"'


# ---------- reading the source files ----------


def read(name: str) -> str:
    return (HERE / name).read_text(encoding="utf-8")


def parse_measures(text: str) -> dict[str, str]:
    """Split measures.dax into {name: expression}. A measure starts with an unindented 'Name ='."""
    measures: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        start = re.fullmatch(r"([A-Za-z][^=/]*?) =", line)
        if start:
            current = start.group(1)
            measures[current] = []
        elif current is not None:
            measures[current].append(line)
    return {name: "\n".join(body).strip() for name, body in measures.items()}


def parse_queries(text: str) -> dict[str, str]:
    """Split queries.pq into {query name: M expression} using its '// ---------- Query: Name (' markers."""
    parts = re.split(r"^// -{10} Query: (.+?) \(.*$", text, flags=re.M)
    return {name: body.strip() for name, body in zip(parts[1::2], parts[2::2], strict=True)}


def parse_parameter(text: str) -> str:
    return re.search(r"^(-?\d+ meta \[IsParameterQuery.*\])$", text, re.M).group(1)


def parse_date_table(text: str) -> str:
    body = text.split("Date =\n", 1)[1]
    return body.split("\n// Column tools", 1)[0].strip()


def parse_security(text: str) -> tuple[str, str]:
    """Return (Hierarchy Path column expression, role filter) from rls.dax."""
    path = re.search(r"^Hierarchy Path =\n(.+?)\n\n", text, re.S | re.M).group(1).strip()
    role = re.search(r"^(VAR Me =\n.+?PATHCONTAINS[^\n]*)$", text, re.S | re.M).group(1).strip()
    return path, role


# ---------- writing TMDL ----------


def quote(name: str) -> str:
    """TMDL object names need single quotes unless they are a plain word."""
    return name if re.fullmatch(r"\w+", name) else "'" + name.replace("'", "''") + "'"


def block(expression: str, depth: int) -> list[str]:
    """A multi-line expression, fenced with ``` so blank lines and comments survive."""
    pad = TAB * (depth + 2)
    return ["```", *[(pad + line).rstrip() for line in expression.splitlines()], pad + "```"]


def column_lines(name: str, data_type: str, extras: list[str], *, source: str | None, expression: str | None = None):
    head = f"{TAB}column {quote(name)}"
    lines = [head] if expression is None else [f"{head} = " + block(expression, 1)[0], *block(expression, 1)[1:]]
    lines.append(f"{TAB}{TAB}dataType: {data_type}")
    lines += [f"{TAB}{TAB}{extra}" for extra in extras]
    if source is not None:
        lines.append(f"{TAB}{TAB}sourceColumn: {source}")
    return [*lines, ""]


def partition_lines(name: str, kind: str, expression: str) -> list[str]:
    fenced = block(expression, 1)
    return [
        f"{TAB}partition {quote(name)} = {kind}",
        f"{TAB}{TAB}mode: import",
        f"{TAB}{TAB}source = {fenced[0]}",
        *fenced[1:],
        "",
    ]


def measure_lines(name: str, expression: str) -> list[str]:
    fenced = block(expression, 1)
    return [
        f"{TAB}measure {quote(name)} = {fenced[0]}",
        *fenced[1:],
        f"{TAB}{TAB}formatString: {FORMATS.get(name, DEFAULT_FORMAT)}",
        "",
    ]


def table_tmdl(name: str, queries: dict[str, str], measures: dict[str, str], hierarchy_path: str) -> str:
    lines = [f"table {quote(name)}", ""]
    if name == "Training Request":
        # Measures have to live on a table. Keeping them on the fact avoids an empty holder table.
        for measure, expression in measures.items():
            lines += measure_lines(measure, expression)
    for column, data_type, extras in COLUMNS[name]:
        lines += column_lines(column, data_type, extras, source=column)
    if name == "Requester":
        lines += column_lines("Hierarchy Path", "string", HIDDEN_KEY, source=None, expression=hierarchy_path)
    query = queries[name].replace(HOST_PLACEHOLDER, "DataverseHost")
    lines += partition_lines(name, "m", query)
    return "\n".join(lines).rstrip() + "\n"


def date_tmdl(expression: str) -> str:
    lines = ["table Date", f"{TAB}dataCategory: Time", ""]
    for column, data_type, extras in DATE_COLUMNS:
        lines += column_lines(column, data_type, ["isNameInferred", *extras], source=f"[{column}]")
    lines += partition_lines("Date", "calculated", expression)
    return "\n".join(lines).rstrip() + "\n"


def relationships_tmdl() -> str:
    lines = []
    for name, (many_table, many_column), (one_table, one_column), active in RELATIONSHIPS:
        lines.append(f"relationship {name}")
        if not active:
            lines.append(f"{TAB}isActive: false")
        lines += [
            f"{TAB}fromColumn: {quote(many_table)}.{quote(many_column)}",
            f"{TAB}toColumn: {quote(one_table)}.{quote(one_column)}",
            "",
        ]
    return "\n".join(lines).rstrip() + "\n"


def expressions_tmdl(parameter: str) -> str:
    return (
        "/// Your environment host, without https://. Set it under Transform data > Manage parameters.\n"
        f"expression DataverseHost = {HOST_PLACEHOLDER} "
        'meta [IsParameterQuery=true, Type="Text", IsParameterQueryRequired=true]\n\n'
        "/// Hours to add to Dataverse's UTC timestamps so requests land on the right calendar day.\n"
        f"expression ReportingUtcOffsetHours = {parameter}\n"
    )


def role_tmdl(name: str, role_filter: str | None) -> str:
    lines = [f"role {quote(name)}", f"{TAB}modelPermission: read"]
    if role_filter:
        fenced = block(role_filter, 1)
        lines += ["", f"{TAB}tablePermission Requester = {fenced[0]}", *fenced[1:]]
    return "\n".join(lines) + "\n"


def model_tmdl() -> str:
    tables = [*COLUMNS, "Date"]
    lines = [
        "model Model",
        f"{TAB}culture: en-US",
        f"{TAB}defaultPowerBIDataSourceVersion: powerBI_V3",
        f"{TAB}sourceQueryCulture: en-US",
        "",
        *[f"ref table {quote(t)}" for t in tables],
        "",
        *[f"ref role {quote(r)}" for r in ROLES],
    ]
    return "\n".join(lines) + "\n"


# ---------- the project ----------


def dump(data: dict) -> str:
    return json.dumps(data, indent=2) + "\n"


def build() -> dict[str, str]:
    """Every file of the project, keyed by path relative to this folder."""
    measures = parse_measures(read("measures.dax"))
    queries = parse_queries(read("queries.pq"))
    parameter = parse_parameter(read("queries.pq"))
    hierarchy_path, role_filter = parse_security(read("rls.dax"))

    model = f"{NAME}.SemanticModel"
    report = f"{NAME}.Report"
    files = {
        f"{NAME}.pbip": dump(
            {"version": "1.0", "artifacts": [{"report": {"path": report}}], "settings": {"enableAutoRecovery": True}}
        ),
        f"{model}/definition.pbism": dump({"version": "4.0", "settings": {}}),
        f"{model}/definition/database.tmdl": f"database {NAME}\n{TAB}compatibilityLevel: 1567\n",
        f"{model}/definition/model.tmdl": model_tmdl(),
        f"{model}/definition/expressions.tmdl": expressions_tmdl(parameter),
        f"{model}/definition/relationships.tmdl": relationships_tmdl(),
        f"{model}/definition/tables/Date.tmdl": date_tmdl(parse_date_table(read("date-table.dax"))),
        f"{model}/definition/roles/{ROLES[0]}.tmdl": role_tmdl(ROLES[0], role_filter),
        f"{model}/definition/roles/{ROLES[1]}.tmdl": role_tmdl(ROLES[1], None),
        f"{report}/definition.pbir": dump({"version": "1.0", "datasetReference": {"byPath": {"path": f"../{model}"}}}),
        # One empty page. Visuals are laid out in Desktop (model.md, section 3).
        f"{report}/report.json": dump(
            {
                "config": json.dumps({"version": "5.37", "themeCollection": {}}),
                "layoutOptimization": 0,
                "sections": [
                    {
                        "name": "ReportSection",
                        "displayName": "Overview",
                        "displayOption": 1,
                        "width": 1280,
                        "height": 720,
                        "config": "{}",
                        "filters": "[]",
                        "visualContainers": [],
                    }
                ],
            }
        ),
    }
    for table in COLUMNS:
        files[f"{model}/definition/tables/{table}.tmdl"] = table_tmdl(table, queries, measures, hierarchy_path)
    return files


if __name__ == "__main__":
    for path, content in sorted(build().items()):
        target = HERE / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"wrote {path}")
