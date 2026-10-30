"""Telegram Bot API transport shared by every method group of the client.

Talks to the official ``api.telegram.org`` or, through ``api_base``, to a self-hosted Bot API server or a
reverse proxy. ``proxy`` (an ``http://``, ``https://``, ``socks5://`` or ``socks5h://`` URL) routes every call
and file download through a forward proxy; without it the process environment decides. A transport error reaches
the caller as the ``httpx`` error it is, so the caller's retry policy can tell a connection that never opened
(safe to repeat) from a request the platform may already have taken (not).

[INPUT]
- httpx::AsyncClient (POS: pooled HTTP client)

[OUTPUT]
- TelegramApiError: raised when the Bot API answers ok=false
- TelegramApiBase: endpoint, pooled HTTP client and the unified ``_call``; the method groups subclass it

[POS]
Transport layer of the Telegram Bot API client. The method groups (media, forum topics) and ``TelegramClient`` build
on it.
"""

from __future__ import annotations

import httpx

_DEFAULT_API_BASE = "https://api.telegram.org"
_TIMEOUT = 30.0


class TelegramApiError(Exception):
    """Raised when the Telegram Bot API returns ok=false."""

    def __init__(self, error_code: int, description: str, parameters: dict[str, object] | None = None) -> None:
        self.error_code = error_code
        self.description = description
        self.parameters = parameters or {}
        super().__init__(f"Telegram API {error_code}: {description}")

    @property
    def is_parse_error(self) -> bool:
        return self.error_code == 400 and "can't parse entities" in self.description.lower()

    @property
    def is_not_modified(self) -> bool:
        return self.error_code == 400 and "message is not modified" in self.description.lower()

    @property
    def is_invalid_token(self) -> bool:
        """The Bot API refuses the token itself: 401 for a token it does not know, 404 for one that is
        not shaped like a token. Only meaningful for a method known to exist (``getMe``), since an unknown
        method answers 404 too."""
        return self.error_code in (401, 404)

    @property
    def is_method_not_found(self) -> bool:
        desc = self.description.lower()
        return self.error_code == 404 or (
            self.error_code == 400
            and ("method" in desc or "endpoint" in desc)
            and ("not found" in desc or "does not exist" in desc)
        )


class TelegramApiBase:
    """Endpoint, pooled ``httpx.AsyncClient`` and the unified ``_call`` every Bot API method goes through.

    Call ``close()`` during application shutdown to release resources.
    """

    def __init__(self, token: str, *, api_base: str | None = None, proxy: str | None = None) -> None:
        self._token = token
        self._proxy = (proxy or "").strip() or None
        self._http: httpx.AsyncClient | None = None
        base = api_base.rstrip("/") if api_base else _DEFAULT_API_BASE
        self._base = f"{base}/bot{token}"
        self._file_base = f"{base}/file/bot{token}"

    @property
    def token(self) -> str:
        return self._token

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=_TIMEOUT, proxy=self._proxy)
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    async def _call(
        self,
        method: str,
        *,
        json_data: dict[str, object] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        data: dict[str, str] | None = None,
        timeout: float = _TIMEOUT,
    ) -> dict[str, object]:
        """Unified Bot API call; a transport error is raised as the ``httpx`` error it is."""
        url = f"{self._base}/{method}"
        http = self._get_http()
        resp = await (
            http.post(url, data=data or {}, files=files, timeout=timeout)
            if files
            else http.post(url, json=json_data or {}, timeout=timeout)
        )

        body: dict[str, object] = resp.json()
        if not body.get("ok"):
            raw_code = body.get("error_code", resp.status_code)
            code = int(raw_code) if isinstance(raw_code, int | str) else resp.status_code
            desc = str(body.get("description", "Unknown error"))
            params = body.get("parameters")
            raise TelegramApiError(code, desc, params if isinstance(params, dict) else None)

        return body.get("result", {})  # type: ignore[return-value]
