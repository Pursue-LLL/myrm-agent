"""The provider's own words reach the user as one clean line.

The unknown fallback and the rejected-request diagnosis show what the provider said. That text comes from gateways,
relays and SDKs, so it can carry a credential the gateway echoes, a whole HTML error page, or the SDK's dict framing
around the one sentence worth reading. The line the card shows has none of that, and a secret is masked before the
text is cut so no half of one is left at the boundary.
"""

import pytest

from myrm_agent_harness.agent.errors.diagnostics import LLMErrorDiagnostic

_KEY = "sk-proj-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
_KEY_BODY = "AbCdEfGhIjKlMnOpQrStUvWxYz"


def _shown(text: str, locale: str = "en") -> str:
    result = LLMErrorDiagnostic.diagnose(RuntimeError(text), locale=locale)
    assert result.error_type == "unknown"
    return result.user_message


@pytest.mark.parametrize(
    "text",
    [
        f"weird failure for key {_KEY}",
        f"Authorization: Bearer {_KEY} was rejected by the gateway",
        f"gateway echoed api_key={_KEY}&retry=1",
    ],
    ids=["bare key", "bearer header", "query string"],
)
def test_a_credential_in_the_provider_text_is_masked(text: str) -> None:
    shown = _shown(text)

    assert _KEY not in shown
    assert _KEY_BODY not in shown


def test_a_credential_at_the_cut_is_masked_before_the_text_is_cut() -> None:
    shown = _shown("x " * 90 + _KEY)

    assert "AbCdEf" not in shown


@pytest.mark.timeout(5)
@pytest.mark.parametrize("quote", ['"', "'"], ids=["json body", "python dict body"])
def test_a_body_cut_off_inside_a_run_of_backslashes_is_read_in_linear_time(quote: str) -> None:
    """The text is cut at a fixed length before it is read, so a long escaped path can end mid-string."""
    cut_off_body = "{" + quote + "message" + quote + ": " + quote + "\\" * 1900

    assert _shown(cut_off_body)


def test_an_html_error_page_shows_its_text_without_markup_or_scripts() -> None:
    page = (
        "<html><head><title>405 Not Allowed</title><style>h1{color:red}</style></head>"
        "<body><script>var tracking = 1;</script><center><h1>405 Not Allowed</h1></center>"
        "<hr><center>nginx/1.18.0</center></body></html>"
    )

    shown = _shown(page)

    assert "405 Not Allowed" in shown
    assert "nginx/1.18.0" in shown
    assert not any(leftover in shown for leftover in ("<", ">", "tracking", "color:red"))


def test_an_error_body_shows_its_message_field() -> None:
    body = '{"type":"error","error":{"type":"invalid_request_error","message":"tool_use ids must be unique"}}'

    shown = _shown(f"AnthropicException - {body}")

    assert shown.endswith("tool_use ids must be unique")


def test_a_python_dict_body_is_unescaped() -> None:
    shown = _shown("Error code: 418 - {'error': {'message': 'it\\'s a teapot', 'type': 'teapot'}}")

    assert shown.endswith("it's a teapot")


def test_prose_with_angle_brackets_is_left_alone() -> None:
    assert _shown("expected <int> but got <str>").endswith("expected <int> but got <str>")


def test_line_breaks_in_the_provider_text_collapse_to_spaces() -> None:
    assert _shown("first line\n\n   second\tline").endswith("first line second line")


def test_a_silent_exception_still_names_what_failed() -> None:
    assert _shown("").endswith("RuntimeError")
