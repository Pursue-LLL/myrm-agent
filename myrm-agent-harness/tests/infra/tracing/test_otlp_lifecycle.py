"""A failing provider flush or shutdown is reported without echoing the credentials in its text."""

from __future__ import annotations

import logging

import pytest

from myrm_agent_harness.infra.tracing.otlp.lifecycle import run_bounded

_URL_PASSWORD = "p4ssw0rd-in-the-url"
_LIFECYCLE_LOGGER = "myrm_agent_harness.infra.tracing.otlp.lifecycle"


def _fails_quoting_the_endpoint() -> None:
    raise ConnectionError(f"cannot reach https://exporter:{_URL_PASSWORD}@collector.example.com:4318/v1/traces")


def test_a_failing_action_reports_false_instead_of_raising() -> None:
    assert (
        run_bounded(_fails_quoting_the_endpoint, thread_name="lifecycle-test", timeout_ms=500.0, label="probe") is False
    )


def test_the_failure_log_masks_the_credentials_in_the_exception_text(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR, logger=_LIFECYCLE_LOGGER):
        run_bounded(_fails_quoting_the_endpoint, thread_name="lifecycle-test", timeout_ms=500.0, label="probe")

    assert "Error during probe" in caplog.text
    assert "collector.example.com" in caplog.text
    assert _URL_PASSWORD not in caplog.text
