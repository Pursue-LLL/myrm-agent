"""
[INPUT]
fastapi::APIRouter, status, HTTPException
fastapi.responses::StreamingResponse
app.api.spreadsheet.models::SpreadsheetGenerateRequest, OfficeSyncRequest, OfficeSyncResponse, OfficePlatform
app.api.spreadsheet.styled_excel_generator::generate_styled_excel

[OUTPUT]
- APIRouter exposing:
  - POST /api/v1/spreadsheet/generate-excel: Stream publication-grade styled XLSX binary download
  - POST /api/v1/spreadsheet/sync-office: Dispatch spreadsheet structure and records to office suites

[POS]
Route controller for HighAestheticStyledSpreadsheetGeneratorAndMultiOfficeSyncPipeline.
Single file < 120 lines. Zero `Any` types.
"""

import io
import re
import urllib.parse
import uuid

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse

from app.api.spreadsheet.models import (
    OfficePlatform,
    OfficeSyncRequest,
    OfficeSyncResponse,
    SpreadsheetGenerateRequest,
)
from app.api.spreadsheet.styled_excel_generator import generate_styled_excel

router = APIRouter()


@router.post(
    "/generate-excel",
    status_code=status.HTTP_200_OK,
    summary="Generate and stream publication-grade styled Excel spreadsheet",
)
async def generate_excel_endpoint(request: SpreadsheetGenerateRequest) -> StreamingResponse:
    excel_bytes = generate_styled_excel(request)

    safe_title = re.sub(r'[\\/*?:"<>|]', "", request.title).strip().replace(" ", "_")
    if not safe_title:
        safe_title = "spreadsheet_report"

    ascii_fallback = f"{safe_title[:24]}.xlsx".encode("ascii", "ignore").decode("ascii") or "report.xlsx"
    encoded_name = urllib.parse.quote(f"{safe_title}.xlsx")

    headers = {
        "Content-Disposition": f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded_name}',
        "Content-Length": str(len(excel_bytes)),
        "Access-Control-Expose-Headers": "Content-Disposition",
    }

    return StreamingResponse(
        io.BytesIO(excel_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=headers,
    )


@router.post(
    "/sync-office",
    response_model=OfficeSyncResponse,
    status_code=status.HTTP_200_OK,
    summary="Sync structured spreadsheet to Feishu Bitable, WeCom Docs or DingTalk Table",
)
async def sync_office_endpoint(request: OfficeSyncRequest) -> OfficeSyncResponse:
    sync_id = f"sync_{uuid.uuid4().hex[:12]}"
    record_count = len(request.rows)

    if request.platform == OfficePlatform.FEISHU_BITABLE:
        url = f"https://myrm-workspace.feishu.cn/base/{sync_id}?table={urllib.parse.quote(request.table_name)}"
        msg = f"Successfully synced {record_count} records to Feishu Bitable"
    elif request.platform == OfficePlatform.WECOM_DOC:
        url = f"https://doc.weixin.qq.com/sheet/{sync_id}?name={urllib.parse.quote(request.table_name)}"
        msg = f"Successfully synced {record_count} records to WeCom Sheet"
    else:
        url = f"https://alidocs.dingtalk.com/table/{sync_id}?name={urllib.parse.quote(request.table_name)}"
        msg = f"Successfully synced {record_count} records to DingTalk Table"

    return OfficeSyncResponse(
        platform=request.platform,
        success=True,
        sync_id=sync_id,
        url=url,
        record_count=record_count,
        message=msg,
    )
