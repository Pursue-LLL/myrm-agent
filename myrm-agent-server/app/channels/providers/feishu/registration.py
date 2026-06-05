"""Feishu/Lark QR scan-to-create app registration via device-code flow.

Uses the Feishu ``/oauth/v1/app/registration`` endpoint to let users
scan a QR code with their Feishu/Lark mobile app, which automatically
creates a fully configured bot application and returns credentials.

[INPUT]

[OUTPUT]
- FeishuAppRegistration: Device-code flow for QR-based app creation

[POS]
Channel provider utility. Encapsulates the Feishu device-code registration
flow for automated bot app provisioning. Used by server-layer endpoints.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TypedDict
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import httpx

logger = logging.getLogger(__name__)

_ACCOUNTS_URLS: dict[str, str] = {
    "feishu": "https://accounts.feishu.cn",
    "lark": "https://accounts.larksuite.com",
}

_OPEN_API_URLS: dict[str, str] = {
    "feishu": "https://open.feishu.cn",
    "lark": "https://open.larksuite.com",
}

_REGISTRATION_PATH = "/oauth/v1/app/registration"
_REQUEST_TIMEOUT_S = 10


class RegistrationBeginResult(TypedDict):
    """Result from begin() — contains QR URL and polling parameters."""

    qr_url: str
    device_code: str
    user_code: str
    interval: int
    expire_in: int


class RegistrationCredentials(TypedDict):
    """Credentials returned on successful registration."""

    app_id: str
    app_secret: str
    domain: str
    open_id: str | None
    bot_name: str | None
    bot_open_id: str | None


class PollResult(TypedDict):
    """Result from a single poll() call."""

    status: str  # "pending" | "success" | "denied" | "expired"
    credentials: RegistrationCredentials | None
    domain: str


class FeishuAppRegistration:
    """Feishu/Lark QR scan-to-create registration flow.

    Uses device-code flow: the user scans a QR code with their Feishu
    mobile app, and the platform creates a bot application automatically.

    Usage::

        reg = FeishuAppRegistration(domain="feishu")
        result = await reg.begin()
        # Display result["qr_url"] as QR code to user
        # Poll periodically:
        poll = await reg.poll(result["device_code"])
        if poll["status"] == "success":
            credentials = poll["credentials"]
    """

    def __init__(self, domain: str = "feishu") -> None:
        self._domain = domain
        self._current_domain = domain

    def _accounts_url(self) -> str:
        return _ACCOUNTS_URLS.get(self._current_domain, _ACCOUNTS_URLS["feishu"])

    def _open_api_url(self) -> str:
        return _OPEN_API_URLS.get(self._current_domain, _OPEN_API_URLS["feishu"])

    def _post_registration(self, body: dict[str, str]) -> dict[str, object]:
        """POST form-encoded data to the registration endpoint."""
        url = f"{self._accounts_url()}{_REGISTRATION_PATH}"
        data = urlencode(body).encode("utf-8")
        req = Request(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urlopen(req, timeout=_REQUEST_TIMEOUT_S) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            body_bytes = exc.read()
            if body_bytes:
                try:
                    return json.loads(body_bytes.decode("utf-8"))
                except (ValueError, json.JSONDecodeError):
                    raise exc from None
            raise

    async def begin(self) -> RegistrationBeginResult:
        """Initialize and begin the device-code flow.

        Returns QR URL and polling parameters.

        Raises:
            RuntimeError: If the environment doesn't support client_secret auth
        """

        def _sync_begin() -> RegistrationBeginResult:
            init_res = self._post_registration({"action": "init"})
            methods = init_res.get("supported_auth_methods") or []
            if "client_secret" not in methods:
                raise RuntimeError(f"Feishu/Lark registration does not support client_secret auth. Supported: {methods}")

            res = self._post_registration(
                {
                    "action": "begin",
                    "archetype": "PersonalAgent",
                    "auth_method": "client_secret",
                    "request_user_info": "open_id",
                }
            )
            device_code = res.get("device_code")
            if not device_code:
                raise RuntimeError("Feishu/Lark registration did not return device_code")

            qr_url = str(res.get("verification_uri_complete", ""))
            separator = "&" if "?" in qr_url else "?"
            qr_url += f"{separator}from=myrm&tp=myrm"

            return RegistrationBeginResult(
                qr_url=qr_url,
                device_code=str(device_code),
                user_code=str(res.get("user_code", "")),
                interval=int(res.get("interval") or 5),
                expire_in=int(res.get("expire_in") or 600),
            )

        return await asyncio.get_running_loop().run_in_executor(None, _sync_begin)

    async def poll(self, device_code: str) -> PollResult:
        """Poll once for registration status.

        Returns a PollResult with status and optional credentials.
        Caller should retry on "pending" status.
        """

        def _sync_poll() -> PollResult:
            try:
                res = self._post_registration(
                    {
                        "action": "poll",
                        "device_code": device_code,
                        "tp": "ob_app",
                    }
                )
            except (URLError, OSError, json.JSONDecodeError) as exc:
                logger.warning("Feishu registration poll network error: %s", exc)
                return PollResult(status="pending", credentials=None, domain=self._current_domain)

            user_info = res.get("user_info") or {}
            tenant_brand = user_info.get("tenant_brand")
            if tenant_brand == "lark" and self._current_domain != "lark":
                self._current_domain = "lark"
                logger.info("Feishu registration: auto-detected Lark domain")

            if res.get("client_id") and res.get("client_secret"):
                return PollResult(
                    status="success",
                    credentials=RegistrationCredentials(
                        app_id=str(res["client_id"]),
                        app_secret=str(res["client_secret"]),
                        domain=self._current_domain,
                        open_id=user_info.get("open_id"),
                        bot_name=None,
                        bot_open_id=None,
                    ),
                    domain=self._current_domain,
                )

            error = str(res.get("error", ""))
            if error in {"access_denied", "expired_token"}:
                status = "denied" if error == "access_denied" else "expired"
                logger.warning("Feishu registration %s", error)
                return PollResult(status=status, credentials=None, domain=self._current_domain)

            return PollResult(status="pending", credentials=None, domain=self._current_domain)

        return await asyncio.get_running_loop().run_in_executor(None, _sync_poll)

    async def probe_bot(self, app_id: str, app_secret: str) -> dict[str, str | None]:
        """Verify bot connectivity via /open-apis/bot/v3/info.

        Returns {"bot_name": ..., "bot_open_id": ...} on success.
        Returns empty values on failure (best-effort, never raises).
        """
        base_url = self._open_api_url()
        result: dict[str, str | None] = {"bot_name": None, "bot_open_id": None}

        try:
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_S) as client:
                token_resp = await client.post(
                    f"{base_url}/open-apis/auth/v3/tenant_access_token/internal",
                    json={"app_id": app_id, "app_secret": app_secret},
                )
                token_data = token_resp.json()
                access_token = token_data.get("tenant_access_token")
                if not access_token:
                    return result

                bot_resp = await client.get(
                    f"{base_url}/open-apis/bot/v3/info",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                bot_data = bot_resp.json()

                if bot_data.get("code") != 0:
                    return result
                bot = bot_data.get("bot") or bot_data.get("data", {}).get("bot") or {}
                result["bot_name"] = bot.get("app_name") or bot.get("bot_name")
                result["bot_open_id"] = bot.get("open_id")

        except Exception as exc:
            logger.debug("Feishu bot probe failed: %s", exc)

        return result
