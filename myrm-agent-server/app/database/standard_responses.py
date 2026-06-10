"""Standardized API response models and builders.

[OUTPUT]
StandardSuccessResponse, StandardErrorResponse: Pydantic response models
PaginationInfo, BusinessCode: Common data structures
create_success_response, create_list_response, create_error_response: Factory functions

[POS]
统一 API 响应格式定义。所有端点的响应结构通过此模块标准化。
"""

from enum import IntEnum
from typing import Any, List
from uuid import uuid4

from pydantic import BaseModel, Field

# Note: Pydantic requires `Any` for dynamically-typed JSON fields.
# Using `object` causes FieldInfo subscript errors at class definition time.


class StandardSuccessResponse(BaseModel):
    success: bool = Field(True, description="Whether the request was successful")
    code: int = Field(0, description="Business status code, 0 means success")
    data: Any = Field(None, description="Response payload")


class ErrorDetail(BaseModel):
    field: str | None = Field(None, description="Error field name")
    issue: str = Field(..., description="Error description")


class ErrorInfo(BaseModel):
    details: list[ErrorDetail] | None = Field(None, description="Detailed error information")
    trace_id: str = Field(default_factory=lambda: str(uuid4()), description="Trace ID")


class StandardErrorResponse(BaseModel):
    success: bool = Field(False, description="Whether the request was successful")
    code: int = Field(..., description="Business error code")
    message: str = Field(..., description="Error message")
    error: ErrorInfo | None = Field(None, description="Error details")


class ListData(BaseModel):
    list: List[Any] = Field(..., description="Data list")
    pagination: dict[str, Any] | None = Field(None, description="Pagination info")


class PaginationInfo(BaseModel):
    current_page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Page size")
    total: int = Field(..., description="Total records")
    total_pages: int = Field(..., description="Total pages")


class BusinessCode(IntEnum):
    """Business status codes.

    Code Structure:
    - 0: Success
    - 40xxx: Client errors
    - 50xxx: Server errors
    - 51xxx: Database errors
    - 52xxx: External service errors
    - 53xxx: AI/Model errors
    """

    SUCCESS = 0

    VALIDATION_ERROR = 40001
    AUTHENTICATION_FAILED = 40101
    PERMISSION_DENIED = 40301
    RESOURCE_NOT_FOUND = 40401
    RESOURCE_CONFLICT = 40901
    RATE_LIMIT_ERROR = 42901

    INTERNAL_ERROR = 50001
    SERVICE_UNAVAILABLE = 50003
    TIMEOUT_ERROR = 50008

    DB_CONNECTION_ERROR = 51001
    DB_QUERY_ERROR = 51002
    DB_INTEGRITY_ERROR = 51003
    DB_TIMEOUT_ERROR = 51004
    DB_STORAGE_BUSY = 51005

    EXTERNAL_SERVICE_ERROR = 52001
    SEARCH_SERVICE_ERROR = 52002
    FILE_SERVICE_ERROR = 52003

    AI_MODEL_ERROR = 53001
    AI_RATE_LIMIT_ERROR = 53002
    AI_AUTH_ERROR = 53003
    AI_TIMEOUT_ERROR = 53004


def create_success_response(data: Any = None, code: int = BusinessCode.SUCCESS) -> StandardSuccessResponse:
    return StandardSuccessResponse(success=True, code=code, data=data)


def create_list_response(items: list[Any], pagination: PaginationInfo | None = None) -> StandardSuccessResponse:
    data: dict[str, Any] = {"list": items}
    if pagination:
        data["pagination"] = pagination.model_dump()
    return StandardSuccessResponse(success=True, code=BusinessCode.SUCCESS, data=data)


def create_error_response(
    code: int, message: str, details: list[ErrorDetail] | None = None, trace_id: str | None = None
) -> StandardErrorResponse:
    error_info = None
    if details or trace_id:
        error_info = ErrorInfo(details=details, trace_id=trace_id or str(uuid4()))
    return StandardErrorResponse(success=False, code=code, message=message, error=error_info)
