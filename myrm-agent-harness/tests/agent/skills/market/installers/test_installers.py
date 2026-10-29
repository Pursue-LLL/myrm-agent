"""Unit tests for the git skill installer.

[INPUT]
- myrm_agent_harness.agent.skills.market.installers.git_installer

[OUTPUT]
- pytest suite covering skill directory resolution, file collection,
  frontmatter parsing, and clone/extract failure paths. The git clone
  itself is stubbed, so no network or subprocess runs. The walk, the
  symlink policy and the size limits are in test_git_installer_collection.py.

[POS]
myrm-agent-harness/tests/agent/skills/market/installers/test_installers.py
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from myrm_agent_harness.agent.skills.market.installers.git_installer import (
    GitInstaller,
    _parse_skill_md_metadata,
)

SKILL_MD = b"---\nname: Alpha\ndescription: does alpha\n---\n# Alpha\n"


def _make_skill(root: Path, rel: str, *, name: str = "Alpha", body: bytes = b"") -> Path:
    skill_dir = root / rel
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_bytes(f"---\nname: {name}\ndescription: d\n---\n# body\n".encode())
    if body:
        (skill_dir / "data.txt").write_bytes(body)
    return skill_dir


class TestResolveSkillDir:
    def test_no_subdirectory_returns_root(self, tmp_path: Path) -> None:
        assert GitInstaller._resolve_skill_dir(tmp_path, None) == tmp_path

    def test_exact_path_wins(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "skills/pdf")
        assert GitInstaller._resolve_skill_dir(tmp_path, "skills/pdf") == tmp_path / "skills/pdf"

    def test_matches_by_directory_name(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "nested/deep/pdf")
        assert GitInstaller._resolve_skill_dir(tmp_path, "pdf") == tmp_path / "nested" / "deep" / "pdf"

    def test_matches_by_substring(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "skills/pdf-tools")
        assert GitInstaller._resolve_skill_dir(tmp_path, "pdf") == tmp_path / "skills" / "pdf-tools"

    def test_single_candidate_is_used(self, tmp_path: Path) -> None:
        _make_skill(tmp_path, "whatever/other")
        assert GitInstaller._resolve_skill_dir(tmp_path, "absent") == tmp_path / "whatever" / "other"

    def test_existing_dir_without_skill_md(self, tmp_path: Path) -> None:
        (tmp_path / "empty").mkdir()
        _make_skill(tmp_path, "a/first")
        _make_skill(tmp_path, "b/second")
        assert GitInstaller._resolve_skill_dir(tmp_path, "empty") == tmp_path / "empty"

    def test_falls_back_to_root_without_candidates(self, tmp_path: Path) -> None:
        assert GitInstaller._resolve_skill_dir(tmp_path, "absent") == tmp_path

    def test_ignores_git_internal_candidates(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "SKILL.md").write_bytes(SKILL_MD)
        (tmp_path / "real").mkdir()
        (tmp_path / "real" / "SKILL.md").write_bytes(SKILL_MD)
        # .git 内的候选被排除后只剩 real，走单候选回退
        assert GitInstaller._resolve_skill_dir(tmp_path, "zzz") == tmp_path / "real"


class TestCollectSkillFiles:
    def test_collects_files_and_metadata(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(tmp_path, "pdf", body=b"payload")
        result = GitInstaller()._collect_skill_files(skill_dir)
        assert result.name == "Alpha"
        assert result.description == "d"
        assert set(result.files) == {"SKILL.md", "data.txt"}
        assert result.files["data.txt"] == b"payload"

    def test_falls_back_to_searched_skill_md(self, tmp_path: Path) -> None:
        wrapper = tmp_path / "wrapper"
        inner = wrapper / "inner"
        inner.mkdir(parents=True)
        (inner / "SKILL.md").write_bytes(SKILL_MD)
        (wrapper / "readme.md").write_bytes(b"ignored")

        result = GitInstaller()._collect_skill_files(wrapper)

        assert result.name == "Alpha"
        assert set(result.files) == {"SKILL.md"}

    def test_missing_skill_md_raises(self, tmp_path: Path) -> None:
        (tmp_path / "nothing").mkdir()
        with pytest.raises(ValueError, match=r"SKILL\.md not found"):
            GitInstaller()._collect_skill_files(tmp_path / "nothing")

    def test_missing_frontmatter_falls_back_to_dir_name(self, tmp_path: Path) -> None:
        skill_dir = tmp_path / "plain"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_bytes(b"no frontmatter here")
        (skill_dir / "file.txt").write_bytes(b"x")
        result = GitInstaller()._collect_skill_files(skill_dir)
        # SKILL.md 存在但无 frontmatter：名称回退为占位符
        assert result.name == "unnamed_skill"
        assert result.description == ""

    def test_collect_skips_unreadable_files(self, tmp_path: Path) -> None:
        skill_dir = _make_skill(tmp_path, "pdf", body=b"data")
        locked = skill_dir / "locked.txt"
        locked.write_bytes(b"secret")
        locked.chmod(0o000)
        try:
            result = GitInstaller()._collect_skill_files(skill_dir)
        finally:
            locked.chmod(0o644)
        assert set(result.files) == {"SKILL.md", "data.txt"}


class TestSkillMdMetadata:
    @pytest.mark.parametrize(
        ("content", "expected"),
        [
            (SKILL_MD, ("Alpha", "does alpha")),
            (b"no frontmatter", ("unnamed_skill", "")),
            (b"---\nbroken: [\n---\nbody", ("unnamed_skill", "")),
            (b"---\n- a\n- b\n---\nbody", ("unnamed_skill", "")),
        ],
    )
    def test_parse_skill_md_metadata(self, content: bytes, expected: tuple[str, str]) -> None:
        assert _parse_skill_md_metadata(content) == expected


class TestGitInstallerDownload:
    @pytest.mark.asyncio
    async def test_download_cleans_temp_dir(self, tmp_path: Path) -> None:
        installer = GitInstaller()
        seen: dict[str, Path] = {}

        async def _fake_clone(_self: object, url: str, target: Path, *, ref: str | None = None) -> None:
            seen["target"] = target
            _make_skill(target, "skills/pdf", body=b"data")

        with (
            patch.object(GitInstaller, "_git_clone", new=_fake_clone),
            patch("myrm_agent_harness.agent.skills.market.installers.git_installer.shutil.rmtree") as rmtree,
        ):
            result = await installer.download("https://example.invalid/x.git", "skills/pdf")

        assert rmtree.called
        assert result.files["data.txt"] == b"data"

    @pytest.mark.asyncio
    async def test_clone_failure_propagates_and_cleans(self) -> None:
        installer = GitInstaller()
        with (
            patch.object(
                GitInstaller,
                "_git_clone",
                new=AsyncMock(side_effect=ValueError("Git clone failed: nope")),
            ),
            patch("myrm_agent_harness.agent.skills.market.installers.git_installer.shutil.rmtree") as rmtree,
            pytest.raises(ValueError, match="Git clone failed"),
        ):
            await installer.download("https://example.invalid/x.git")

        assert rmtree.called

    @pytest.mark.asyncio
    async def test_clone_timeout_reports_url(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        proc = MagicMock()
        proc.communicate = AsyncMock(side_effect=TimeoutError)
        proc.returncode = None

        with (
            patch(
                "myrm_agent_harness.agent.skills.market.installers.git_installer.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=proc),
            ),
            pytest.raises(ValueError, match="timed out after 60s"),
        ):
            await GitInstaller()._git_clone("https://example.invalid/x.git", tmp_path)

        assert proc.kill.called

    @pytest.mark.asyncio
    async def test_clone_reports_stderr(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b"permission denied"))
        proc.returncode = 128

        with (
            patch(
                "myrm_agent_harness.agent.skills.market.installers.git_installer.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=proc),
            ),
            pytest.raises(ValueError, match="permission denied"),
        ):
            await GitInstaller()._git_clone("https://example.invalid/x.git", tmp_path)

    @pytest.mark.asyncio
    async def test_clone_includes_branch_flag(self, tmp_path: Path) -> None:
        from unittest.mock import MagicMock

        proc = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))
        proc.returncode = 0

        with patch(
            "myrm_agent_harness.agent.skills.market.installers.git_installer.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ) as spawn:
            await GitInstaller()._git_clone("https://example.invalid/x.git", tmp_path, ref="dev")

        assert "--branch" in spawn.await_args.args
        assert "dev" in spawn.await_args.args
