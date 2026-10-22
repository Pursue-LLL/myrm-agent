"""Instance archive: export, import and restore points of a whole Myrm instance.

[INPUT]
- myrm_agent_harness.infra.state_archive (POS: generic archive/snapshot/promotion primitive)

[OUTPUT]
- ArchivePaths / ImportReport / PromotionOutcome: shared contracts
- ExportJobManager / InstanceImporter / UploadStore: the three user flows (get_export_manager: the one shared export manager)
- run_pending_promotion: pre-boot swap entry point (called by the server lifespan)
- restore point helpers

[POS]
Business policy layer over the harness primitive: what travels, what stays with
the target host, how secrets are protected, and how a swap is queued and
applied. See _ARCH.md for the file table and the data-class rules.
"""

from app.services.instance_archive.export_jobs import (
    ExportBusyError,
    ExportJob,
    ExportJobManager,
    JobState,
    get_export_manager,
)
from app.services.instance_archive.import_service import ImportEnvironment, ImportRejectedError, InstanceImporter
from app.services.instance_archive.models import (
    ArchivePaths,
    ImportReport,
    Operation,
    OutcomeStatus,
    PendingPromotion,
    PromotionOutcome,
)
from app.services.instance_archive.promotion_hook import (
    acknowledge_outcome,
    latest_aside,
    prepare_rollback,
    read_outcome,
    run_pending_promotion,
)
from app.services.instance_archive.restore_points import (
    RestorePoint,
    RestorePointError,
    create_pre_update_point,
    create_restore_point,
    delete_restore_point,
    list_restore_points,
    stage_restore,
)
from app.services.instance_archive.uploads import UploadError, UploadSession, UploadStore

__all__ = [
    "ArchivePaths",
    "ExportBusyError",
    "ExportJob",
    "ExportJobManager",
    "ImportEnvironment",
    "ImportRejectedError",
    "ImportReport",
    "InstanceImporter",
    "JobState",
    "Operation",
    "OutcomeStatus",
    "PendingPromotion",
    "PromotionOutcome",
    "RestorePoint",
    "RestorePointError",
    "UploadError",
    "UploadSession",
    "UploadStore",
    "acknowledge_outcome",
    "create_pre_update_point",
    "create_restore_point",
    "delete_restore_point",
    "get_export_manager",
    "latest_aside",
    "list_restore_points",
    "prepare_rollback",
    "read_outcome",
    "run_pending_promotion",
    "stage_restore",
]
