"""API endpoint tests with auth, ARM and Table Storage replaced by fakes (no Azure needed)."""

import json

import azure.functions as func
import pytest

import function_app
from auth import AuthError

VALID_BODY = {
    "name": "demo-vnet",
    "addressSpace": ["10.0.0.0/16"],
    "subnets": [
        {"name": "web", "addressPrefix": "10.0.1.0/24"},
        {"name": "db", "addressPrefix": "10.0.2.0/24"},
    ],
}


@pytest.fixture
def stored_records(monkeypatch) -> dict:
    """Replace auth, VNet creation and storage with in-memory fakes; returns the fake table."""
    records: dict[str, dict] = {}

    def fake_create_vnet(vnet_spec: dict) -> dict:
        return {"name": vnet_spec["name"], "subnets": vnet_spec["subnets"]}

    def fake_save_record(record: dict) -> None:
        records[record["name"]] = record

    monkeypatch.setattr(
        function_app, "authenticate", lambda header: {"preferred_username": "tester"}
    )
    monkeypatch.setattr(function_app, "create_vnet", fake_create_vnet)
    monkeypatch.setattr(function_app, "save_record", fake_save_record)
    monkeypatch.setattr(function_app, "get_record", records.get)
    monkeypatch.setattr(function_app, "list_records", lambda: list(records.values()))
    return records


def call(endpoint, method: str, body=None, route_params=None, headers=None) -> func.HttpResponse:
    """Invoke the endpoint's Python function with a hand-built HTTP request."""
    raw_body = body if isinstance(body, bytes) else json.dumps(body).encode() if body else b""
    request = func.HttpRequest(
        method=method,
        url="/api/test",
        headers=headers if headers is not None else {"Authorization": "Bearer fake-token"},
        params={},
        route_params=route_params or {},
        body=raw_body,
    )
    return endpoint.build().get_user_function()(request)


def test_health_needs_no_token():
    response = call(function_app.health, "GET", headers={})

    assert response.status_code == 200


def test_missing_token_returns_401():
    response = call(function_app.list_vnets_endpoint, "GET", headers={})

    assert response.status_code == 401
    assert "missing bearer token" in response.get_body().decode()


def test_invalid_token_returns_401(monkeypatch):
    def reject(header):
        raise AuthError("invalid token")

    monkeypatch.setattr(function_app, "authenticate", reject)

    response = call(function_app.list_vnets_endpoint, "GET")

    assert response.status_code == 401


def test_create_returns_201_and_stores_record(stored_records):
    response = call(function_app.create_vnet_endpoint, "POST", VALID_BODY)

    assert response.status_code == 201
    assert json.loads(response.get_body())["createdBy"] == "tester"
    assert stored_records["demo-vnet"]["createdBy"] == "tester"


def test_create_duplicate_name_returns_409(stored_records):
    call(function_app.create_vnet_endpoint, "POST", VALID_BODY)

    response = call(function_app.create_vnet_endpoint, "POST", VALID_BODY)

    assert response.status_code == 409


def test_create_with_invalid_json_returns_400(stored_records):
    response = call(function_app.create_vnet_endpoint, "POST", b"not json")

    assert response.status_code == 400


def test_create_with_invalid_spec_returns_400(stored_records):
    overlapping = {**VALID_BODY, "subnets": [{"name": "web", "addressPrefix": "192.168.0.0/24"}]}

    response = call(function_app.create_vnet_endpoint, "POST", overlapping)

    assert response.status_code == 400
    assert stored_records == {}


def test_create_failure_in_azure_returns_500(stored_records, monkeypatch):
    def fail(vnet_spec):
        raise RuntimeError("ARM is down")

    monkeypatch.setattr(function_app, "create_vnet", fail)

    response = call(function_app.create_vnet_endpoint, "POST", VALID_BODY)

    assert response.status_code == 500
    assert stored_records == {}


def test_list_returns_stored_records(stored_records):
    call(function_app.create_vnet_endpoint, "POST", VALID_BODY)

    response = call(function_app.list_vnets_endpoint, "GET")

    assert response.status_code == 200
    assert [vnet["name"] for vnet in json.loads(response.get_body())] == ["demo-vnet"]


def test_get_existing_vnet_returns_200(stored_records):
    call(function_app.create_vnet_endpoint, "POST", VALID_BODY)

    response = call(function_app.get_vnet_endpoint, "GET", route_params={"name": "demo-vnet"})

    assert response.status_code == 200


def test_get_unknown_vnet_returns_404(stored_records):
    response = call(function_app.get_vnet_endpoint, "GET", route_params={"name": "nope"})

    assert response.status_code == 404
