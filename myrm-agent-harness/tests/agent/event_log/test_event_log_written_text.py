"""Text an event carries reaches the event file with no credential in it.

Two shapes are not a field named after a credential: the result of ``cat .env`` or an HTTP dump holds assignments and
header lines whose values have no token shape, and a security decision the logger writes itself carries the URL it
blocked. Both end up in the file the control plane pulls, so every one of them goes through the same redaction.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from myrm_agent_harness.agent.event_log._sanitize import sanitize_event_data
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.agent.event_log.logger import EventLogger
from myrm_agent_harness.core.security.audit import record_decision, reset_audit_log

_ENV_PASSWORDS = ("Pr0dDbPassw0rd!", "redispass123456", "smtpPassw0rd99", "admin-Passw0rd")
_ENV_DUMP = (
    "APP_ENV=production\n"
    f"DB_PASSWORD={_ENV_PASSWORDS[0]}\n"
    f"REDIS_PASSWORD={_ENV_PASSWORDS[1]}\n"
    f"SMTP_PASS={_ENV_PASSWORDS[2]}\n"
    f"ADMIN_PASSWORD={_ENV_PASSWORDS[3]}\n"
)
_SESSION_ID = "abc123def456ghi789"
_HIGH_ENTROPY = "q8Xw3LmN7pRt2VbY5cHj9KdF4sGa6ZeU"
_URL_PASSWORD = "S3cretPassw0rd"
_URL_API_KEY = "sk-live-abcdefghijklmnop12345678"


def test_an_assignment_in_a_result_is_masked_and_the_plain_lines_stay() -> None:
    written = str(sanitize_event_data({"result": _ENV_DUMP}))

    for password in _ENV_PASSWORDS:
        assert password not in written
    assert "APP_ENV=production" in written


def test_a_cookie_header_line_in_a_result_is_masked() -> None:
    written = str(sanitize_event_data({"result": f"> Cookie: sessionid={_SESSION_ID}; theme=dark"}))

    assert _SESSION_ID not in written


def test_a_high_entropy_string_is_still_masked_next_to_the_assignments() -> None:
    written = str(sanitize_event_data({"result": f'{_ENV_DUMP}\nsession "{_HIGH_ENTROPY}"'}))

    assert _HIGH_ENTROPY not in written


@pytest.mark.asyncio
async def test_the_security_audit_the_logger_writes_holds_no_credential_of_the_url_it_blocked(tmp_path: Path) -> None:
    backend = FileEventLogBackend(tmp_path, "sess-1")
    event_logger = EventLogger(backend, "sess-1")
    await event_logger.start()
    blocked = f"http://deploy:{_URL_PASSWORD}@10.0.0.5/hook?api_key={_URL_API_KEY}&x=1"
    reset_audit_log()
    record_decision("ssrf", "SSRF_BLOCKED", f"{blocked}: private address")
    await event_logger.close()

    written = (tmp_path / "sess-1.jsonl").read_text(encoding="utf-8")
    audit = next(json.loads(line) for line in written.splitlines() if '"security_audit"' in line)
    assert _URL_PASSWORD not in written
    assert _URL_API_KEY not in written
    assert audit["data"]["decisions"][0]["decision"] == "SSRF_BLOCKED"
    assert audit["data"]["decisions"][0]["reason"].endswith("private address")
