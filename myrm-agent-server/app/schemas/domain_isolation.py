"""Pydantic schemas for Connection and Account Domain Isolation (Item 156).

[INPUT]
- Connector binding declarations, domain-scoped grant configs, recall and egress requests.

[OUTPUT]
- ConnectorDomainBindingDTO, DomainGrantConfigDTO, EgressDecisionDTO,
  ValidateRecallResponseDTO, and ValidateWriteResponseDTO.

[POS]
- Server-side DTO contracts for Item 156 ConnectionAndAccountDomainIsolation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

DataDomainDTO = Literal["work", "personal"]


class ConnectorDomainBindingDTO(BaseModel):
    """External connector bound to a specific data domain."""

    connector_id: str
    channel: str = ""
    account_id: str | None = None
    domain: DataDomainDTO = "work"
    created_at: str = ""
    updated_at: str = ""


class SetConnectorDomainRequest(BaseModel):
    """Payload to declare or update connector domain assignment."""

    connector_id: str
    domain: DataDomainDTO = "work"
    channel: str = ""
    account_id: str | None = None


class DomainGrantConfigDTO(BaseModel):
    """Permissions and toggles for an isolated data domain."""

    domain: DataDomainDTO
    allow_write: bool = True
    allow_recall: bool = True
    allow_proactive: bool = True
    allow_egress: bool = False


class UpdateDomainGrantRequest(BaseModel):
    """Payload to update permissions of an isolated domain."""

    allow_write: bool | None = None
    allow_recall: bool | None = None
    allow_proactive: bool | None = None
    allow_egress: bool | None = None


class ValidateRecallRequestDTO(BaseModel):
    """Payload to verify cross-domain memory recall allowance."""

    target_domain: DataDomainDTO
    active_domain: DataDomainDTO = "work"
    allow_cross_domain: bool = False


class ValidateRecallResponseDTO(BaseModel):
    """Result of recall permission verification."""

    allowed: bool
    reason: str
    is_cross_domain: bool


class ValidateWriteRequestDTO(BaseModel):
    """Payload to check whether memory writing is permitted."""

    domain: DataDomainDTO


class ValidateWriteResponseDTO(BaseModel):
    """Result of write permission verification."""

    allowed: bool
    reason: str


class EvaluateEgressRequestDTO(BaseModel):
    """Payload to evaluate external channel egress redline."""

    content_domain: DataDomainDTO
    target_channel: str
    user_confirmed: bool = False


class EgressDecisionDTO(BaseModel):
    """Decision verdict for external channel egress."""

    allowed: bool
    requires_user_confirmation: bool
    reason: str
    source_domain: DataDomainDTO
    target_channel: str
    is_cross_domain: bool
