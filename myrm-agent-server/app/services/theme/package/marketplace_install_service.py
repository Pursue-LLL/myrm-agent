"""Install theme packages acquired from the CP public marketplace.

[INPUT]
app.services.theme.package.inspect_service (POS: 包检查)
app.services.theme.package.install_service (POS: 包安装)
app.services.theme.package.marketplace_cp_client (POS: CP 权限校验)
app.services.theme.package.marketplace_signing (POS: 传输签名校验)

[OUTPUT]
marketplace_install(signed_payload) -> ThemeProfileRecipeModel

[POS]
完整的市场主题安装流水线：签名验证 → entitlement 校验 → inspect → install → 记录安装。
"""

from __future__ import annotations

from app.platform_utils.deployment_capabilities import get_deployment_capabilities
from app.schemas.theme_profile import ThemeProfileRecipeModel
from app.services.theme.package.inspect_service import inspect_theme_package
from app.services.theme.package.install_service import ThemePackageInstallError, install_theme_package
from app.services.theme.package.marketplace_cp_client import (
    record_marketplace_install,
    verify_marketplace_entitlement,
)
from app.services.theme.package.marketplace_signing import verify_marketplace_download_signature


class ThemeMarketplaceInstallError(ValueError):
    """User-facing marketplace install failure."""


async def install_theme_package_from_marketplace(
    *,
    listing_id: str,
    package_bytes: bytes,
    package_sha256: str,
    transport_signature: str,
    expires_at: float,
    set_active: bool,
    existing_profile_ids: set[str],
) -> tuple[ThemeProfileRecipeModel, bool, str]:
    if not verify_marketplace_download_signature(
        listing_id=listing_id,
        package_sha256=package_sha256,
        signature=transport_signature,
        expires_at=expires_at,
    ):
        raise ThemeMarketplaceInstallError("Invalid or expired theme marketplace download token")

    if get_deployment_capabilities().is_sandbox_instance:
        entitled = await verify_marketplace_entitlement(listing_id=listing_id)
        if not entitled:
            raise ThemeMarketplaceInstallError("Theme marketplace entitlement required")

    inspect_result = inspect_theme_package(package_bytes)
    if inspect_result.package_sha256 != package_sha256:
        raise ThemeMarketplaceInstallError("Theme package hash mismatch")

    if not inspect_result.can_import:
        raise ThemeMarketplaceInstallError(
            "Theme package cannot be imported due to validation warnings"
        )

    try:
        profile, applied = await install_theme_package(
            inspect_result.session_id,
            set_active=set_active,
            existing_profile_ids=existing_profile_ids,
        )
    except ThemePackageInstallError as error:
        raise ThemeMarketplaceInstallError(str(error)) from error

    if get_deployment_capabilities().is_sandbox_instance:
        await record_marketplace_install(listing_id=listing_id)

    return profile, applied, inspect_result.signature_status
