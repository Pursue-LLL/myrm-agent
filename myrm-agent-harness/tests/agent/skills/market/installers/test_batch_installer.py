"""Unit tests for the Hermes batch import parser.

[INPUT]
- myrm_agent_harness.agent.skills.market.installers.batch_installer

[OUTPUT]
- pytest suite covering directory-grouped and root-level skills, name fallbacks, keyword handling, malformed
  frontmatter and excluded paths, parsed from in-memory archives.

[POS]
myrm-agent-harness/tests/agent/skills/market/installers/test_batch_installer.py
"""

import io
import zipfile

import pytest

from myrm_agent_harness.agent.skills.market.installers.batch_installer import HermesBatchParser

SKILL_MD = b"---\nname: Alpha\ndescription: does alpha\n---\n# Alpha\n"


def create_mock_zip(files: dict) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for file_path, content in files.items():
            zip_file.writestr(file_path, content)
    return zip_buffer.getvalue()


@pytest.mark.asyncio
async def test_hermes_batch_parser_valid_zip():
    skill1_md = """---
name: translate_skill
description: Translate text
trigger_keywords: ["translate", "翻译"]
---
def translate():
    pass
"""
    skill2_md = """---
name: summarize_skill
description: Summarize text
---
def summarize():
    pass
"""
    files = {
        "translate_skill/SKILL.md": skill1_md,
        "translate_skill/utils.py": "def util(): pass",
        "summarize_skill/README.md": skill2_md,
        "ignored_root_file.txt": "ignore me",
    }
    zip_bytes = create_mock_zip(files)

    parser = HermesBatchParser()
    skills = parser.parse_zip(zip_bytes)

    assert len(skills) == 2

    # Verify translate_skill
    translate = next((s for s in skills if s.name == "translate_skill"), None)
    assert translate is not None
    assert translate.description == "Translate text\n\n触发关键词(Patterns): translate, 翻译"
    assert "def translate():" in translate.content
    assert "utils.py" in translate.files

    # Verify summarize_skill
    summarize = next((s for s in skills if s.name == "summarize_skill"), None)
    assert summarize is not None
    assert summarize.description == "Summarize text"


@pytest.mark.asyncio
async def test_hermes_batch_parser_empty_zip():
    zip_bytes = create_mock_zip({})
    parser = HermesBatchParser()
    skills = parser.parse_zip(zip_bytes)
    assert len(skills) == 0


@pytest.mark.asyncio
async def test_hermes_batch_parser_no_md():
    files = {
        "bad_skill/main.py": "def main(): pass",
    }
    zip_bytes = create_mock_zip(files)
    parser = HermesBatchParser()
    skills = parser.parse_zip(zip_bytes)
    # Should skip because no .md file is found
    assert len(skills) == 0


class TestHermesBatchParser:
    def test_parses_directory_grouped_skills(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.batch_installer import (
            HermesBatchParser,
        )

        payload = create_mock_zip(
            {
                "alpha/SKILL.md": SKILL_MD,
                "alpha/notes.md": b"extra",
                "beta/SKILL.md": b"---\nname: Beta\ndescription: b\n---\n# Beta\n",
            }
        )
        skills = HermesBatchParser().parse_zip(payload)
        by_name = {s.name: s for s in skills}
        assert set(by_name) == {"Alpha", "Beta"}
        assert by_name["Alpha"].files["notes.md"] == b"extra"

    def test_parses_root_level_skill(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.batch_installer import (
            HermesBatchParser,
        )

        payload = create_mock_zip({"SKILL.md": SKILL_MD})
        skills = HermesBatchParser().parse_zip(payload)
        assert [s.name for s in skills] == ["Alpha"]

    def test_root_level_skill_without_name_falls_back(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.batch_installer import (
            HermesBatchParser,
        )

        payload = create_mock_zip({"SKILL.md": b"no frontmatter body"})
        assert [s.name for s in HermesBatchParser().parse_zip(payload)] == ["unnamed_skill"]

    def test_alternate_markdown_is_promoted(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.batch_installer import (
            HermesBatchParser,
        )

        payload = create_mock_zip({"alpha/README.md": SKILL_MD})
        skills = HermesBatchParser().parse_zip(payload)
        assert skills[0].name == "Alpha"
        assert "SKILL.md" in skills[0].files

    def test_group_without_markdown_is_skipped(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.batch_installer import (
            HermesBatchParser,
        )

        payload = create_mock_zip({"alpha/data.bin": b"\x00\x01"})
        assert HermesBatchParser().parse_zip(payload) == []

    def test_trigger_keywords_are_appended(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.batch_installer import (
            HermesBatchParser,
        )

        payload = create_mock_zip(
            {"alpha/SKILL.md": b"---\nname: A\ndescription: d\ntrigger_keywords: [x, y]\n---\nbody\n"}
        )
        skill = HermesBatchParser().parse_zip(payload)[0]
        assert "x, y" in skill.description
        assert skill.metadata["trigger_keywords"] == ["x", "y"]

    def test_single_string_keyword_is_wrapped(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.batch_installer import (
            HermesBatchParser,
        )

        payload = create_mock_zip({"alpha/SKILL.md": b"---\nname: A\ntrigger_keywords: solo\n---\nbody\n"})
        assert "solo" in HermesBatchParser().parse_zip(payload)[0].description

    def test_malformed_frontmatter_is_tolerated(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.batch_installer import (
            HermesBatchParser,
        )

        payload = create_mock_zip({"alpha/SKILL.md": b"---\nbroken: [\n---\nbody\n"})
        assert [s.name for s in HermesBatchParser().parse_zip(payload)] == ["alpha"]

    def test_skill_md_content_decodes(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.batch_installer import (
            HermesImportedSkill,
        )

        skill = HermesImportedSkill(name="A", description="d", content="c")
        skill.files["SKILL.md"] = b"# body"
        assert skill.skill_md_content == "# body"

    def test_skill_md_content_defaults_empty(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.batch_installer import (
            HermesImportedSkill,
        )

        assert HermesImportedSkill(name="A", description="d", content="c").skill_md_content == ""

    def test_excluded_paths_are_filtered(self) -> None:
        from myrm_agent_harness.agent.skills.market.installers.batch_installer import (
            _is_excluded_file as batch_excluded,
        )

        assert batch_excluded("a/node_modules/b.txt") is True
        assert batch_excluded("a/.DS_Store") is True
        assert batch_excluded("a/__MACOSX/b") is True
        assert batch_excluded("alpha/SKILL.md") is False
