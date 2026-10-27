"""Failure classification of a finished CLI attempt: the CLI's own words first, the exit code last."""

from __future__ import annotations

from myrm_agent_harness.toolkits.acp.runtime.cli.failure import classify_failure
from myrm_agent_harness.toolkits.acp.runtime.cli.parser import FAILURE_TEXT_CHARS
from myrm_agent_harness.toolkits.acp.runtime.cli.turn_parser import CliResult
from myrm_agent_harness.toolkits.acp.types import AcpErrorCode


def _result(**overrides: object) -> CliResult:
    fields: dict[str, object] = {
        "is_error": True,
        "subtype": "",
        "message": "",
        "terminal_reason": "",
        "api_error_status": None,
        "assistant_error": "",
    }
    fields.update(overrides)
    return CliResult(**fields)  # type: ignore[arg-type]


def _classify(
    result: CliResult | None = None,
    *,
    returncode: int = 1,
    stderr: str = "",
    killed: bool = False,
    notice: str = "",
    auth_rejection: str = "",
):
    return classify_failure(
        result=result,
        returncode=returncode,
        stderr=stderr,
        killed=killed,
        notice=notice,
        auth_rejection=auth_rejection,
    )


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


def test_a_run_stopped_for_a_rejected_login_is_an_auth_failure_not_a_cancellation() -> None:
    error = _classify(None, returncode=-15, killed=True, auth_rejection="API request rejected with HTTP 401")

    assert error is not None
    assert error.code is AcpErrorCode.AUTH_FAILED
    assert error.message == "API request rejected with HTTP 401"
    assert error.retryable is False


def test_an_unauthorized_api_error_needs_the_user_not_a_retry() -> None:
    error = _classify(_result(message="API Error: 401", api_error_status=401))

    assert error is not None
    assert error.code is AcpErrorCode.AUTH_FAILED
    assert error.retryable is False


def test_a_rejected_login_is_one_whatever_category_the_cli_gave_it() -> None:
    error = _classify(_result(message="API Error: 401", api_error_status=401, assistant_error="invalid_request"))

    assert error is not None
    assert error.code is AcpErrorCode.AUTH_FAILED


def test_a_forbidden_api_error_is_not_a_login_problem_even_under_the_auth_category() -> None:
    # A blocked region or an organization policy answers 403 with the same category as a rejected login; telling that
    # user to sign in again would send them the wrong way, so they get the CLI's own words.
    for category in ("", "authentication_failed"):
        error = _classify(
            _result(message="API Error: 403 Request not allowed", api_error_status=403, assistant_error=category)
        )

        assert error is not None
        assert error.code is AcpErrorCode.UNKNOWN
        assert error.message == "API Error: 403 Request not allowed"
        assert error.retryable is False


def test_a_missing_login_is_an_auth_failure_although_no_api_call_was_made() -> None:
    error = _classify(
        _result(message="Not logged in · Please run /login", assistant_error="authentication_failed"),
    )

    assert error is not None
    assert error.code is AcpErrorCode.AUTH_FAILED
    assert error.message == "Not logged in · Please run /login"
    assert error.retryable is False


def test_the_other_error_categories_do_not_make_an_auth_failure() -> None:
    for category in ("invalid_request", "rate_limit", "billing_error", "model_not_found", "server_error"):
        error = _classify(_result(message="boom", assistant_error=category))

        assert error is not None
        assert error.code is AcpErrorCode.UNKNOWN, category


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


def test_the_last_error_line_explains_a_crash_better_than_the_stderr() -> None:
    error = _classify(None, returncode=1, stderr="Reading additional input from stdin...", notice="model not supported")

    assert error is not None
    assert error.code is AcpErrorCode.PROCESS_CRASHED
    assert error.message == "CLI process exited with code 1: model not supported"


def test_an_error_line_never_turns_a_clean_exit_or_a_verdict_into_another_failure() -> None:
    assert _classify(None, returncode=0, notice="Reconnecting... 2/5") is None
    verdict = _classify(_result(message="API Error: 400", api_error_status=400), notice="Reconnecting... 2/5")

    assert verdict is not None
    assert verdict.message == "API Error: 400"


def test_a_crash_without_stderr_has_no_dangling_colon() -> None:
    error = _classify(None, returncode=2, stderr="")

    assert error is not None
    assert error.message == "CLI process exited with code 2"


def test_the_stderr_excerpt_is_bounded() -> None:
    error = _classify(None, returncode=1, stderr="e" * 5000)

    assert error is not None
    assert len(error.message) == len("CLI process exited with code 1: ") + FAILURE_TEXT_CHARS
    assert error.message.endswith("\u2026")


def test_a_web_page_in_the_stderr_is_not_the_excerpt() -> None:
    page = "<html>\n<head><title>Access denied</title></head>\n<body>" + "<p>blocked</p>" * 400 + "</body>\n</html>"

    error = _classify(None, returncode=1, stderr="error: " + page)

    assert error is not None
    assert error.message == "CLI process exited with code 1: error: [web page: Access denied]"


def test_a_success_result_with_a_nonzero_exit_is_still_a_crash() -> None:
    error = _classify(_result(is_error=False, subtype="success"), returncode=1, stderr="late failure")

    assert error is not None
    assert error.code is AcpErrorCode.PROCESS_CRASHED
