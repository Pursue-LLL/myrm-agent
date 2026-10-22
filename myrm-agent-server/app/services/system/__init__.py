"""System management, diagnostics, and technical support bundle services.

[INPUT]
- .storage_service::DatabaseStorageBreakdown, StorageOptimizePreflightData, check_storage_preflight, execute_storage_optimization, get_sqlite_breakdown, perform_sqlite_backup
- .support_bundle_service::SupportBundleService

[OUTPUT]
- Public package exports for system services

[POS]
Subsystem facade exporting storage governance and support bundle generation services.
"""

from app.services.system.model_ping_service import (
    ModelPingResult,
    ModelPingService,
    get_model_ping_service,
)
from app.services.system.storage_service import (
    DatabaseStorageBreakdown,
    StorageOptimizePreflightData,
    check_storage_preflight,
    execute_storage_optimization,
    get_sqlite_breakdown,
    perform_sqlite_backup,
)
from app.services.system.support_bundle_service import SupportBundleService
from app.services.system.vault_purge_service import (
    SafeVaultPurgeResult,
    SafeVaultPurgeService,
)

__all__ = [
    "DatabaseStorageBreakdown",
    "ModelPingResult",
    "ModelPingService",
    "SafeVaultPurgeResult",
    "SafeVaultPurgeService",
    "StorageOptimizePreflightData",
    "SupportBundleService",
    "check_storage_preflight",
    "execute_storage_optimization",
    "get_model_ping_service",
    "get_sqlite_breakdown",
    "perform_sqlite_backup",
]
