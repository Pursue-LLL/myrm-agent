"""Shared WeChat Official Account API client (access token lifecycle).

[INPUT]
- httpx (HTTP client)
- wechat_api_errors::format_wechat_api_error_message (POS: locale-aware errcode hints)

[OUTPUT]
- WeChatOfficialApiClient: token refresh, transient retry, authenticated API calls

[POS]
Reusable token manager for official-account APIs (messaging, drafts, media).
Messaging channel and draft service share this client; no duplicate token logic.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

from app.channels.core.exceptions import ChannelAuthError, ChannelConnectionError
from app.channels.providers.wechat.wechat_api_errors import format_wechat_api_error_message

logger = logging.getLogger(__name__)

_API_BASE = "https://api.weixin.qq.com/cgi-bin"
_TOKEN_REFRESH_BUFFER = 300
_TOKEN_EXPIRED_ERRCODES = frozenset({40001, 42001})
_TRANSIENT_ERRCODES = frozenset({-1, 45009})
_MAX_TRANSIENT_RETRIES = 2


@dataclass(frozen=True, slots=True)
class _MultipartRetryContext:
    field_name: str
    filename: str
    content: bytes
    extra_params: dict[str, str] | None
    timeout: float


class WeChatOfficialApiClient:
    """Minimal WeChat Official Account API client with token caching."""

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        *,
        http: httpx.AsyncClient | None = None,
        locale: str = "zh",
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._locale = locale
        self._owns_http = http is None
        self._http = http or httpx.AsyncClient()
        self._access_token = ""
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    async def close(self) -> None:
        if self._owns_http:
            await self._http.aclose()

    async def ensure_token(self) -> str:
        if time.monotonic() < self._token_expires_at and self._access_token:
            return self._access_token
        async with self._token_lock:
            if time.monotonic() >= self._token_expires_at or not self._access_token:
                await self._refresh_token()
        return self._access_token

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, str] | None = None,
        timeout: float = 15.0,
        _retried: bool = False,
        _transient_attempt: int = 0,
    ) -> dict[str, object]:
        token = await self.ensure_token()
        query = {"access_token": token, **(params or {})}
        resp = await self._http.get(f"{_API_BASE}/{path}", params=query, timeout=timeout)
        return await self._parse_json_response(
            resp,
            path,
            _retried=_retried,
            _transient_attempt=_transient_attempt,
            retry_params=params,
        )

    async def post_json(
        self,
        path: str,
        payload: dict[str, object],
        *,
        params: dict[str, str] | None = None,
        timeout: float = 30.0,
        _retried: bool = False,
        _transient_attempt: int = 0,
    ) -> dict[str, object]:
        token = await self.ensure_token()
        query = {"access_token": token, **(params or {})}
        resp = await self._http.post(
            f"{_API_BASE}/{path}",
            params=query,
            json=payload,
            timeout=timeout,
        )
        return await self._parse_json_response(
            resp,
            path,
            _retried=_retried,
            _transient_attempt=_transient_attempt,
            retry_payload=payload,
            retry_params=params,
        )

    async def post_multipart(
        self,
        path: str,
        *,
        field_name: str,
        filename: str,
        content: bytes,
        extra_params: dict[str, str] | None = None,
        timeout: float = 30.0,
        _retried: bool = False,
        _transient_attempt: int = 0,
    ) -> dict[str, object]:
        token = await self.ensure_token()
        query = {"access_token": token, **(extra_params or {})}
        resp = await self._http.post(
            f"{_API_BASE}/{path}",
            params=query,
            files={field_name: (filename, content)},
            timeout=timeout,
        )
        return await self._parse_json_response(
            resp,
            path,
            _retried=_retried,
            _transient_attempt=_transient_attempt,
            retry_multipart=_MultipartRetryContext(
                field_name=field_name,
                filename=filename,
                content=content,
                extra_params=extra_params,
                timeout=timeout,
            ),
        )

    async def _refresh_token(self) -> None:
        resp = await self._http.get(
            f"{_API_BASE}/token",
            params={
                "grant_type": "client_credential",
                "appid": self._app_id,
                "secret": self._app_secret,
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            raise ChannelAuthError(
                f"WeChat token refresh failed: HTTP {resp.status_code}",
                channel="wechat_official",
            )
        data = resp.json()
        errcode = data.get("errcode")
        if errcode not in (None, 0):
            raise ChannelAuthError(
                f"WeChat token error: {data.get('errmsg')}",
                channel="wechat_official",
            )
        self._access_token = str(data.get("access_token", ""))
        expire = int(data.get("expires_in", 7200))
        self._token_expires_at = time.monotonic() + expire - _TOKEN_REFRESH_BUFFER
        logger.debug("WeChat official access token refreshed")

    async def _parse_json_response(
        self,
        resp: httpx.Response,
        path: str,
        *,
        _retried: bool,
        _transient_attempt: int = 0,
        retry_payload: dict[str, object] | None = None,
        retry_params: dict[str, str] | None = None,
        retry_multipart: _MultipartRetryContext | None = None,
    ) -> dict[str, object]:
        if resp.status_code >= 400:
            raise ChannelConnectionError(
                f"WeChat API HTTP {resp.status_code} for {path}",
                channel="wechat_official",
            )
        data: dict[str, object] = resp.json()
        errcode_raw = data.get("errcode", 0)
        errcode = int(errcode_raw) if errcode_raw is not None else 0
        if errcode == 0:
            return data
        if errcode in _TOKEN_EXPIRED_ERRCODES and not _retried:
            await self._refresh_token()
            if retry_payload is not None:
                return await self.post_json(path, retry_payload, params=retry_params, _retried=True)
            if retry_multipart is not None:
                return await self.post_multipart(
                    path,
                    field_name=retry_multipart.field_name,
                    filename=retry_multipart.filename,
                    content=retry_multipart.content,
                    extra_params=retry_multipart.extra_params,
                    timeout=retry_multipart.timeout,
                    _retried=True,
                )
            return await self.get_json(path, params=retry_params, _retried=True)
        if errcode in _TRANSIENT_ERRCODES and _transient_attempt < _MAX_TRANSIENT_RETRIES:
            delay = 0.5 * (_transient_attempt + 1)
            logger.info(
                "WeChat API transient error errcode=%s on %s; retry %s/%s after %.1fs",
                errcode,
                path,
                _transient_attempt + 1,
                _MAX_TRANSIENT_RETRIES,
                delay,
            )
            await asyncio.sleep(delay)
            next_attempt = _transient_attempt + 1
            if retry_payload is not None:
                return await self.post_json(
                    path,
                    retry_payload,
                    params=retry_params,
                    _retried=_retried,
                    _transient_attempt=next_attempt,
                )
            if retry_multipart is not None:
                return await self.post_multipart(
                    path,
                    field_name=retry_multipart.field_name,
                    filename=retry_multipart.filename,
                    content=retry_multipart.content,
                    extra_params=retry_multipart.extra_params,
                    timeout=retry_multipart.timeout,
                    _retried=_retried,
                    _transient_attempt=next_attempt,
                )
            return await self.get_json(
                path,
                params=retry_params,
                _retried=_retried,
                _transient_attempt=next_attempt,
            )
        message = format_wechat_api_error_message(
            errcode,
            data.get("errmsg"),
            path=path,
            locale=self._locale,
        )
        raise ChannelConnectionError(message, channel="wechat_official")
