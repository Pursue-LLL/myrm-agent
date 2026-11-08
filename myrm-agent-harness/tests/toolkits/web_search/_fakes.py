"""Test doubles shared by the web_search error-classification and provider-chain tests."""

from __future__ import annotations


class FakeAPIConnectionError(Exception):
    """Simulates a gateway's generic APIConnectionError(status=500) wrapper."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        super().__init__(f"APIConnectionError: {message}")
        self.status_code = status_code


class FakeProviderHTTPError(Exception):
    """Provider SDK exception carrying the HTTP fields the error classifier probes with ``getattr``."""

    def __init__(
        self,
        message: str = "",
        *,
        status_code: int | None = None,
        http_status: int | None = None,
        response: str | None = None,
        body: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.http_status = http_status
        self.response = response
        self.body = body
