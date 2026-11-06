import json
import logging
from collections.abc import Callable
from typing import Any

import azure.functions as func

from auth import AuthError, authenticate
from network import create_vnet
from storage import get_record, list_records, save_record
from validation import ValidationError, validate_request

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

EndpointHandler = Callable[[func.HttpRequest, dict], func.HttpResponse]


def json_response(body: Any, status_code: int = 200) -> func.HttpResponse:
    """Serialize `body` as a JSON HTTP response."""
    return func.HttpResponse(json.dumps(body), status_code=status_code, mimetype="application/json")


def require_authentication(
    endpoint_handler: EndpointHandler,
) -> Callable[[func.HttpRequest], func.HttpResponse]:
    """Authenticate (any valid Entra ID token is authorized) and map errors to HTTP codes."""

    def authenticated_endpoint(req: func.HttpRequest) -> func.HttpResponse:
        try:
            token_claims = authenticate(req.headers.get("Authorization"))
            return endpoint_handler(req, token_claims)
        except AuthError as error:
            return json_response({"error": str(error)}, 401)
        except ValidationError as error:
            return json_response({"error": str(error)}, 400)
        except Exception:
            logging.exception("Unhandled error")
            return json_response({"error": "internal error"}, 500)

    authenticated_endpoint.__name__ = endpoint_handler.__name__
    return authenticated_endpoint


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    """Unauthenticated liveness check."""
    return json_response({"status": "ok"})


@app.route(route="vnets", methods=["POST"])
@require_authentication
def create_vnet_endpoint(req: func.HttpRequest, token_claims: dict) -> func.HttpResponse:
    """Create a VNet with its subnets and store the result (201), or 409 if the name is taken."""
    try:
        request_body = req.get_json()
    except ValueError as error:
        raise ValidationError("body must be valid JSON") from error
    vnet_spec = validate_request(request_body)

    if get_record(vnet_spec["name"]):
        return json_response({"error": f"vnet '{vnet_spec['name']}' already exists"}, 409)

    created_vnet = create_vnet(vnet_spec)
    created_vnet["createdBy"] = (
        token_claims.get("preferred_username")
        or token_claims.get("appid")
        or token_claims.get("oid")
    )
    save_record(created_vnet)
    return json_response(created_vnet, 201)


@app.route(route="vnets", methods=["GET"])
@require_authentication
def list_vnets_endpoint(req: func.HttpRequest, token_claims: dict) -> func.HttpResponse:
    """Return every stored VNet record."""
    return json_response(list_records())


@app.route(route="vnets/{name}", methods=["GET"])
@require_authentication
def get_vnet_endpoint(req: func.HttpRequest, token_claims: dict) -> func.HttpResponse:
    """Return one stored VNet record by name, or 404."""
    stored_vnet = get_record(req.route_params["name"])
    return json_response(stored_vnet) if stored_vnet else json_response({"error": "not found"}, 404)
