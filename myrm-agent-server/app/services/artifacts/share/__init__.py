"""Artifact share domain: token signing, bundle materialization, registry ledger.

[INPUT]
- Artifact metadata (name, artifact_type) from the artifact API.
- Share-bundle directory paths + artifact source payloads.
- SQLite async sessions (registry read/write).

[OUTPUT]
- Aggregate facade re-exporting every public name of the ``share`` subpackage:
  - share_token: ArtifactShareClaims + create/rebuild/parse token primitives +
    shareability predicates
  - share_bundle: ShareBundleManifest + bundle_dir_for_claims /
    materialize_share_bundle / resolve_share_bundle_file / purge_expired_share_bundles
  - share_registry: ActiveShareRow + register/list/revoke/expire ledger operations

[POS]
Server business layer. Single artifact-share domain shared by the artifact API
surface, public share endpoints and deliverable deep links; token/bundle/registry
are always used together, so they stay co-located under one facade.
"""

from app.services.artifacts.share.share_bundle import (
    ShareBundleManifest,
    bundle_asset_count,
    bundle_dir_for_claims,
    materialize_share_bundle,
    purge_expired_share_bundles,
    resolve_share_bundle_file,
)
from app.services.artifacts.share.share_registry import (
    ActiveShareRow,
    is_token_revoked,
    list_active_shares,
    purge_expired_shares,
    register_share,
    revoke_share,
)
from app.services.artifacts.share.share_token import (
    ArtifactShareClaims,
    create_artifact_share_token,
    is_shareable_artifact,
    is_shareable_artifact_name,
    parse_artifact_share_token,
    rebuild_artifact_share_token,
)

__all__ = [
    "ActiveShareRow",
    "ArtifactShareClaims",
    "ShareBundleManifest",
    "bundle_asset_count",
    "bundle_dir_for_claims",
    "create_artifact_share_token",
    "is_shareable_artifact",
    "is_shareable_artifact_name",
    "is_token_revoked",
    "list_active_shares",
    "materialize_share_bundle",
    "parse_artifact_share_token",
    "purge_expired_share_bundles",
    "purge_expired_shares",
    "rebuild_artifact_share_token",
    "register_share",
    "resolve_share_bundle_file",
    "revoke_share",
]
