"""Marketplace export: bundled skill files are redacted and never lossily decoded."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.agent.marketplace import export as export_module

CANARY_TOKEN = "ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
CANARY_PATH = "/Users/alice/projects/private/notes.txt"


class _FakeSkills:
    def __init__(self, skills: list[SimpleNamespace], files: dict[str, dict[str, bytes]]) -> None:
        self._skills = skills
        self._files = files

    async def get_skills_by_ids(self, skill_ids: list[str]) -> list[SimpleNamespace]:
        return [skill for skill in self._skills if skill.id in skill_ids]

    async def list_skill_files(self, skill_id: str) -> list[str]:
        return list(self._files[skill_id])

    async def get_skill_file(self, skill_id: str, file_path: str) -> bytes | None:
        return self._files[skill_id].get(file_path)


def _skill(skill_id: str, kind: str = "local") -> SimpleNamespace:
    return SimpleNamespace(id=skill_id, name=skill_id, description="d", type=SimpleNamespace(value=kind))


@pytest.fixture
def profile() -> SimpleNamespace:
    return SimpleNamespace(skills=["custom", "builtin", "no-md"])


async def test_bundle_redacts_text_skips_binary_and_bookkeeping(
    monkeypatch: pytest.MonkeyPatch, profile: SimpleNamespace
) -> None:
    fake = _FakeSkills(
        [_skill("custom"), _skill("builtin", "prebuilt"), _skill("no-md")],
        {
            "custom": {
                "SKILL.md": f"---\nname: custom\n---\nUse {CANARY_TOKEN}\n".encode(),
                "notes.txt": f"see {CANARY_PATH}\n".encode(),
                "logo.png": b"\x89PNG\r\n\xff\xfe\x00binary",
                "receipt.json": b'{"installed_path": "/Users/alice/x"}',
            },
            "builtin": {"SKILL.md": b"prebuilt skills are never bundled"},
            "no-md": {"notes.txt": b"orphan resource"},
        },
    )
    monkeypatch.setattr(export_module, "skills_service", fake)

    bundled = await export_module._bundle_custom_skills(profile)

    assert [entry["name"] for entry in bundled] == ["custom"]
    entry = bundled[0]
    assert CANARY_TOKEN not in entry["content"]
    assert set(entry["resources"]) == {"notes.txt"}
    assert CANARY_PATH not in entry["resources"]["notes.txt"]
    assert "installed_path" not in str(entry)
