import sys
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace

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


class _FakeSkillStore:
    def __init__(self, db_dir: Path, *, existing_skills: list[SimpleNamespace] | None = None) -> None:
        self.db_path = db_dir / "skills.db"
        self._existing_skills = existing_skills or []
        self.saved_batches: list[list[object]] = []

    def list_skills(self) -> list[SimpleNamespace]:
        return self._existing_skills

    async def save_skills_batch(self, records: list[object]) -> None:
        self.saved_batches.append(records)


class _FakeSkillStoreNoBatch:
    def __init__(self, db_dir: Path) -> None:
        self.db_path = db_dir / "skills.db"
        self._existing_skills: list[SimpleNamespace] = []
        self.saved_records: list[object] = []

    def list_skills(self) -> list[SimpleNamespace]:
        return self._existing_skills

    async def save_skill(self, record: object) -> None:
        self.saved_records.append(record)


def _make_imported_skill(name: str = "skill-one", description: str = "demo") -> SimpleNamespace:
    content = "print('ok')"
    skill_md = f"---\nname: {name}\ndescription: {description}\n---\n{content}\n"
    return SimpleNamespace(
        name=name,
        description=description,
        content=content,
        metadata={"name": name, "description": description},
        files={"SKILL.md": skill_md.encode("utf-8")},
    )


def _install_fake_app_optimization_modules(monkeypatch, *, passed: bool, issues: list[str] | None = None) -> None:
    issues_list = issues or []

    config_module = ModuleType("app.api.skills.optimization.config")
    security_module = ModuleType("app.api.skills.optimization.security")

    class SecurityConfig:  # noqa: D401
        """Test double for SecurityConfig."""

    class SkillSecurityValidator:
        def __init__(self, config: SecurityConfig) -> None:
            self._config = config

        def validate_skill(self, _content: str) -> SimpleNamespace:
            return SimpleNamespace(passed=passed, issues=issues_list)

    config_module.SecurityConfig = SecurityConfig
    security_module.SkillSecurityValidator = SkillSecurityValidator

    monkeypatch.setitem(sys.modules, "app.api.skills.optimization", ModuleType("app.api.skills.optimization"))
    monkeypatch.setitem(sys.modules, "app.api.skills.optimization.config", config_module)
    monkeypatch.setitem(sys.modules, "app.api.skills.optimization.security", security_module)


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


def test_preview_batch_import_rejects_non_zip_file() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    response = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.txt", b"not-zip", "text/plain")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "必须上传 .zip 文件"


def test_preview_batch_import_rejects_empty_file() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    response = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", b"", "application/zip")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "文件为空"


def test_preview_batch_import_rejects_oversized_file() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    response = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", b"x" * (10 * 1024 * 1024 + 1), "application/zip")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "上传被系统安全拦截：文件大小不能超过 10MB，保护内存免遭拒绝服务攻击。"


def test_preview_batch_import_generic_parse_error_uses_structured_detail(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    monkeypatch.setattr(
        "app.api.skills.batch_import.HermesBatchParser.parse_zip",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("bad zip payload")),
    )

    response = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", b"broken-zip", "application/zip")},
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail == {
        "message": "解析压缩包失败，防爆防护触发或格式错误: bad zip payload",
        "error_code": "",
    }


def test_preview_batch_import_returns_empty_response_when_no_skills(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    monkeypatch.setattr(
        "app.api.skills.batch_import.HermesBatchParser.parse_zip",
        lambda *args, **kwargs: [],
    )

    response = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", b"valid-zip", "application/zip")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "session_id": "",
        "items": [],
        "total_found": 0,
        "total_conflicts": 0,
    }


def test_preview_batch_import_uses_server_optimization_modules_when_available(
    monkeypatch, tmp_path: Path
) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    _install_fake_app_optimization_modules(monkeypatch, passed=True, issues=[])
    fake_store = _FakeSkillStore(tmp_path)
    monkeypatch.setattr("app.api.skills.batch_import._get_skill_store", lambda: fake_store)
    monkeypatch.setattr(
        "app.api.skills.batch_import.HermesBatchParser.parse_zip",
        lambda *args, **kwargs: [_make_imported_skill()],
    )

    response = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", b"valid-zip", "application/zip")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_found"] == 1
    assert payload["items"][0]["security_issues"] is None


def test_preview_batch_import_success_persists_session_and_marks_conflict(monkeypatch, tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    fake_store = _FakeSkillStore(
        tmp_path,
        existing_skills=[SimpleNamespace(name="skill-one", skill_id="existing-1")],
    )
    monkeypatch.setattr("app.api.skills.batch_import._get_skill_store", lambda: fake_store)
    monkeypatch.setattr(
        "app.api.skills.batch_import.HermesBatchParser.parse_zip",
        lambda *args, **kwargs: [_make_imported_skill()],
    )
    monkeypatch.setattr(
        "myrm_agent_harness.agent.skills.optimization.security.SkillSecurityValidator.validate_skill",
        lambda *args, **kwargs: SimpleNamespace(passed=False, issues=["blocked"]),
    )

    response = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", b"valid-zip", "application/zip")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_found"] == 1
    assert payload["total_conflicts"] == 1
    assert payload["session_id"]
    assert payload["items"][0]["conflict_type"] == "conflict"
    assert payload["items"][0]["existing_skill_id"] == "existing-1"
    assert payload["items"][0]["security_issues"] == "blocked"


def test_confirm_batch_import_blank_load_session_error_uses_default_message(monkeypatch, tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    class BlankMessageError(Exception):
        def __str__(self) -> str:
            return "   "

    def _raise_blank_message(*args, **kwargs):
        raise BlankMessageError()

    monkeypatch.setattr(
        "app.api.skills.batch_import._get_skill_store",
        lambda: SimpleNamespace(db_path=tmp_path / "skills.db"),
    )
    monkeypatch.setattr("app.api.skills._staging.SkillStagingManager.load_session", _raise_blank_message)

    response = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": "session-blank",
            "items": [
                {
                    "virtual_id": "import_0",
                    "name": "skill-one",
                    "description": "demo",
                    "resolution": "new",
                    "existing_skill_id": None,
                }
            ],
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail == {
        "message": "导入会话无效或已过期。",
        "error_code": "",
    }


def test_confirm_batch_import_success_returns_counts_and_saves_batch(monkeypatch, tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    fake_store = _FakeSkillStore(tmp_path)
    monkeypatch.setattr("app.api.skills.batch_import._get_skill_store", lambda: fake_store)
    monkeypatch.setattr(
        "app.api.skills.batch_import.HermesBatchParser.parse_zip",
        lambda *args, **kwargs: [_make_imported_skill()],
    )
    monkeypatch.setattr(
        "myrm_agent_harness.agent.skills.optimization.security.SkillSecurityValidator.validate_skill",
        lambda *args, **kwargs: SimpleNamespace(passed=True, issues=[]),
    )

    preview_response = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", b"valid-zip", "application/zip")},
    )
    preview_payload = preview_response.json()

    response = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": preview_payload["session_id"],
            "items": [
                {
                    "virtual_id": preview_payload["items"][0]["virtual_id"],
                    "name": "skill-one",
                    "description": "demo",
                    "resolution": "new",
                    "existing_skill_id": None,
                },
                {
                    "virtual_id": "import_99",
                    "name": "skip-skill",
                    "description": "skip",
                    "resolution": "skip",
                    "existing_skill_id": None,
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "imported_count": 1,
        "skipped_count": 1,
    }
    assert len(fake_store.saved_batches) == 1
    assert len(fake_store.saved_batches[0]) == 1


def test_confirm_batch_import_success_falls_back_to_save_skill(monkeypatch, tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    fake_store = _FakeSkillStoreNoBatch(tmp_path)
    monkeypatch.setattr("app.api.skills.batch_import._get_skill_store", lambda: fake_store)
    monkeypatch.setattr(
        "app.api.skills.batch_import.HermesBatchParser.parse_zip",
        lambda *args, **kwargs: [_make_imported_skill()],
    )
    monkeypatch.setattr(
        "myrm_agent_harness.agent.skills.optimization.security.SkillSecurityValidator.validate_skill",
        lambda *args, **kwargs: SimpleNamespace(passed=True, issues=[]),
    )

    preview_response = client.post(
        "/api/v1/skills/batch-import/preview",
        files={"file": ("skills.zip", b"valid-zip", "application/zip")},
    )
    preview_payload = preview_response.json()

    response = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": preview_payload["session_id"],
            "items": [
                {
                    "virtual_id": preview_payload["items"][0]["virtual_id"],
                    "name": "skill-one",
                    "description": "demo",
                    "resolution": "new",
                    "existing_skill_id": None,
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "imported_count": 1,
        "skipped_count": 0,
    }
    assert len(fake_store.saved_records) == 1


def test_confirm_batch_import_replace_and_rename_use_server_validator(monkeypatch, tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    _install_fake_app_optimization_modules(monkeypatch, passed=True, issues=[])
    fake_store = _FakeSkillStore(tmp_path)
    monkeypatch.setattr("app.api.skills.batch_import._get_skill_store", lambda: fake_store)

    from app.api.skills._staging import SkillStagingManager

    staged_skills = [
        _make_imported_skill(name="replace-skill", description="replace"),
        _make_imported_skill(name="rename-skill", description="rename"),
    ]
    staging_manager = SkillStagingManager(fake_store.db_path.parent)
    staging_manager.save_session("session-replace-rename", staged_skills)

    skills_root = fake_store.db_path.parent / "skills"
    existing_dir = skills_root / "skill-replace-id"
    existing_dir.mkdir(parents=True, exist_ok=True)
    (existing_dir / "SKILL.md").write_text("---\nname: old\n---\nold", encoding="utf-8")

    response = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": "session-replace-rename",
            "items": [
                {
                    "virtual_id": "import_0",
                    "name": "replace-skill",
                    "description": "replace",
                    "resolution": "replace",
                    "existing_skill_id": "skill-replace-id",
                },
                {
                    "virtual_id": "import_1",
                    "name": "rename-skill",
                    "description": "rename",
                    "resolution": "rename_cow",
                    "existing_skill_id": "skill-parent-id",
                },
            ],
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "imported_count": 2,
        "skipped_count": 0,
    }
    assert len(fake_store.saved_batches) == 1
    saved_names = {record.name for record in fake_store.saved_batches[0]}
    assert saved_names == {"replace-skill", "rename-skill_copy"}


def test_confirm_batch_import_archive_violation_uses_structured_detail(monkeypatch, tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    violation = ArchiveSecurityViolation(
        code=ArchiveSecurityCode.EXECUTABLE_BINARY_DETECTED,
        source="safe_extract_zip",
    )

    def _raise_archive_security(*args, **kwargs):
        raise ArchiveSecurityError(violation, "ZIP contains executable binary member: payload.bin")

    monkeypatch.setattr(
        "app.api.skills.batch_import._get_skill_store",
        lambda: SimpleNamespace(db_path=tmp_path / "skills.db"),
    )
    monkeypatch.setattr("app.api.skills._staging.SkillStagingManager.load_session", _raise_archive_security)

    response = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": "session-1",
            "items": [
                {
                    "virtual_id": "import_0",
                    "name": "skill-one",
                    "description": "demo",
                    "resolution": "new",
                    "existing_skill_id": None,
                }
            ],
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail == {
        "message": "上传被系统安全拦截：ZIP 包含可执行二进制文件。",
        "error_code": ArchiveSecurityCode.EXECUTABLE_BINARY_DETECTED.value,
    }


def test_confirm_batch_import_generic_load_session_error_uses_structured_detail(monkeypatch, tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    def _raise_generic_error(*args, **kwargs):
        raise RuntimeError("session expired")

    monkeypatch.setattr(
        "app.api.skills.batch_import._get_skill_store",
        lambda: SimpleNamespace(db_path=tmp_path / "skills.db"),
    )
    monkeypatch.setattr("app.api.skills._staging.SkillStagingManager.load_session", _raise_generic_error)

    response = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": "session-1",
            "items": [
                {
                    "virtual_id": "import_0",
                    "name": "skill-one",
                    "description": "demo",
                    "resolution": "new",
                    "existing_skill_id": None,
                }
            ],
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail == {
        "message": "session expired",
        "error_code": "",
    }


def test_confirm_batch_import_invalid_virtual_id_uses_structured_detail(monkeypatch, tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    monkeypatch.setattr(
        "app.api.skills.batch_import._get_skill_store",
        lambda: SimpleNamespace(db_path=tmp_path / "skills.db"),
    )
    monkeypatch.setattr("app.api.skills._staging.SkillStagingManager.load_session", lambda *args, **kwargs: [])

    response = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": "session-1",
            "items": [
                {
                    "virtual_id": "invalid-id",
                    "name": "skill-one",
                    "description": "demo",
                    "resolution": "new",
                    "existing_skill_id": None,
                }
            ],
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail == {
        "message": "非法的 virtual_id",
        "error_code": "",
    }


def test_confirm_batch_import_security_scan_failure_uses_structured_detail(monkeypatch, tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1/skills")
    client = TestClient(app)

    monkeypatch.setattr(
        "app.api.skills.batch_import._get_skill_store",
        lambda: SimpleNamespace(db_path=tmp_path / "skills.db"),
    )
    monkeypatch.setattr(
        "app.api.skills._staging.SkillStagingManager.load_session",
        lambda *args, **kwargs: [SimpleNamespace(content="print('blocked')")],
    )
    monkeypatch.setattr(
        "myrm_agent_harness.agent.skills.optimization.security.SkillSecurityValidator.validate_skill",
        lambda *args, **kwargs: SimpleNamespace(passed=False, issues=["blocked"]),
    )

    response = client.post(
        "/api/v1/skills/batch-import/confirm",
        json={
            "session_id": "session-1",
            "items": [
                {
                    "virtual_id": "import_0",
                    "name": "skill-one",
                    "description": "demo",
                    "resolution": "new",
                    "existing_skill_id": None,
                }
            ],
        },
    )

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail == {
        "message": "安全拦截: skill-one 包含恶意代码 -> ['blocked']。本次导入已撤销。",
        "error_code": "",
    }
