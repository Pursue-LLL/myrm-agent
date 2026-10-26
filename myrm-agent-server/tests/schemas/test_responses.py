"""Tests for schemas/responses.py — verify ListData[Any] type fix and factory functions."""

from collections.abc import Iterator
from contextlib import contextmanager

from myrm_agent_harness.observability.tracing import TracingContext

from app.schemas.responses import (
    BusinessCode,
    ErrorDetail,
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


_REQUEST_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"


@contextmanager
def _serving_request(trace_id: str) -> Iterator[None]:
    token = TracingContext.set_trace_id(trace_id)
    try:
        yield
    finally:
        TracingContext.reset_trace_id(token)


class TestErrorEnvelopeTraceId:
    """The envelope names the request it answers, so an id a user reports finds that request's logs and trace."""

    def test_client_error_without_details_stays_a_message(self) -> None:
        with _serving_request(_REQUEST_TRACE_ID):
            resp = create_error_response(code=BusinessCode.RESOURCE_NOT_FOUND, message="Missing")

        assert resp.error is None

    def test_server_fault_carries_the_request_trace_id(self) -> None:
        with _serving_request(_REQUEST_TRACE_ID):
            resp = create_error_response(code=BusinessCode.INTERNAL_ERROR, message="Boom")

        assert resp.error is not None
        assert resp.error.trace_id == _REQUEST_TRACE_ID

    def test_details_carry_the_request_trace_id(self) -> None:
        with _serving_request(_REQUEST_TRACE_ID):
            resp = create_error_response(
                code=BusinessCode.VALIDATION_ERROR,
                message="Bad input",
                details=[ErrorDetail(field="name", issue="required")],
            )

        assert resp.error is not None
        assert resp.error.trace_id == _REQUEST_TRACE_ID
        assert resp.error.details == [ErrorDetail(field="name", issue="required")]

    def test_an_explicit_trace_id_wins_over_the_request(self) -> None:
        with _serving_request(_REQUEST_TRACE_ID):
            resp = create_error_response(code=BusinessCode.RESOURCE_NOT_FOUND, message="Missing", trace_id="given")

        assert resp.error is not None
        assert resp.error.trace_id == "given"

    def test_outside_a_request_every_envelope_gets_a_fresh_id(self) -> None:
        first = create_error_response(code=BusinessCode.INTERNAL_ERROR, message="Boom")
        second = create_error_response(code=BusinessCode.INTERNAL_ERROR, message="Boom")

        assert first.error is not None and second.error is not None
        assert first.error.trace_id and first.error.trace_id != second.error.trace_id
