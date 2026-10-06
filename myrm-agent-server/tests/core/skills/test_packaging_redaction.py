"""Shared skill redaction: canary secrets never reach exported packages."""

from __future__ import annotations

import io
import zipfile

import pytest

from app.core.skills.models import Skill, SkillType
from app.core.skills.packaging import SKILL_CHANGED_SINCE_PREVIEW, SkillPackagingService
from app.core.skills.packaging.collect import collect_skill_files
from app.core.skills.packaging.redaction import redact_files, review_digest

CANARY_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
CANARY_PATH = "/Users/alice/projects/private/notes.txt"
SKILL_MD = f"---\nname: demo\ndescription: Demo skill\nversion: 1.0.0\n---\n# Demo\nUse token {CANARY_TOKEN}\n"
BINARY = b"\xff\xfe\x00\x01binary-payload"


class _FakeSkills:
    """Minimal SkillsService stub for the packaging facade."""

    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.skill = Skill(
            id="demo",
            type=SkillType.PREBUILT,
            name="demo",
            description="Demo skill",
            storage_path="skills/prebuilt/demo",
            version="1.0.0",
        )

    async def get_skill(self, skill_id: str) -> Skill | None:
        return self.skill if skill_id == "demo" else None

    async def list_skill_files(self, skill_id: str) -> list[str]:
        return list(self.files)

    async def get_skill_file(self, skill_id: str, file_path: str) -> bytes | None:
        return self.files.get(file_path)


def _service(monkeypatch: pytest.MonkeyPatch, files: dict[str, bytes]) -> tuple[SkillPackagingService, _FakeSkills]:
    monkeypatch.setattr("app.core.skills.packaging._load_evolution_record", lambda _name: None)
    fake = _FakeSkills(files)
    return SkillPackagingService(skills_svc=fake), fake  # type: ignore[arg-type]


def _zip_text(zip_content: bytes | None) -> str:
    assert zip_content is not None
    with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
        return "\n".join(zf.read(name).decode("utf-8", errors="replace") for name in zf.namelist())


def _files() -> dict[str, bytes]:
    return {
        "SKILL.md": SKILL_MD.encode(),
        "notes.txt": f"see {CANARY_PATH}\n".encode(),
        "blob.bin": BINARY,
        "receipt.json": b'{"installed_path": "/Users/alice/.myrm/skills/demo"}',
        "origin.json": b'{"source": "clawhub"}',
    }


class TestRedactFiles:
    def test_apply_removes_secrets_and_never_touches_binary(self) -> None:
        outcome = redact_files(
            {"SKILL.md": SKILL_MD.encode(), "notes.txt": f"see {CANARY_PATH}\n".encode(), "blob.bin": BINARY},
            apply=True,
        )
        assert CANARY_TOKEN not in outcome.files["SKILL.md"].decode()
        assert CANARY_PATH not in outcome.files["notes.txt"].decode()
        assert outcome.files["blob.bin"] == BINARY
        assert set(outcome.redactions) == {"SKILL.md", "notes.txt"}
        assert not outcome.is_safe

    def test_preview_mode_reports_without_rewriting(self) -> None:
        files = {"SKILL.md": SKILL_MD.encode()}
        outcome = redact_files(files, apply=False)
        assert outcome.files == files
        assert "SKILL.md" in outcome.redactions

    def test_ignored_finding_is_kept_and_not_reported(self) -> None:
        outcome = redact_files({"SKILL.md": SKILL_MD.encode()}, apply=True, ignored={"SKILL.md": [0]})
        assert CANARY_TOKEN in outcome.files["SKILL.md"].decode()
        assert outcome.is_safe

    def test_clean_tree_is_safe(self) -> None:
        assert redact_files({"SKILL.md": b"# nothing sensitive\n"}, apply=True).is_safe


class TestReviewDigest:
    def test_stable_for_identical_trees_and_sensitive_to_any_change(self) -> None:
        base = {"a.txt": b"one", "b.txt": b"two"}
        assert review_digest(base) == review_digest(dict(reversed(list(base.items()))))
        assert review_digest(base) != review_digest({**base, "b.txt": b"twp"})
        assert review_digest(base) != review_digest({"a.txt": b"one", "c.txt": b"two"})


class TestCollect:
    async def test_bookkeeping_files_are_excluded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _, fake = _service(monkeypatch, _files())
        collected = await collect_skill_files(fake, "demo")
        assert set(collected) == {"SKILL.md", "notes.txt", "blob.bin"}


class TestPackageSkillDigestGuard:
    async def test_preview_exposes_findings_and_digest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        service, _ = _service(monkeypatch, _files())
        preview = await service.package_skill("demo", preview_only=True)
        assert preview.success and not preview.is_safe
        assert preview.review_digest
        assert preview.redactions is not None and "SKILL.md" in preview.redactions

    async def test_ignore_decisions_without_matching_digest_are_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        service, _ = _service(monkeypatch, _files())
        result = await service.package_skill("demo", apply_redactions=True, ignored_redactions={"SKILL.md": [0]})
        assert not result.success
        assert result.error_code == SKILL_CHANGED_SINCE_PREVIEW

    async def test_redact_everything_is_a_one_way_tightening_and_needs_no_digest(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        service, _ = _service(monkeypatch, _files())
        result = await service.package_skill("demo", apply_redactions=True, export_format="raw_skill")
        assert result.success, result.error
        assert CANARY_TOKEN not in _zip_text(result.zip_content)

    async def test_matching_digest_exports_redacted_package(self, monkeypatch: pytest.MonkeyPatch) -> None:
        service, _ = _service(monkeypatch, _files())
        preview = await service.package_skill("demo", preview_only=True)
        result = await service.package_skill(
            "demo",
            apply_redactions=True,
            export_format="raw_skill",
            review_digest=preview.review_digest,
        )
        assert result.success, result.error
        text = _zip_text(result.zip_content)
        assert CANARY_TOKEN not in text
        assert CANARY_PATH not in text
        assert "installed_path" not in text

    async def test_skill_edited_after_preview_is_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        service, fake = _service(monkeypatch, _files())
        preview = await service.package_skill("demo", preview_only=True)
        fake.files["notes.txt"] = b"a different file now\n"
        result = await service.package_skill(
            "demo",
            ignored_redactions={"SKILL.md": [0]},
            review_digest=preview.review_digest,
        )
        assert not result.success
        assert result.error_code == SKILL_CHANGED_SINCE_PREVIEW

    async def test_plain_export_needs_no_digest(self, monkeypatch: pytest.MonkeyPatch) -> None:
        service, _ = _service(monkeypatch, _files())
        result = await service.package_skill("demo", export_format="raw_skill")
        assert result.success, result.error
