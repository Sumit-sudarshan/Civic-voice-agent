"""
Verifies Supabase-issued JWTs against Supabase's own public signing key —
never trusts a token at face value (MVP_Design.md §5). Supabase projects sign
access tokens with ES256 using a per-project asymmetric key, published at a
standard JWKS endpoint; this fetches and caches that key set in memory rather
than round-tripping to Supabase on every request.
"""
import logging
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

from app.config import settings

logger = logging.getLogger(__name__)

# PyJWKClient caches the fetched key set internally (5 min lifespan by
# default) and auto-refetches when a kid it hasn't seen shows up — no manual
# cache management needed. One client for the process lifetime, same pattern
# as the ollama_client singleton in app/llm/client.py.
_jwk_client = PyJWKClient(
    f"{settings.SUPABASE_URL}/auth/v1/.well-known/jwks.json",
    headers={"apikey": settings.PUBLISHABLE_KEY},
)


class InvalidToken(Exception):
    pass


def verify_jwt(token: str) -> dict[str, Any]:
    """Returns the verified claims dict, or raises InvalidToken."""
    try:
        signing_key = _jwk_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            key=signing_key.key,
            algorithms=["ES256"],
            audience="authenticated",
        )
        return claims
    except httpx.HTTPError as e:
        logger.error(f"JWKS fetch failed: {e}")
        raise InvalidToken("Could not verify token (JWKS unavailable)") from e
    except jwt.PyJWTError as e:
        raise InvalidToken(str(e)) from e
