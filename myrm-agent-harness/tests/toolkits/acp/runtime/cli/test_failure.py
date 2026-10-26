"""Failure classification of a finished CLI attempt: the CLI's own words first, the exit code last."""

from __future__ import annotations

from myrm_agent_harness.toolkits.acp.runtime.cli.failure import classify_failure
from myrm_agent_harness.toolkits.acp.runtime.cli.turn_parser import CliResult
from myrm_agent_harness.toolkits.acp.types import AcpErrorCode


def _result(**overrides: object) -> CliResult:
    fields: dict[str, object] = {
        "is_error": True,
        "subtype": "",
        "message": "",
        "terminal_reason": "",
        "api_error_status": None,
    }
    fields.update(overrides)
    return CliResult(**fields)  # type: ignore[arg-type]


def _classify(result: CliResult | None = None, *, returncode: int = 1, stderr: str = "", killed: bool = False):
    return classify_failure(result=result, returncode=returncode, stderr=stderr, killed=killed)


def test_a_clean_exit_without_an_error_result_succeeded() -> None:
    assert _classify(None, returncode=0) is None
    assert _classify(_result(is_error=False, subtype="success"), returncode=0) is None


def test_a_process_we_stopped_is_a_cancellation_whatever_it_exited_with() -> None:
    error = _classify(_result(message="aborted"), returncode=143, killed=True)

    assert error is not None
    assert error.code is AcpErrorCode.CANCELLED


def test_the_turn_limit_is_named_with_the_cli_own_text() -> None:
    by_subtype = _classify(_result(subtype="error_max_turns", message="Reached maximum number of turns (3)"))
    by_reason = _classify(_result(terminal_reason="max_turns"))

    assert by_subtype is not None
    assert by_subtype.code is AcpErrorCode.MAX_TURNS
    assert by_subtype.message == "Reached maximum number of turns (3)"
    assert by_reason is not None
    assert by_reason.code is AcpErrorCode.MAX_TURNS


def test_an_unauthorized_api_error_needs_the_user_not_a_retry() -> None:
    for status in (401, 403):
        error = _classify(_result(message="API Error: 401", api_error_status=status))

        assert error is not None
        assert error.code is AcpErrorCode.AUTH_FAILED
        assert error.retryable is False


def test_a_rate_limit_is_retryable() -> None:
    error = _classify(_result(message="API Error: 429", api_error_status=429))

    assert error is not None
    assert error.code is AcpErrorCode.RATE_LIMITED
    assert error.retryable is True


def test_a_server_side_api_error_is_retryable_and_a_client_one_is_not() -> None:
    server = _classify(_result(message="API Error: 503", api_error_status=503))
    client = _classify(_result(message="API Error: 400", api_error_status=400))
    unknown = _classify(_result(message="boom"))

    assert server is not None and server.retryable is True
    assert client is not None and client.retryable is False and client.code is AcpErrorCode.UNKNOWN
    assert unknown is not None and unknown.retryable is False


def test_an_error_result_without_text_still_says_something() -> None:
    error = _classify(_result())

    assert error is not None
    assert error.message == "The CLI reported an error"


def test_an_error_result_wins_over_the_exit_code() -> None:
    error = _classify(_result(message="API Error: 400", api_error_status=400), returncode=0)

    assert error is not None
    assert error.message == "API Error: 400"


def test_a_crash_without_a_verdict_reports_the_exit_code_and_the_stderr_excerpt() -> None:
    error = _classify(None, returncode=3, stderr="  segfault  ")

    assert error is not None
    assert error.code is AcpErrorCode.PROCESS_CRASHED
    assert error.retryable is True
    assert error.message == "CLI process exited with code 3: segfault"


def test_a_crash_without_stderr_has_no_dangling_colon() -> None:
    error = _classify(None, returncode=2, stderr="")

    assert error is not None
    assert error.message == "CLI process exited with code 2"


def test_the_stderr_excerpt_is_bounded() -> None:
    error = _classify(None, returncode=1, stderr="e" * 5000)

    assert error is not None
    assert len(error.message) < 600


def test_a_success_result_with_a_nonzero_exit_is_still_a_crash() -> None:
    error = _classify(_result(is_error=False, subtype="success"), returncode=1, stderr="late failure")

    assert error is not None
    assert error.code is AcpErrorCode.PROCESS_CRASHED
