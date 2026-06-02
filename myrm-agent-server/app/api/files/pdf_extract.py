"""PDF content extraction API endpoint

Extracts text and/or images from a PDF file.
Strategy: text-first via pdfplumber; image-fallback via pypdfium2 when text is sparse.

Supports two resolution modes:
- Sandbox: fileId → resolves via FilesService (StorageProvider)
- Local: filePath → direct local filesystem path
"""

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from myrm_agent_harness.toolkits.file_parsers.pdf_content_extractor import (
    PDFExtractConfig,
    extract_pdf_content,
)
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

from app.config.deploy_mode import is_local_mode
from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.core.storage import files_service
from app.core.utils.errors import not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse

logger = logging.getLogger(__name__)

router = APIRouter()


class PDFImageItem(BaseModel):
    data: str = Field(..., description="Base64-encoded PNG data")
    mime_type: str = Field(default="image/png", description="MIME type")


class PDFTableItem(BaseModel):
    page_number: int
    table_index: int
    data: list[list[str]]
    id: str
    markdown: str
    summary_l0: str

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class PDFExtractResponse(BaseModel):
    text: str = Field(default="", description="Extracted text (may be empty for scanned PDFs)")
    images: list[PDFImageItem] = Field(default=[], description="Rendered page images (only when text is sparse)")
    page_count: int = Field(default=0, description="Total pages in PDF")
    strategy: str = Field(default="", description="Extraction strategy: 'text', 'image', or 'hybrid'")
    tables: list[PDFTableItem] = Field(default=[], description="Extracted table capsules with L0 summaries and L2 markdown")
    image_trace: dict[str, object] = Field(
        default_factory=dict, description="Diagnostic trace of the image ablation process (heuristic filtering details)"
    )

    class Config:
        alias_generator = to_camel
        populate_by_name = True


class PDFExtractRequest(BaseModel):
    """Sandbox mode: provide fileId.
    Local mode: provide filePath (direct local path).
    """

    file_id: str | None = Field(default=None, description="File ID (sandbox mode)")
    file_path: str | None = Field(default=None, description="Local file path (local mode)")
    max_pages: int = Field(default=20, ge=1, le=50, description="Max pages to process")
    min_text_chars: int = Field(default=200, ge=0, description="Min chars before image fallback")
    table_format: str = Field(default="placeholder", description="Table output: 'inline' or 'placeholder'")

    class Config:
        alias_generator = to_camel
        populate_by_name = True


async def _resolve_pdf_path(body: PDFExtractRequest) -> Path:
    """Resolve the actual filesystem path from the request."""
    if body.file_path:
        if not is_local_mode():
            raise validation_error("filePath is only allowed in local mode")
        path = Path(body.file_path)
        if not path.exists():
            raise not_found_error("PDF file")
        if path.suffix.lower() != ".pdf":
            raise validation_error("Only PDF files are supported")
        return path

    if body.file_id:
        file = await files_service.get_file(body.file_id)
        if not file:
            raise not_found_error("PDF file")
        if not file.filename.lower().endswith(".pdf"):
            raise validation_error("Only PDF files are supported")

        content = await files_service.get_content(body.file_id)

        # extract_pdf_content 需要文件路径，写入临时文件
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.write(content)
        tmp.flush()
        tmp.close()
        return Path(tmp.name)

    raise validation_error("Provide either filePath or fileId")


@router.post("/extract-pdf", response_model=StandardSuccessResponse)
@limiter.limit(settings.rate_limit.file_upload)
async def extract_pdf(
    body: PDFExtractRequest,
    request: Request,
) -> JSONResponse:
    """Extract text and/or images from a PDF file.

    Auth: required (single-tenant request identity)
    """
    file_path = await _resolve_pdf_path(body)

    try:
        config = PDFExtractConfig(
            max_pages=body.max_pages,
            min_text_chars=body.min_text_chars,
            table_format=body.table_format,

        )
        result = await extract_pdf_content(str(file_path), config)
    finally:
        # 清理 Sandbox 模式下创建的临时文件
        if body.file_id and file_path.exists():
            file_path.unlink(missing_ok=True)

    response_data = PDFExtractResponse(
        text=result.text,
        images=[PDFImageItem(data=img.data, mime_type=img.mime_type) for img in result.images],
        page_count=result.page_count,
        strategy=result.strategy,
        tables=[
            PDFTableItem(
                page_number=t.page_number,
                table_index=t.table_index,
                data=t.data,
                id=t.id,
                markdown=t.markdown,
                summary_l0=t.summary_l0,
            )
            for t in result.tables
        ],
        image_trace=result.image_trace,
    )

    return success_response(data=response_data.model_dump(by_alias=True))
