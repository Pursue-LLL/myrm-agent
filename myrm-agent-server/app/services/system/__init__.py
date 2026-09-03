"""System management, diagnostics, and technical support bundle services.

[INPUT]
- .storage_service::DatabaseStorageBreakdown, StorageOptimizePreflightData, SubdirUsage, check_storage_preflight, dir_size_bytes, execute_storage_optimization, get_sqlite_breakdown, perform_sqlite_backup
- .support_bundle_service::SupportBundleService
- .takeout_service::UserTakeoutService

[OUTPUT]
- Public package exports for system services

[POS]
Subsystem facade exporting storage governance, support bundle generation, and user data export services.
"""

from app.services.system.storage_service import (
    DatabaseStorageBreakdown,
    StorageOptimizePreflightData,
    SubdirUsage,
    check_storage_preflight,
    dir_size_bytes,
    execute_storage_optimization,
    get_sqlite_breakdown,
    perform_sqlite_backup,
)
from app.services.system.support_bundle_service import SupportBundleService
from app.services.system.takeout_service import UserTakeoutService

__all__ = [
    "DatabaseStorageBreakdown",
    "StorageOptimizePreflightData",
    "SubdirUsage",
    "SupportBundleService",
    "UserTakeoutService",
    "check_storage_preflight",
    "dir_size_bytes",
    "execute_storage_optimization",
    "get_sqlite_breakdown",
    "perform_sqlite_backup",
]
