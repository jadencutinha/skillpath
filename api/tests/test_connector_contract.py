"""The custom connector's Swagger 2.0 file is written by hand (connectors don't accept
OpenAPI 3). These tests fail when it drifts from what the API actually serves."""

import json
from pathlib import Path

import pytest

from app.main import MAX_COST, MAX_HOURS, app

SWAGGER_PATH = Path(__file__).resolve().parents[2] / "connector" / "apiDefinition.swagger.json"


@pytest.fixture(scope="module")
def swagger() -> dict:
    return json.loads(SWAGGER_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def openapi() -> dict:
    return app.openapi()


def resolve(schema: dict, openapi: dict) -> dict:
    """Follow a local $ref in the generated OpenAPI 3 document."""
    while "$ref" in schema:
        node = openapi
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        schema = node
    return schema


def test_same_paths_and_operation_ids(swagger, openapi):
    def operations(doc):
        return {
            (path, method): op.get("operationId") for path, item in doc["paths"].items() for method, op in item.items()
        }

    documented = operations(swagger)
    served = operations(openapi)
    assert documented.keys() == served.keys()
    # GetEstimate is the name flows and the canvas app call, so it must match exactly.
    assert documented[("/estimate", "get")] == served[("/estimate", "get")] == "GetEstimate"


def test_version_matches(swagger, openapi):
    assert swagger["info"]["version"] == openapi["info"]["version"]


def test_query_parameters_match(swagger, openapi):
    documented = {p["name"]: p for p in swagger["paths"]["/estimate"]["get"]["parameters"] if p["in"] == "query"}
    served = {p["name"]: p for p in openapi["paths"]["/estimate"]["get"]["parameters"] if p["in"] == "query"}
    assert documented.keys() == served.keys()
    for name, param in served.items():
        schema = resolve(param["schema"], openapi)
        doc = documented[name]
        assert doc["required"] == param["required"], name
        assert doc["type"] == schema["type"], name
        assert doc.get("maximum") == schema.get("maximum"), name
        # OpenAPI 3.1 writes exclusiveMinimum as a number; Swagger 2.0 as minimum + a boolean flag.
        if "exclusiveMinimum" in schema:
            assert (doc.get("minimum"), doc.get("exclusiveMinimum")) == (
                schema["exclusiveMinimum"],
                True,
            ), name
        else:
            assert doc.get("minimum") == schema.get("minimum"), name
            assert not doc.get("exclusiveMinimum"), name


def test_documented_bounds_are_the_enforced_bounds(swagger):
    params = {p["name"]: p for p in swagger["paths"]["/estimate"]["get"]["parameters"]}
    assert params["cost"]["maximum"] == MAX_COST
    assert params["hours"]["maximum"] == MAX_HOURS


def test_estimate_response_schema_matches(swagger, openapi):
    served_ref = openapi["paths"]["/estimate"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    served = resolve(served_ref, openapi)
    documented = swagger["definitions"]["Estimate"]

    assert documented["properties"].keys() == served["properties"].keys()
    assert sorted(documented["required"]) == sorted(served["required"])
    for name, prop in served["properties"].items():
        prop = resolve(prop, openapi)
        doc = documented["properties"][name]
        assert doc["type"] == prop["type"], name
        assert doc.get("enum") == prop.get("enum"), name


def test_documented_error_responses_are_declared_by_the_api(swagger, openapi):
    documented = set(swagger["paths"]["/estimate"]["get"]["responses"])
    served = set(openapi["paths"]["/estimate"]["get"]["responses"])
    assert documented == served


def test_api_key_header_matches(swagger, openapi):
    documented = swagger["securityDefinitions"]["api_key"]
    served = next(iter(openapi["components"]["securitySchemes"].values()))
    assert (documented["type"], documented["in"], documented["name"]) == (
        served["type"],
        served["in"],
        served["name"],
    )
    assert swagger["paths"]["/estimate"]["get"].get("security", swagger["security"]) == [{"api_key": []}]
    assert "security" in openapi["paths"]["/estimate"]["get"]
    # Health is deliberately open so the host's health check needs no secret.
    assert "security" not in openapi["paths"]["/health"]["get"]
    assert swagger["paths"]["/health"]["get"]["security"] == []
