"""Tests for standard_responses.py — verify ListData[Any] type fix and factory functions."""

from app.database.standard_responses import (
    BusinessCode,
    ListData,
    StandardErrorResponse,
    StandardSuccessResponse,
    create_error_response,
    create_list_response,
    create_success_response,
)


class TestListData:
    """Ensure ListData with field named 'list' works (List[Any] vs list[Any])."""

    def test_list_data_creation(self) -> None:
        data = ListData(list=[1, 2, 3])
        assert data.list == [1, 2, 3]
        assert data.pagination is None

    def test_list_data_with_dicts(self) -> None:
        items = [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]
        data = ListData(list=items)
        assert len(data.list) == 2
        assert data.list[0]["name"] == "a"

    def test_list_data_empty(self) -> None:
        data = ListData(list=[])
        assert data.list == []

    def test_list_data_with_pagination(self) -> None:
        data = ListData(list=[1], pagination={"page": 1, "size": 10})
        assert data.pagination == {"page": 1, "size": 10}


class TestStandardResponses:
    def test_success_response(self) -> None:
        resp = create_success_response(data={"key": "value"})
        assert isinstance(resp, StandardSuccessResponse)
        assert resp.success is True
        assert resp.code == 0
        assert resp.data == {"key": "value"}

    def test_list_response(self) -> None:
        resp = create_list_response(items=[1, 2, 3])
        assert resp.success is True
        assert resp.data["list"] == [1, 2, 3]

    def test_error_response(self) -> None:
        resp = create_error_response(
            code=BusinessCode.VALIDATION_ERROR,
            message="Bad input",
        )
        assert isinstance(resp, StandardErrorResponse)
        assert resp.success is False
        assert resp.code == 40001
        assert resp.message == "Bad input"
