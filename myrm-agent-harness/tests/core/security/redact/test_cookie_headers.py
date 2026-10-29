"""Cookie and Set-Cookie header lines carry the session, so their value is masked whole.

``curl -v``, a request dump or a pasted HTTP exchange shows them as raw header lines; a command shows them as a quoted
``-H`` argument. A cookie header is a list of ``name=value`` pairs separated by ``; ``, so a mask that stops at the first
space would leave the second cookie readable.
"""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.core.security.redact import redact_sensitive_text

_SESSION = "sessionid=Zk3fQ9xLm2Pq7Rt1; csrftoken=Vb8nWc4Yd6Xe0Aj5"
_LEAKS = ("Zk3fQ9xL", "Vb8nWc4Y", "csrftoken")


def _masked(text: str) -> str:
    return redact_sensitive_text(text)


class TestRawHeaderLines:
    def test_a_cookie_header_is_masked_to_the_end_of_the_line(self) -> None:
        text = f"GET /api HTTP/1.1\nHost: app.example\nCookie: {_SESSION}\nAccept: */*"
        assert _masked(text) == "GET /api HTTP/1.1\nHost: app.example\nCookie: ***\nAccept: */*"

    def test_a_set_cookie_header_is_masked_with_its_attributes(self) -> None:
        text = f"HTTP/1.1 200 OK\nSet-Cookie: {_SESSION}; Path=/; HttpOnly; Secure\nContent-Length: 2"
        assert _masked(text) == "HTTP/1.1 200 OK\nSet-Cookie: ***\nContent-Length: 2"

    @pytest.mark.parametrize("prefix", ["> ", "< ", "  ", "\t", ">", "[stderr] "])
    def test_a_trace_prefix_does_not_hide_the_header(self, prefix: str) -> None:
        masked = _masked(f"{prefix}Cookie: {_SESSION}\n{prefix}Accept: */*")
        assert not any(leak in masked for leak in _LEAKS)
        assert masked.endswith(f"{prefix}Accept: */*")

    @pytest.mark.parametrize("name", ["cookie", "COOKIE", "Cookie", "set-cookie", "SET-COOKIE", "Set-Cookie"])
    def test_the_header_name_is_matched_in_any_case(self, name: str) -> None:
        assert _masked(f"{name}: {_SESSION}") == f"{name}: ***"

    @pytest.mark.parametrize("separator", [":", ": ", ":  ", ":\t"])
    def test_the_space_after_the_colon_is_kept_as_written(self, separator: str) -> None:
        assert _masked(f"Cookie{separator}{_SESSION}") == f"Cookie{separator}***"

    def test_a_crlf_line_ending_is_kept(self) -> None:
        assert _masked(f"Cookie: {_SESSION}\r\nHost: a.example\r\n") == "Cookie: ***\r\nHost: a.example\r\n"

    def test_a_dumped_request_with_escaped_line_breaks_is_masked(self) -> None:
        masked = _masked(f"send: b'GET / HTTP/1.1\\r\\nHost: a.example\\r\\nCookie: {_SESSION}\\r\\n\\r\\n'")
        assert not any(leak in masked for leak in _LEAKS)
        assert "Host: a.example" in masked

    def test_a_header_after_a_large_body_is_masked(self) -> None:
        filler = "x" * 70_000
        masked = _masked(f"{filler}\nCookie: {_SESSION}\n{filler}")
        assert not any(leak in masked for leak in _LEAKS)
        assert masked.count("x") == 140_000


class TestQuotedCommandArguments:
    @pytest.mark.parametrize("quote", ['"', "'"])
    def test_the_closing_quote_and_the_rest_of_the_command_stay(self, quote: str) -> None:
        text = f"curl -H {quote}Cookie: {_SESSION}{quote} https://app.example/api -o out.json"
        assert _masked(text) == f"curl -H {quote}Cookie: ***{quote} https://app.example/api -o out.json"

    def test_a_value_that_holds_the_other_quote_is_masked_whole(self) -> None:
        masked = _masked(
            """curl -H 'Cookie: sid="Zk3fQ9xLm2Pq7Rt1"; csrftoken=Vb8nWc4Yd6Xe0Aj5' https://app.example/api"""
        )
        assert masked == "curl -H 'Cookie: ***' https://app.example/api"

    def test_an_unclosed_quote_is_masked_to_the_end_of_the_line(self) -> None:
        masked = _masked(f'curl -H "Cookie: {_SESSION}\nnext line')
        assert masked == 'curl -H "Cookie: ***\nnext line'


class TestInsideJsonRecords:
    """An event log writes a command and its output as JSON strings, where a line break is the two characters ``\\n``."""

    @staticmethod
    def _record(**data: str) -> str:
        return json.dumps({"seq": 1, "type": "bash_command_executed", "data": data}, ensure_ascii=False)

    def test_a_header_in_the_middle_of_output_leaves_a_valid_record(self) -> None:
        output = f"> GET /api HTTP/1.1\n> Cookie: {_SESSION}\n> Accept: */*\n< HTTP/1.1 200 OK"
        record = json.loads(_masked(self._record(stdout=output, stderr="")))
        assert record["data"]["stdout"] == "> GET /api HTTP/1.1\n> Cookie: ***\n> Accept: */*\n< HTTP/1.1 200 OK"

    def test_a_header_that_ends_the_output_leaves_a_valid_record(self) -> None:
        record = json.loads(_masked(self._record(stdout=f"< set-cookie: {_SESSION}; Path=/", stderr="")))
        assert record["data"] == {"stdout": "< set-cookie: ***", "stderr": ""}

    def test_a_header_that_opens_the_output_leaves_a_valid_record(self) -> None:
        masked = _masked(self._record(stdout=f"Cookie: {_SESSION}", stderr=""))
        assert json.loads(masked)["data"] == {"stdout": "Cookie: ***", "stderr": ""}

    def test_a_quoted_argument_with_escaped_quotes_leaves_a_valid_record(self) -> None:
        command = f'curl -H "Cookie: {_SESSION}" https://app.example/api'
        record = json.loads(_masked(self._record(command=command)))
        assert record["data"]["command"] == 'curl -H "Cookie: ***" https://app.example/api'


class TestWhatStaysReadable:
    @pytest.mark.parametrize(
        "text",
        [
            "Cookie policy: we use cookies",
            "Cookies: 3 stored",
            "X-Cookie: not-a-header",
            "NoCookie: value",
            "Cookie2: legacy",
            "the Cookie header is documented",
            "Cookie:",
            "Cookie:   ",
            "Set-Cookie:\n",
        ],
    )
    def test_text_that_is_not_a_cookie_header_line_is_unchanged(self, text: str) -> None:
        assert _masked(text) == text

    def test_a_source_file_comment_is_unchanged_in_source_mode(self) -> None:
        text = "# Cookie: the session id travels here\nTIMEOUT = 30"
        assert redact_sensitive_text(text, source_code=True) == text

    def test_masking_is_idempotent(self) -> None:
        once = _masked(f"> Cookie: {_SESSION}\n< Set-Cookie: {_SESSION}; Path=/")
        assert _masked(once) == once
