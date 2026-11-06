import os
from functools import lru_cache

import jwt
from jwt import PyJWKClient


class AuthError(Exception):
    """The request has no valid bearer token."""


@lru_cache(maxsize=1)
def _get_tenant_signing_keys() -> PyJWKClient:
    """Client for the tenant's token-signing public keys (cached for the process lifetime)."""
    tenant_id = os.environ["AZURE_TENANT_ID"]
    return PyJWKClient(f"https://login.microsoftonline.com/{tenant_id}/discovery/v2.0/keys")


def authenticate(authorization_header: str | None) -> dict:
    """Validate an Entra ID bearer token. Any authenticated principal is authorized."""
    if not authorization_header or not authorization_header.lower().startswith("bearer "):
        raise AuthError("missing bearer token")
    token = authorization_header[len("bearer ") :].strip()

    tenant_id = os.environ["AZURE_TENANT_ID"]
    api_client_id = os.environ["API_CLIENT_ID"]
    try:
        signing_key = _get_tenant_signing_keys().get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            signing_key,
            algorithms=["RS256"],
            audience=[api_client_id, f"api://{api_client_id}"],
            issuer=[
                f"https://login.microsoftonline.com/{tenant_id}/v2.0",
                f"https://sts.windows.net/{tenant_id}/",
            ],
            options={"require": ["exp", "iss", "aud"]},
        )
    except Exception as error:
        raise AuthError(f"invalid token: {error}") from error
