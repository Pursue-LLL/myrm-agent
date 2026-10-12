"""
[POS] tests/unit/test_assignment_sweep_service.py
[INPUT] app.schemas.assignment_sweep, app.services.security.assignment_sweep_service
[OUTPUT] Unit tests for AssignmentSweepService
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest

from app.schemas.assignment_sweep import (
    AuditDatabaseUrlRequestDTO,
    CheckCleanContentRequestDTO,
    SweepTextRequestDTO,
)
from app.services.security.assignment_sweep_service import (
    AssignmentSweepService,
)


@pytest.fixture
def service() -> AssignmentSweepService:
    return AssignmentSweepService()


def test_sweep_text_quoted_json(service: AssignmentSweepService) -> None:
    req = SweepTextRequestDTO(
        content='{\n  "api_key": "sk-live-super-secret-key-112233",\n  "name": "service"\n}'
    )
    report = service.sweep_text(req)

    assert report.verdict == "suspected_leak"
    assert report.active_leaks_count == 1
    assert len(report.findings) == 1
    assert report.findings[0].key_name == "api_key"
    assert report.findings[0].key_family == "api_key"
    assert report.findings[0].is_exempt is False


def test_sweep_text_env_bracket_and_separator_prefixes(
    service: AssignmentSweepService,
) -> None:
    req = SweepTextRequestDTO(
        content=(
            'os.environ["CLIENT_SECRET"] = "secret-client-token-998877"\n'
            'MY_API_KEY = "custom-key-val-554433"\n'
        )
    )
    report = service.sweep_text(req)

    assert report.verdict == "suspected_leak"
    assert report.active_leaks_count == 2
    keys = {f.key_name for f in report.findings}
    assert "CLIENT_SECRET" in keys
    assert "MY_API_KEY" in keys


def test_sweep_text_benign_alphanumeric_words(service: AssignmentSweepService) -> None:
    benign_text = (
        "tokenizer = AutoTokenizer.from_pretrained('gpt2')\n"
        "token_count = 120\n"
        "secretive = False\n"
        "credentials_file = '/path/to/innocent/file'\n"
    )
    req = SweepTextRequestDTO(content=benign_text)
    report = service.sweep_text(req)

    assert report.verdict == "clean"
    assert report.active_leaks_count == 0
    assert len(report.findings) == 0


def test_audit_database_url_loopback_vs_remote(service: AssignmentSweepService) -> None:
    # 1. Localhost with default postgres -> Exempted
    req_local = AuditDatabaseUrlRequestDTO(
        raw_url="postgresql://postgres:postgres@localhost:5432/dev_db"
    )
    res_local = service.audit_database_url(req_local)
    assert res_local is not None
    assert res_local.is_loopback is True
    assert res_local.is_exempt is True
    assert "Exempted local development DSN" in res_local.audit_reason

    # 2. Remote host -> Flagged non-exempt
    req_remote = AuditDatabaseUrlRequestDTO(
        raw_url="postgresql://postgres:postgres@db.prod.internal:5432/main"
    )
    res_remote = service.audit_database_url(req_remote)
    assert res_remote is not None
    assert res_remote.is_loopback is False
    assert res_remote.is_exempt is False


def test_check_clean_content(service: AssignmentSweepService) -> None:
    # Clean check
    clean_res = service.check_clean_content(
        CheckCleanContentRequestDTO(content="const port = 8080;\nconst name = 'app';")
    )
    assert clean_res.is_clean is True
    assert clean_res.active_leaks_count == 0

    # Dirty check
    dirty_res = service.check_clean_content(
        CheckCleanContentRequestDTO(content='API_KEY="sk-live-001122334455"')
    )
    assert dirty_res.is_clean is False
    assert dirty_res.active_leaks_count >= 1
