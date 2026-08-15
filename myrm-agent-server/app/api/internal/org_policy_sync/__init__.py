"""Internal org policy-sync API domain: managed approval / MCP / model policy sync.

[INPUT]
- Internal admin payloads pushed to this server (cloud-hosted org orchestration).
- Org policy snapshots (approval policy, MCP allow-list, model allow-list).

[OUTPUT]
- Aggregate facade re-exporting the routers of the ``org_policy_sync`` subpackage:
  - org_managed_approval_policy_sync: ``router`` — org-managed approval policy sync
  - org_mcp_sync: ``router`` — org MCP server allow-list sync
  - org_model_policy_sync: ``router`` (internal) + ``frontend_router`` (WebUI view)

[POS]
Server business layer (Internal API). The three org policy-sync surfaces share
the same ingress semantics (admin push from the org control plane) and are all
mounted in ``app.main``, so they stay co-located under one facade.
"""

from app.api.internal.org_policy_sync.org_managed_approval_policy_sync import (
    OrgManagedApprovalPolicySyncRequest,
    OrgManagedApprovalPolicySyncResponse,
    router,
)
from app.api.internal.org_policy_sync.org_mcp_sync import (
    OrgMCPSyncRequest,
    OrgMCPSyncResponse,
    router as mcp_sync_router,
)
from app.api.internal.org_policy_sync.org_model_policy_sync import (
    AllowedModelsResponse,
    OrgModelPolicySyncRequest,
    OrgModelPolicySyncResponse,
    frontend_router,
    router as model_policy_sync_router,
)

__all__ = [
    "AllowedModelsResponse",
    "OrgMCPSyncRequest",
    "OrgMCPSyncResponse",
    "OrgManagedApprovalPolicySyncRequest",
    "OrgManagedApprovalPolicySyncResponse",
    "OrgModelPolicySyncRequest",
    "OrgModelPolicySyncResponse",
    "frontend_router",
    "mcp_sync_router",
    "model_policy_sync_router",
    "router",
]
