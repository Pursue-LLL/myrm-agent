"""Unit tests for the ZIP skill installer.

[INPUT]
- myrm_agent_harness.agent.skills.market.installers.zip_installer

[OUTPUT]
- pytest suite covering excluded paths, skill extraction from an archive (root, subdirectory, plugin manifest, shallowest
  skill root, missing SKILL.md) and the download limits. The fetch is stubbed, so no network runs.

[POS]
myrm-agent-harness/tests/agent/skills/market/installers/test_zip_installer.py
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.skills.market.installers.zip_installer import (
    MAX_ZIP_SIZE,
    ZIP_DOWNLOAD_TIMEOUT,
    ZipInstaller,
    _is_excluded_file,
)

SKILL_MD = b"---\nname: Alpha\ndescription: does alpha\n---\n# Alpha\n"


class TestZipExclusion:
    @pytest.mark.parametrize(
        "path",
        ["a/.git/b.txt", "a/node_modules/b.txt", "a/.venv/b.txt", "a/__pycache__/b.txt", ".hidden/b.txt"],
    )
    def test_excluded_paths(self, path: str) -> None:
        assert _is_excluded_file(path) is True

    def test_regular_path_included(self) -> None:
        assert _is_excluded_file("skills/pdf/SKILL.md") is False


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class TestZipInstaller:
    @pytest.mark.asyncio
    async def test_extracts_skill_at_root(self) -> None:
        payload = _zip_bytes({"SKILL.md": SKILL_MD, "data.txt": b"payload"})
        result = ZipInstaller()._extract_skill(payload, None)
        assert result.name == "Alpha"
        assert result.files["data.txt"] == b"payload"

    @pytest.mark.asyncio
    async def test_honours_subdirectory(self) -> None:
        # strip_top_dir 会剥掉首个路径段，故顶层目录为 archive-root
        payload = _zip_bytes({"archive-root/skills/pdf/SKILL.md": SKILL_MD})
        result = ZipInstaller()._extract_skill(payload, "skills/pdf/")
        assert set(result.files) == {"SKILL.md"}

    @pytest.mark.asyncio
    async def test_reads_plugin_manifest(self) -> None:
        import json

        payload = _zip_bytes({"plugin.json": json.dumps({"name": "suite", "description": "d"}).encode()})
        result = ZipInstaller()._extract_skill(payload, None)
        assert result.name == "suite"
        assert result.description == "d"

    @pytest.mark.asyncio
    async def test_malformed_plugin_manifest_falls_back(self) -> None:
        payload = _zip_bytes({"plugin.json": b"{not json", "SKILL.md": SKILL_MD})
        result = ZipInstaller()._extract_skill(payload, None)
        assert result.name == "Alpha"

    @pytest.mark.asyncio
    async def test_selects_shallowest_skill_root(self) -> None:
        # strip_top_dir 会剥掉统一的顶层目录，此处两个候选深度不同
        payload = _zip_bytes(
            {
                "archive-root/a/b/SKILL.md": SKILL_MD,
                "archive-root/top/SKILL.md": SKILL_MD,
            }
        )
        result = ZipInstaller()._extract_skill(payload, None)
        assert set(result.files) == {"SKILL.md"}

    @pytest.mark.asyncio
    async def test_missing_skill_md_raises(self) -> None:
        payload = _zip_bytes({"readme.md": b"x"})
        with pytest.raises(ValueError, match=r"SKILL\.md not found in ZIP"):
            ZipInstaller()._extract_skill(payload, None)

    @pytest.mark.asyncio
    async def test_subdirectory_without_manifest_raises(self) -> None:
        payload = _zip_bytes({"other/x.txt": b"x"})
        with pytest.raises(ValueError, match=r"SKILL\.md or plugin\.json not found"):
            ZipInstaller()._extract_skill(payload, "absent")

    @pytest.mark.asyncio
    async def test_plugin_only_archive_uses_default_name(self) -> None:
        payload = _zip_bytes({"plugin.json": b"{not json", "other.txt": b"x"})
        result = ZipInstaller()._extract_skill(payload, None)
        assert result.name == "agent-plugin"
        assert result.description == ""

    @pytest.mark.asyncio
    async def test_download_failure_raises(self) -> None:

        with patch(
            "myrm_agent_harness.core.security.http.secure_fetch.secure_get",
            new=AsyncMock(),
        ) as fetch:
            from types import SimpleNamespace

            fetch.return_value = SimpleNamespace(status_code=404, content=b"")
            with pytest.raises(ValueError, match="HTTP 404"):
                await ZipInstaller()._download_zip("https://example.invalid/a.zip")

    @pytest.mark.asyncio
    async def test_oversized_download_raises(self) -> None:
        from myrm_agent_harness.core.security.http.secure_fetch import ContentTooLargeError

        with (
            patch(
                "myrm_agent_harness.core.security.http.secure_fetch.secure_get",
                new=AsyncMock(side_effect=ContentTooLargeError("too big")),
            ),
            pytest.raises(ValueError, match="ZIP too large"),
        ):
            await ZipInstaller()._download_zip("https://example.invalid/a.zip")

    @pytest.mark.asyncio
    async def test_download_returns_content(self) -> None:
        from types import SimpleNamespace

        with patch(
            "myrm_agent_harness.core.security.http.secure_fetch.secure_get",
            new=AsyncMock(return_value=SimpleNamespace(status_code=200, content=b"PK")),
        ):
            assert await ZipInstaller()._download_zip("https://example.invalid/a.zip") == b"PK"

    @pytest.mark.asyncio
    async def test_download_forwards_limits(self) -> None:
        from types import SimpleNamespace

        with patch(
            "myrm_agent_harness.core.security.http.secure_fetch.secure_get",
            new=AsyncMock(return_value=SimpleNamespace(status_code=200, content=b"PK")),
        ) as fetch:
            await ZipInstaller()._download_zip("https://example.invalid/a.zip")
        assert fetch.await_args.kwargs["max_content_length"] == MAX_ZIP_SIZE
        assert fetch.await_args.kwargs["timeout"] == ZIP_DOWNLOAD_TIMEOUT

    @pytest.mark.asyncio
    async def test_zip_download_composes_fetch_and_extract(self) -> None:
        payload = _zip_bytes({"SKILL.md": SKILL_MD})
        with patch.object(ZipInstaller, "_download_zip", new=AsyncMock(return_value=payload)):
            result = await ZipInstaller().download("https://example.invalid/a.zip", None)
        assert result.name == "Alpha"
        assert set(result.files) == {"SKILL.md"}
