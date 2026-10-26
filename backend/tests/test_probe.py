from datetime import date

from app.sources.garmin_personal.probe import base_url, guess_params, list_operations, shape

SPEC = {
    "openapi": "3.0.0",
    "servers": [{"url": "https://api.example/"}],
    "components": {
        "parameters": {
            "Start": {
                "name": "startDate",
                "in": "query",
                "required": True,
                "schema": {"type": "string", "format": "date"},
            }
        }
    },
    "paths": {
        "/activities": {
            "get": {
                "operationId": "listActivities",
                "summary": "Lista",
                "parameters": [
                    {"$ref": "#/components/parameters/Start"},
                    {
                        "name": "endDate",
                        "in": "query",
                        "schema": {"type": "string", "format": "date"},
                    },
                    {
                        "name": "limit",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "integer", "default": 50},
                    },
                ],
            }
        },
        "/activities/{id}/file": {"get": {"parameters": [{"name": "id", "in": "path"}]}},
        "/sleep": {
            "get": {
                "parameters": [
                    {"name": "fromEpochMs", "in": "query", "schema": {"type": "integer"}}
                ]
            }
        },
        "/upload": {"post": {}},
    },
}


def test_list_operations_resolves_refs_and_skips_non_get() -> None:
    ops = list_operations(SPEC)
    assert [o.path for o in ops] == ["/activities", "/activities/{id}/file", "/sleep"]
    assert ops[0].query_params[0]["name"] == "startDate"
    assert ops[1].path_params == ["id"]
    assert base_url(SPEC) == "https://api.example"


def test_guess_params() -> None:
    ops = list_operations(SPEC)
    p = guess_params(ops[0], date(2026, 10, 1), date(2026, 10, 7))
    assert p == {"startDate": "2026-10-01", "endDate": "2026-10-07", "limit": 50}
    q = guess_params(ops[2], date(1970, 1, 2), date(1970, 1, 2))
    assert q == {"fromEpochMs": 86_400_000}


def test_shape_hides_values() -> None:
    s = shape({"name": "Rodaje por Vigo", "hr": [120, 130], "gps": {"lat": 42.2}, "x": None})
    assert s == {"name": "str", "hr": ["int", "×2"], "gps": {"lat": "float"}, "x": "null"}
