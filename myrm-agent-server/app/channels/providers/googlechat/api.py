"""Google Chat API client — Service Account JWT auth with zero new deps.

Uses the project's existing ``cryptography`` library for RS256 JWT signing,
exchanging the assertion for an OAuth2 access_token via Google's token endpoint.

Also provides ``verify_google_chat_bearer`` for webhook request authentication,
verifying tokens signed by ``chat@system.gserviceaccount.com``.

[INPUT]
- (none)

[OUTPUT]
- GoogleChatClient: Async client for Google Chat API v1 with self-signed JWT auth.
- verify_google_chat_bearer: Verify a bearer token from Google Chat webhook requests.

[POS]
app.channels.providers.googlechat.api — Google Chat API client with Service Account JWT auth.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey, RSAPublicKey
from cryptography.x509 import load_pem_x509_certificate

from app.channels.providers._http_timeout import resolve_timeout

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_CHAT_API = "https://chat.googleapis.com/v1"
_SCOPE = "https://www.googleapis.com/auth/chat.bot"
_TIMEOUT = resolve_timeout(15.0)
_TOKEN_REFRESH_BUFFER = 60


def _b64url(data: bytes) -> str:
    """Base64url encode without padding (RFC 7515)."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class GoogleChatClient:
    """Async client for Google Chat API v1 with self-signed JWT auth.

    Authenticates using a Service Account JSON key, signing a JWT with
    RS256 (via ``cryptography``) and exchanging it for an access_token.
    """

    def __init__(self, service_account_json: str) -> None:
        self._client_email: str = ""
        self._private_key: RSAPrivateKey | None = None
        self._token: str = ""
        self._token_expires_at: float = 0.0
        self._token_lock = asyncio.Lock()
        self._http: httpx.AsyncClient | None = None

        if service_account_json:
            self._parse_service_account(service_account_json)

    @property
    def is_configured(self) -> bool:
        return bool(self._client_email and self._private_key)

    def _parse_service_account(self, raw: str) -> None:
        try:
            sa = json.loads(raw)
            self._client_email = sa["client_email"]
            key_pem = sa["private_key"].encode("utf-8")
            loaded = serialization.load_pem_private_key(key_pem, password=None)
            if not isinstance(loaded, RSAPrivateKey):
                raise TypeError("Expected RSA private key")
            self._private_key = loaded
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            logger.warning("Google Chat: invalid service account JSON: %s", exc)
            self._client_email = ""
            self._private_key = None

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=_TIMEOUT)
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    # ── JWT + OAuth2 token management ─────────────────────────────

    def _sign_jwt(self) -> str:
        if not self._private_key or not self._client_email:
            raise RuntimeError("Service account not configured")

        now = int(time.time())
        header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
        claims = _b64url(
            json.dumps(
                {
                    "iss": self._client_email,
                    "scope": _SCOPE,
                    "aud": _TOKEN_URL,
                    "iat": now,
                    "exp": now + 3600,
                }
            ).encode()
        )
        signing_input = f"{header}.{claims}".encode("ascii")
        signature = self._private_key.sign(
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return f"{header}.{claims}.{_b64url(signature)}"

    async def _ensure_token(self) -> str:
        """Return a valid access_token, refreshing via JWT exchange if expired.

        Uses asyncio.Lock with double-check locking to prevent
        concurrent requests from triggering redundant token refreshes.
        """
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token

        async with self._token_lock:
            if self._token and time.monotonic() < self._token_expires_at:
                return self._token

            jwt = self._sign_jwt()
            http = self._get_http()
            resp = await http.post(
                _TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": jwt,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            self._token = data["access_token"]
            expires_in = int(data.get("expires_in", 3600))
            self._token_expires_at = time.monotonic() + expires_in - _TOKEN_REFRESH_BUFFER
            logger.info("Google Chat token refreshed, expires in %ds", expires_in)
            return self._token

    async def verify_token(self) -> bool:
        try:
            await self._ensure_token()
            return True
        except Exception:
            return False

    # ── Chat API operations ───────────────────────────────────────

    async def _auth_headers(self) -> dict[str, str]:
        token = await self._ensure_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def send_message(
        self,
        space: str,
        text: str,
        *,
        thread_key: str | None = None,
    ) -> dict[str, object]:
        """Create a message in a space (format: ``spaces/XXXXX``)."""
        http = self._get_http()
        url = f"{_CHAT_API}/{space}/messages"
        body: dict[str, object] = {"text": text}
        params: dict[str, str] = {}

        if thread_key:
            body["thread"] = {"threadKey": thread_key}
            params["messageReplyOption"] = "REPLY_MESSAGE_FALLBACK_TO_NEW_THREAD"

        resp = await http.post(url, json=body, params=params, headers=await self._auth_headers())
        resp.raise_for_status()
        return resp.json()

    async def update_message(self, name: str, text: str) -> dict[str, object]:
        """Update an existing message (format: ``spaces/XXXXX/messages/YYYYY``)."""
        http = self._get_http()
        url = f"{_CHAT_API}/{name}"
        resp = await http.put(
            url,
            json={"text": text},
            params={"updateMask": "text"},
            headers=await self._auth_headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def delete_message(self, name: str) -> None:
        http = self._get_http()
        url = f"{_CHAT_API}/{name}"
        resp = await http.delete(url, headers=await self._auth_headers())
        resp.raise_for_status()


# ── Webhook bearer token verification ─────────────────────────

_CHAT_ISSUER = "chat@system.gserviceaccount.com"
_CERTS_URL = "https://www.googleapis.com/service_accounts/v1/metadata/x509/" + _CHAT_ISSUER
_CERTS_CACHE: dict[str, RSAPublicKey] = {}
_CERTS_EXPIRE_AT: float = 0.0
_CLOCK_SKEW = 30


def _b64url_decode(s: str) -> bytes:
    """Base64url decode with padding restoration."""
    s += "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s)


async def _fetch_google_certs(http: httpx.AsyncClient) -> dict[str, RSAPublicKey]:
    """Fetch and cache Google's x509 public keys for chat@system SA."""
    global _CERTS_CACHE, _CERTS_EXPIRE_AT

    now = time.monotonic()
    if _CERTS_CACHE and now < _CERTS_EXPIRE_AT:
        return _CERTS_CACHE

    resp = await http.get(_CERTS_URL, timeout=10.0)
    resp.raise_for_status()

    cache_ttl = 3600.0
    cc = resp.headers.get("cache-control", "")
    for directive in cc.split(","):
        directive = directive.strip()
        if directive.startswith("max-age="):
            try:
                cache_ttl = float(directive.split("=", 1)[1])
            except ValueError:
                pass

    certs: dict[str, RSAPublicKey] = {}
    for kid, pem in resp.json().items():
        cert = load_pem_x509_certificate(pem.encode("utf-8"))
        pub = cert.public_key()
        if isinstance(pub, RSAPublicKey):
            certs[kid] = pub

    _CERTS_CACHE = certs
    _CERTS_EXPIRE_AT = now + cache_ttl
    return certs


async def verify_google_chat_bearer(
    bearer_token: str,
    audience: str,
    *,
    http: httpx.AsyncClient | None = None,
) -> bool:
    """Verify a bearer token from Google Chat webhook requests.

    Supports both authentication modes:
    - OIDC ID Token (audience = endpoint URL)
    - Project Number JWT (audience = project number)

    Returns True if the token is valid, signed by chat@system.gserviceaccount.com,
    and targeted at the given audience.
    """
    try:
        parts = bearer_token.split(".")
        if len(parts) != 3:
            return False

        header_data = json.loads(_b64url_decode(parts[0]))
        claims_data = json.loads(_b64url_decode(parts[1]))

        kid = header_data.get("kid", "")
        alg = header_data.get("alg", "")
        if alg != "RS256":
            return False

        now = int(time.time())
        exp = int(claims_data.get("exp", 0))
        iat = int(claims_data.get("iat", 0))
        if now > exp + _CLOCK_SKEW or now < iat - _CLOCK_SKEW:
            return False

        issuer = claims_data.get("iss", "") or claims_data.get("email", "")
        if issuer != _CHAT_ISSUER:
            return False

        token_aud = claims_data.get("aud", "")
        if token_aud != audience:
            return False

        close_after = False
        if http is None:
            http = httpx.AsyncClient()
            close_after = True
        try:
            certs = await _fetch_google_certs(http)
        finally:
            if close_after:
                await http.aclose()

        pub_key = certs.get(kid)
        if not pub_key:
            return False

        signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
        signature = _b64url_decode(parts[2])
        pub_key.verify(
            signature,
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

    except Exception:
        return False
    else:
        return True
