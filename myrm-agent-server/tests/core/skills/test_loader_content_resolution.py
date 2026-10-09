"""The assembled skill backend must serve the SKILL.md of every skill it lists.

`create_skill_backend` composes three sources under route prefixes that skill names never carry:
enabled prebuilt skills, the skills bound to the agent (prebuilt picks and LOCAL folders) and the
workspace skill directories. Everything downstream (`skill_select_tool`, the explicit `[use ...]`
preload, skill hooks) asks that backend for content by the name or `storage_skill_id` found on the
listed metadata, so each listed skill has to resolve through the whole stack.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from myrm_agent_harness.agent.meta_tools.skills.select.skill_document_loader import get_skill_document
from myrm_agent_harness.backends.skills.protocols import SkillBackend
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.skills import prebuilt_sync
from app.core.skills.loader import create_skill_backend
from app.core.skills.providers.local import LocalSkillsProvider
from app.core.skills.store.service import SkillsService

_LOCAL_SKILL_MD = "---\nname: probe-local\ndescription: A local probe skill\n---\n# probe-local\n\nLocal SOP body.\n"
_WORKSPACE_SKILL_MD = "---\nname: ws-probe\ndescription: A workspace probe skill\n---\n# ws-probe\n\nWorkspace SOP body.\n"


@pytest.fixture(autouse=True)
def _fresh_prebuilt_sync() -> Iterator[None]:
    prebuilt_sync._synced = False  # noqa: SLF001
    yield
    prebuilt_sync._synced = False  # noqa: SLF001


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(str(tmp_path / "storage"))


@pytest_asyncio.fixture
async def service(storage: LocalStorageBackend) -> AsyncIterator[SkillsService]:
    svc = SkillsService(storage=storage)
    sync_result = await prebuilt_sync.sync_prebuilt_seeds(storage)
    await svc.user_config.ensure_prebuilt_enabled_after_sync(list(sync_result.skill_ids))
    yield svc


def _write_skill(root: Path, dirname: str, skill_md: str, extra: dict[str, str] | None = None) -> Path:
    skill_dir = root / dirname
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(skill_md, encoding="utf-8")
    for relative, body in (extra or {}).items():
        target = skill_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    return skill_dir


async def _assemble(
    storage: LocalStorageBackend,
    service: SkillsService,
    *,
    skill_ids: list[str] | None = None,
    local_root: Path | None = None,
    workspace_path: str | None = None,
) -> SkillBackend:
    allowed = frozenset((await service.user_config.get_config()).enabled_prebuilt_ids)
    local_skills = LocalSkillsProvider([str(local_root)]).scan_all() if local_root else []

    async def _by_ids(skill_ids: list[str]) -> list[object]:
        return [skill for skill in local_skills if skill.id in skill_ids]

    with (
        patch("app.core.skills.store.service.skills_service", service),
        patch.object(service, "get_skills_by_ids", _by_ids),
    ):
        return await create_skill_backend(
            storage=storage,
            skill_ids=skill_ids,
            user_id="content-resolution-test" if skill_ids else None,
            workspace_path=workspace_path,
            allowed_prebuilt_ids=allowed,
        )


def _by_name(skills: list[SkillMetadata], name: str) -> SkillMetadata:
    return next(skill for skill in skills if skill.name == name)


@pytest.mark.asyncio
async def test_enabled_prebuilt_skills_serve_their_sop(storage: LocalStorageBackend, service: SkillsService) -> None:
    backend = await _assemble(storage, service)

    listed = await backend.list_skills()
    assert listed, "the curated default prebuilt skills must be enabled after the first sync"
    for skill in listed:
        document = await get_skill_document(skill, backend)
        assert document.startswith(f"# {skill.name}") or skill.name in document
        assert "Error: failed to load skill document" not in document


@pytest.mark.asyncio
async def test_prebuilt_skill_the_user_did_not_enable_stays_unreachable(
    storage: LocalStorageBackend, service: SkillsService
) -> None:
    backend = await _assemble(storage, service)

    listed_names = {skill.name for skill in await backend.list_skills()}
    assert "systematic-debugging" not in listed_names
    with pytest.raises(FileNotFoundError):
        await backend.get_skill_content("systematic-debugging")


@pytest.mark.asyncio
async def test_local_skill_resolves_by_runtime_name_and_by_id(
    tmp_path: Path, storage: LocalStorageBackend, service: SkillsService
) -> None:
    local_root = tmp_path / "local-skills"
    _write_skill(local_root, "probe-local", _LOCAL_SKILL_MD, {"scripts/run.py": "print('hi')\n"})
    skill_id = LocalSkillsProvider([str(local_root)]).scan_all()[0].id

    backend = await _assemble(storage, service, skill_ids=[skill_id], local_root=local_root)

    meta = _by_name(await backend.list_skills(), "probe_local_skill")
    assert meta.storage_skill_id == skill_id
    assert await backend.get_skill_content(meta.name) == _LOCAL_SKILL_MD
    assert await backend.get_skill_content(skill_id) == _LOCAL_SKILL_MD
    document = await get_skill_document(meta, backend)
    assert "Local SOP body." in document
    assert "Error: failed to load skill document" not in document


@pytest.mark.asyncio
async def test_local_skill_resources_are_listed_read_and_confined(
    tmp_path: Path, storage: LocalStorageBackend, service: SkillsService
) -> None:
    local_root = tmp_path / "local-skills"
    _write_skill(local_root, "probe-local", _LOCAL_SKILL_MD, {"scripts/run.py": "print('hi')\n"})
    (tmp_path / "secret.txt").write_text("outside the skill", encoding="utf-8")
    skill_id = LocalSkillsProvider([str(local_root)]).scan_all()[0].id

    backend = await _assemble(storage, service, skill_ids=[skill_id], local_root=local_root)

    meta = _by_name(await backend.list_skills(), "probe_local_skill")
    assert await backend.list_skill_resources(meta.storage_skill_id or meta.name) == ["scripts/run.py"]
    assert await backend.get_skill_resources(meta.name, "scripts/run.py") == b"print('hi')\n"
    with pytest.raises(FileNotFoundError):
        await backend.get_skill_resources(meta.name, "scripts/missing.py")
    with pytest.raises(ValueError):
        await backend.get_skill_resources(meta.name, "../../secret.txt")


@pytest.mark.asyncio
async def test_workspace_skill_resolves(tmp_path: Path, storage: LocalStorageBackend, service: SkillsService) -> None:
    workspace = tmp_path / "workspace"
    _write_skill(workspace / ".myrm" / "skills", "ws-probe", _WORKSPACE_SKILL_MD)

    backend = await _assemble(storage, service, workspace_path=str(workspace))

    meta = _by_name(await backend.list_skills(), "ws-probe")
    document = await get_skill_document(meta, backend)
    assert "Workspace SOP body." in document
