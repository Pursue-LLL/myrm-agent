"""Skills batch-import API domain: preview / confirm + execute + schemas.

[INPUT]
- Import preview/confirm payloads from the skills router (JSON body).
- Skill staging metadata produced by ``app.api.skills._staging``.

[OUTPUT]
- Aggregate facade re-exporting every public name of the ``batch_import``
  subpackage:
  - batch_import: ``router`` (APIRouter prefix `/batch-import`) + preview/confirm
    endpoint handlers
  - batch_import_execute: execute_batch_import_confirm (write path)
  - batch_import_helpers: internal error mapping helpers
  - batch_import_schemas: ImportPreviewSkillItem / ImportPreviewResponse /
    ConfirmImportItem / ConfirmImportRequest / ConfirmImportResponse

[POS]
Server business layer (Skills API). Single batch-import domain: router, write
path, helpers and schemas are always wired together and mounted via
``api.skills.router``, so they stay co-located under one facade.
"""

from app.api.skills.batch_import.batch_import import router
from app.api.skills.batch_import.batch_import_execute import execute_batch_import_confirm
from app.api.skills.batch_import.batch_import_schemas import (
    ConfirmImportItem,
    ConfirmImportRequest,
    ConfirmImportResponse,
    ImportPreviewResponse,
    ImportPreviewSkillItem,
)

__all__ = [
    "ConfirmImportItem",
    "ConfirmImportRequest",
    "ConfirmImportResponse",
    "ImportPreviewResponse",
    "ImportPreviewSkillItem",
    "execute_batch_import_confirm",
    "router",
]
