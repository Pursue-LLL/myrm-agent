"""Pydantic schemas for remote-access API endpoints.

[POS]
Request/response models used by ``router.py``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.remote_access.pairing import (
    BROWSER_TAKEOVER_PURPOSE,
    MOBILE_HUB_CONTROL_PURPOSE,
    MOBILE_HUB_LIST_PURPOSE,
)

PAIRING_PURPOSES = {
    MOBILE_HUB_LIST_PURPOSE,
    MOBILE_HUB_CONTROL_PURPOSE,
    BROWSER_TAKEOVER_PURPOSE,
}


class PairingTokenRequest(BaseModel):
    chat_id: str | None = Field(default=None, min_length=1, max_length=128)
    purpose: str = Field(default=MOBILE_HUB_LIST_PURPOSE, min_length=1, max_length=64)


class PairingTokenResponse(BaseModel):
    token: str
    mobile_path: str
    mobile_url: str | None = None


class E2EEHelloRequest(BaseModel):
    type: str = Field(default="e2ee_hello", min_length=1, max_length=32)
    key: str = Field(min_length=16, max_length=256)


class TunnelStartRequest(BaseModel):
    local_port: int | None = Field(default=None, ge=1, le=65535)


class MobileSpawnRequest(BaseModel):
    agent_id: str = Field(..., min_length=1, max_length=128)
    project_id: str | None = Field(default=None, max_length=128)
    initial_message: str = Field(..., min_length=1, max_length=10000)


class NodeEventRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=200)
    event_type: str = Field(..., min_length=1, max_length=200)
    payload: dict[str, object] = Field(default_factory=dict)


class SSHHostCreateRequest(BaseModel):
    host_id: str = Field(..., min_length=1, max_length=64)
    hostname: str = Field(..., min_length=1, max_length=256)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(default="root", min_length=1, max_length=64)
    auth_type: str = Field(default="password")
    secret: str | None = Field(default=None)
    passphrase: str | None = Field(default=None)
    proxy_jump: str | None = Field(default=None)
    tags: list[str] = Field(default_factory=list)
    description: str = Field(default="")


class SSHHostImportRequest(BaseModel):
    config_text: str = Field(..., min_length=1)

