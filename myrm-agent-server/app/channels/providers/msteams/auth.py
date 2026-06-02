"""Bot Framework JWT token verification for MSTeams webhook security.

Validates inbound webhook requests by verifying the JWT token in the
Authorization header against Bot Framework's OpenID Connect public keys.

[INPUT]
- (none)

[OUTPUT]
- BotFrameworkJwtVerifier: async verifier with OpenID metadata + JWKS caching

[POS]
app.channels.providers.msteams.auth — Bot Framework JWT validator.
Fetches public keys via OpenID Connect metadata, verifies JWT signature,
issuer, audience, and serviceUrl claims on webhook requests.
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

_OPENID_METADATA_URL = "https://login.botframework.com/v1/.well-known/openidconfiguration"
_BF_ISSUER = "https://api.botframework.com"
_JWKS_CACHE_TTL = 86400.0


class BotFrameworkJwtVerifier:
    """Verifies Bot Framework JWT tokens from webhook Authorization headers."""

    def __init__(self, app_id: str, http: httpx.AsyncClient) -> None:
        self._app_id = app_id
        self._http = http
        self._jwks_url_cache: str = ""
        self._jwks_fetched_at: float = 0.0

    async def verify(self, auth_header: str, activity: dict[str, object]) -> bool:
        """Verify JWT token. Returns True if valid, False otherwise.

        Skips verification if app_id is not configured (development mode)
        or if PyJWT is not installed.
        """
        if not self._app_id:
            return True

        if not auth_header or not auth_header.lower().startswith("bearer "):
            logger.debug("MSTeams JWT: missing or invalid Authorization header")
            return False

        token = auth_header[7:]

        try:
            import jwt as pyjwt
            from jwt import PyJWKClient
        except (ImportError, TypeError):
            logger.warning("MSTeams JWT: PyJWT not installed, skipping verification")
            return True

        try:
            jwks_url = await self._get_jwks_url()
            if not jwks_url:
                return False

            jwks_client = PyJWKClient(jwks_url, cache_keys=True, lifespan=3600)
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            claims = pyjwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "RS384", "RS512"],
                audience=self._app_id,
                issuer=_BF_ISSUER,
                options={"require": ["exp", "iss", "aud"]},
            )

            service_url_claim = claims.get("serviceurl", "") or claims.get("serviceUrl", "")
            activity_service_url = str(activity.get("serviceUrl", ""))
            if activity_service_url and service_url_claim:
                if str(service_url_claim).rstrip("/") != activity_service_url.rstrip("/"):
                    logger.debug("MSTeams JWT: serviceUrl mismatch")
                    return False

            return True
        except pyjwt.ExpiredSignatureError:
            logger.debug("MSTeams JWT: token expired")
            return False
        except pyjwt.InvalidTokenError as e:
            logger.debug("MSTeams JWT: invalid token — %s", e)
            return False
        except Exception as e:
            logger.warning("MSTeams JWT: verification error — %s", e)
            return False

    async def _get_jwks_url(self) -> str:
        """Fetch JWKS URL from Bot Framework OpenID metadata (cached 24h)."""
        now = time.monotonic()
        if self._jwks_url_cache and now - self._jwks_fetched_at < _JWKS_CACHE_TTL:
            return self._jwks_url_cache

        try:
            resp = await self._http.get(_OPENID_METADATA_URL, timeout=10.0)
            if resp.status_code != 200:
                logger.warning("MSTeams: OpenID metadata fetch failed: HTTP %d", resp.status_code)
                return ""
            metadata = resp.json()
            jwks_url = str(metadata.get("jwks_uri", ""))
            if jwks_url:
                self._jwks_url_cache = jwks_url
                self._jwks_fetched_at = now
            return jwks_url
        except Exception as e:
            logger.warning("MSTeams: OpenID metadata fetch error — %s", e)
            return ""
