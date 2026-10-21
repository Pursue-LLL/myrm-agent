"""Search provider catalog data models.

[INPUT]
- manifest.json entries (POS: Static search provider catalog)

[OUTPUT]
- SearchProviderManifestEntry, SearchDeploymentScope, SearchConnectorType enums

[POS]
Pydantic models for search provider catalog registry (Omni searchServices SSOT).
"""

from enum import Enum

from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel
from pydantic.config import ConfigDict


class SearchConnectorType(str, Enum):
    LITELLM = "litellm"
    NATIVE = "native"


class SearchDeploymentScope(str, Enum):
    ALL_MODES = "all_modes"
    LOCAL_TAURI_ONLY = "local_tauri_only"


class SearchProviderManifestEntry(BaseModel):
    """A single web search provider exposed in Settings."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    slug: str = Field(..., description="Provider slug passed to harness search backend")
    connector: SearchConnectorType = Field(..., description="litellm or native adapter")
    name: str = Field(..., description="English display name")
    name_zh: str = Field(default="", description="Chinese display name")
    deployment_scope: SearchDeploymentScope = Field(
        default=SearchDeploymentScope.ALL_MODES,
        description="Deployment compatibility scope",
    )
    requires_api_key: bool = Field(default=True, description="Whether API key is required")
    requires_api_base: bool = Field(default=False, description="Whether api_base URL is required")
    backend_ready: bool = Field(
        default=True,
        description="When false, provider is listed but not selectable until backend ships",
    )
