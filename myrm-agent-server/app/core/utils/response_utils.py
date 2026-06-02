"""Response utility classes for standardized API responses.

[INPUT]
app.database.standard_responses (POS: 标准响应模型和构造函数)

[OUTPUT]
ResponseUtils: 标准响应工具类
success_response / list_response / paginated_response / error_response: 快捷函数

[POS]
统一 API 响应格式工具。封装标准化的成功/列表/分页/错误响应构造。
"""

from fastapi.responses import JSONResponse

from app.database.standard_responses import (
    PaginationInfo,
    create_error_response,
    create_list_response,
    create_success_response,
)


class ResponseUtils:
    """Standardized API response builder."""

    @staticmethod
    def success(data: object = None, status_code: int = 200) -> JSONResponse:
        response = create_success_response(data=data)
        return JSONResponse(content=response.model_dump(mode="json"), status_code=status_code)

    @staticmethod
    def created(data: object = None) -> JSONResponse:
        response = create_success_response(data=data)
        return JSONResponse(content=response.model_dump(mode="json"), status_code=201)

    @staticmethod
    def no_content() -> JSONResponse:
        response = create_success_response()
        return JSONResponse(content=response.model_dump(mode="json"), status_code=204)

    @staticmethod
    def list_response(items: list[object], pagination: PaginationInfo | None = None) -> JSONResponse:
        response = create_list_response(items=items, pagination=pagination)
        return JSONResponse(content=response.model_dump(mode="json"), status_code=200)

    @staticmethod
    def paginated_response(items: list[object], current_page: int, page_size: int, total: int) -> JSONResponse:
        total_pages = (total + page_size - 1) // page_size
        pagination = PaginationInfo(current_page=current_page, page_size=page_size, total=total, total_pages=total_pages)
        return ResponseUtils.list_response(items=items, pagination=pagination)


def success_response(data: object = None, status_code: int = 200) -> JSONResponse:
    return ResponseUtils.success(data=data, status_code=status_code)


def list_response(items: list[object], pagination: PaginationInfo | None = None) -> JSONResponse:
    return ResponseUtils.list_response(items=items, pagination=pagination)


def paginated_response(items: list[object], current_page: int, page_size: int, total: int) -> JSONResponse:
    return ResponseUtils.paginated_response(items=items, current_page=current_page, page_size=page_size, total=total)


def error_response(message: str, code: int = 400, status_code: int = 200) -> JSONResponse:
    response = create_error_response(code=code, message=message)
    return JSONResponse(content=response.model_dump(mode="json"), status_code=status_code)
