"""Document content extraction API endpoint

Extracts text from Office documents (.docx, .xlsx, .xls, .pptx, .ppt) using Harness file_parsers.
Returns AI-friendly Markdown text.

Supports two resolution modes:
- Sandbox: fileId → resolves via FilesService (StorageProvider)
- Local: filePath → direct local filesystem path

[INPUT]
- myrm_agent_harness.toolkits.file_parsers::DocxParser (POS: Word document parser)
- myrm_agent_harness.toolkits.file_parsers::ExcelParser (POS: Excel file parser)
- app.core.storage::files_service (POS: File storage service)

[OUTPUT]
- POST /extract-document: Extract text from Office documents

[POS]
Document content extraction API. Converts .docx/.xlsx/.xls/.pptx/.ppt to Markdown via Harness parsers.
"""

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

from app.config.deploy_mode import is_local_mode
from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.storage import files_service
from app.core.utils.errors import internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse
from app.services.files.content_extraction import SUPPORTED_OFFICE_EXTENSIONS

logger = logging.getLogger(__name__)

router = APIRouter()


class DocumentExtractRequest(BaseModel):
    """Sandbox mode: provide fileId.
    Local mode: provide filePath (direct local path).
    """

    file_id: str | None = Field(default=None, description="File ID (sandbox mode)")
    file_path: str | None = Field(default=None, description="Local file path (local mode)")

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class DocumentExtractResponse(BaseModel):
    text: str = Field(default="", description="Extracted Markdown text")
    format: str = Field(default="", description="Source format (docx/xlsx/xls)")
    char_count: int = Field(default=0, description="Character count of extracted text")

    class Config:
        alias_generator = to_camel
        populate_by_name = True


def _validate_extension(filename: str) -> str:
    """Validate file extension and return it."""
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_OFFICE_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_OFFICE_EXTENSIONS))
        raise validation_error(f"Unsupported format: {ext}. Supported: {supported}")
    return ext


async def _resolve_document_path(body: DocumentExtractRequest) -> tuple[Path, str, bool]:
    """Resolve the actual filesystem path from the request.

    Returns: (path, extension, is_temp_file)
    """
    if body.file_path:
        if not is_local_mode():
            raise validation_error("filePath is only allowed in local mode")
        path = Path(body.file_path)
        if not path.exists():
            raise not_found_error("Document file")
        ext = _validate_extension(path.name)
        return path, ext, False

    if body.file_id:
        file = await files_service.get_file(body.file_id)
        if not file:
            raise not_found_error("Document file")
        ext = _validate_extension(file.filename)
        content = await files_service.get_content(body.file_id)

        tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        tmp.write(content)
        tmp.flush()
        tmp.close()
        return Path(tmp.name), ext, True

    raise validation_error("Provide either filePath or fileId")


@router.post("/extract-document", response_model=StandardSuccessResponse)
@limiter.limit(settings.rate_limit.file_upload)
async def extract_document(
    body: DocumentExtractRequest,
    request: Request,
) -> JSONResponse:
    """Extract text from an Office document (.docx, .xlsx, .xls).

    Returns AI-friendly Markdown text.
    Auth: required (single-tenant request identity)
    """
    file_path, ext, is_temp = await _resolve_document_path(body)

    try:
        from app.services.files.content_extraction import extract_document_from_path

        text = await extract_document_from_path(file_path, ext)
    except Exception as e:
        logger.error("Document extraction failed for %s: %s", file_path, e)
        raise internal_error(operation="Document extraction", exception=e) from e
    finally:
        if is_temp and file_path.exists():
            file_path.unlink(missing_ok=True)

    response_data = DocumentExtractResponse(
        text=text,
        format=ext.lstrip("."),
        char_count=len(text),
    )

    return success_response(data=response_data.model_dump(by_alias=True))
