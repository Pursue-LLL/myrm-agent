"""MCP call markers versus the output scrubber.

A PTC script reports each tool call as ``__MCP_DATA__{nonce}{base64(json)}__END__{nonce}``
on stdout. The base64 of any ``{"...`` JSON starts with ``eyJ``, which the credential
scrubber reads as a JWT and truncates, so every marker was destroyed before the host
could read it. ``ExecutionResult`` therefore lets marker-shaped spans through verbatim
and still scrubs everything around them.
"""

from __future__ import annotations

import base64
import json

from myrm_agent_harness.toolkits.code_execution.executors.common.mcp_markers import (
    scrub_marker_spans,
    scrub_outside_markers,
)
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionResult, scrub_sensitive_info
from tests.support.fake_secrets import jwt_shaped

NONCE = "0123456789abcdef0123456789abcdef"
SECRET = "sk-proj-" + "a1B2c3D4" * 4


def _marker(nonce: str = NONCE, result: str = "ok") -> str:
    payload = base64.b64encode(json.dumps({"s": "mcp_x_skill", "t": "tool", "r": result}).encode()).decode()
    return f"__MCP_DATA__{nonce}{payload}__END__{nonce}"


class TestExecutionResultStdout:
    def test_the_scrubber_used_to_destroy_the_marker(self) -> None:
        """The defect, stated against the plain scrubber: the payload comes back truncated."""
        marker = _marker()

        assert scrub_sensitive_info(marker) != marker

    def test_marker_reaches_the_host_verbatim(self) -> None:
        marker = _marker()

        result = ExecutionResult(success=True, stdout=f"before\n{marker}\nafter\n")

        assert marker in result.stdout

    def test_text_around_a_marker_is_still_scrubbed(self) -> None:
        marker = _marker()

        result = ExecutionResult(success=True, stdout=f"key {SECRET}\n{marker}\nat /Users/someone/project\n")

        assert marker in result.stdout
        assert SECRET not in result.stdout
        assert "/Users/someone" not in result.stdout

    def test_a_real_jwt_outside_a_marker_is_still_masked(self) -> None:
        jwt = jwt_shaped(
            "hbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",
            "zdWIiOiIxMjM0NTY3ODkwIn0",
            "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        )

        result = ExecutionResult(success=True, stdout=f"{_marker()}\nAuthorization: {jwt}\n")

        assert jwt not in result.stdout

    def test_output_without_a_marker_goes_through_the_plain_scrubber(self) -> None:
        text = f"key {SECRET}\nat /Users/someone/project\n"

        assert ExecutionResult(success=True, stdout=text).stdout == scrub_sensitive_info(text)

    def test_stderr_is_always_scrubbed_even_when_it_carries_a_marker_shape(self) -> None:
        marker = _marker()

        result = ExecutionResult(success=True, stderr=marker)

        assert marker not in result.stderr


class TestMarkerShape:
    def test_a_foreign_shaped_nonce_is_not_exempt(self) -> None:
        """Only the nonce the IPC server mints (32 lowercase hex) is exempt from the first scrub."""
        for nonce in ("attacker-nonce", NONCE.upper(), NONCE[:-1]):
            marker = _marker(nonce)

            assert marker not in ExecutionResult(success=True, stdout=marker).stdout, nonce

    def test_the_nonce_on_both_ends_must_have_the_shape(self) -> None:
        marker = _marker().replace(f"__END__{NONCE}", "__END__nope")

        assert marker not in ExecutionResult(success=True, stdout=marker).stdout

    def test_a_well_shaped_span_of_any_content_passes_through_so_the_host_must_scrub_rejects(self) -> None:
        """The exemption cannot know the nonce, so it cannot tell a forged span from a real one."""
        other = "f" * 32
        forged = f"__MCP_DATA__{other}+AKIAIOSFODNN7EXAMPLE+__END__{other}"

        assert forged in ExecutionResult(success=True, stdout=forged).stdout
        assert "AKIAIOSFODNN7EXAMPLE" not in scrub_sensitive_info(forged)

    def test_payload_is_limited_to_the_base64_alphabet(self) -> None:
        marker = f"__MCP_DATA__{NONCE}eyJ hello world {SECRET}__END__{NONCE}"

        result = ExecutionResult(success=True, stdout=marker)

        assert SECRET not in result.stdout


class TestHelpers:
    def test_outside_helper_leaves_spans_alone_and_scrubs_the_rest(self) -> None:
        marker = _marker()

        out = scrub_outside_markers(f"a{marker}b{marker}c", str.upper)

        assert out == f"A{marker}B{marker}C"

    def test_spans_helper_scrubs_only_the_spans(self) -> None:
        marker = _marker()

        out = scrub_marker_spans(f"keep {marker} keep", str.upper)

        assert out == f"keep {marker.upper()} keep"

    def test_helpers_are_identity_or_plain_scrub_without_a_marker(self) -> None:
        assert scrub_marker_spans("plain text", str.upper) == "plain text"
        assert scrub_outside_markers("plain text", str.upper) == "PLAIN TEXT"
