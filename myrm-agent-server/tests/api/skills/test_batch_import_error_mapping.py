from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.backends.skills.scanning.archive_security import (
    ArchiveSecurityCode,
    ArchiveSecurityError,
    ArchiveSecurityViolation,
)

from app.api.skills.batch_import import (
    _build_batch_import_error_detail,
    _resolve_batch_import_error_message,
    router,
)


def test_resolve_batch_import_error_message_for_archive_security_error() -> None:
    violation = ArchiveSecurityViolation(
        code=ArchiveSecurityCode.ENTRY_LIMIT_EXCEEDED,
        source="safe_extract_zip",
        actual=5001,
        limit=4096,
    )
    error = ArchiveSecurityError(violation, "ZIP contains too many entries (5001 > 4096)")

    message = _resolve_batch_import_error_message(error)

    assert message == "上传被系统安全拦截：ZIP 文件条目数过多。"


def test_resolve_batch_import_error_message_for_generic_error() -> None:
    message = _resolve_batch_import_error_message(RuntimeError("bad zip"))

    assert message.startswith("解析压缩包失败，防爆防护触发或格式错误:")
    assert "bad zip" in message


def test_build_batch_import_error_detail_with_code() -> None:
    violation = ArchiveSecurityViolation(
        code=ArchiveSecurityCode.EXECUTABLE_BINARY_DETECTED,
        source="safe_extract_zip",
    )

    payload = _build_batch_import_error_detail("blocked", violation)

    assert payload == {
        "message": "blocked",
        "error_code": ArchiveSecurityCode.EXECUTABLE_BINARY_DETECTED.value,
    }


def test_build_batch_import_error_detail_without_code() -> None:
    payload = _build_batch_import_error_detail("generic failure")

    assert payload == {"message": "generic failure", "error_code": ""}


def test_preview_batch_import_archive_violation_uses_structured_detail(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    violation = ArchiveSecurityViolation(
        code=ArchiveSecurityCode.EXECUTABLE_BINARY_DETECTED,
        source="safe_extract_zip",
    )

    def _raise_archive_security(*args, **kwargs):
        raise ArchiveSecurityError(violation, "ZIP contains executable binary member: payload.bin")

    monkeypatch.setattr("app.api.skills.batch_import.HermesBatchParser.parse_zip", _raise_archive_security)

    response = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", b"not-a-real-zip", "application/zip")},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail == {
        "message": "上传被系统安全拦截：ZIP 包含可执行二进制文件。",
        "error_code": ArchiveSecurityCode.EXECUTABLE_BINARY_DETECTED.value,
    }
