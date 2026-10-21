"""Shared base model for camelCase-aliased security DTOs.

[INPUT]
- pydantic::BaseModel, ConfigDict
- pydantic.alias_generators::to_camel

[OUTPUT]
- CamelModel: base model whose fields accept both camelCase (API) and snake_case (internal)

[POS]
Shared DTO base for the security schemas package; keeps the camelCase alias contract in one
place so every security response model serializes consistently.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Base model exposing camelCase aliases while accepting snake_case input."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
