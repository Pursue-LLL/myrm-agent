"""Architecture guard: bash skills must document the Bash execution contract."""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SKILLS_ROOT = _REPO_ROOT / "assets" / "prebuilt_skills"
_BASH_TOOL_MARKER = "bash_code_execute_tool"
_CONTRACT_HEADING = "## Bash execution contract"


def _bash_skill_files() -> list[Path]:
    files: list[Path] = []
    if not _SKILLS_ROOT.is_dir():
        return files
    for path in sorted(_SKILLS_ROOT.glob("*/SKILL.md")):
        text = path.read_text(encoding="utf-8")
        if _BASH_TOOL_MARKER in text:
            files.append(path)
    return files


@pytest.mark.architecture
@pytest.mark.parametrize("skill_path", _bash_skill_files(), ids=lambda p: p.parent.name)
def test_bash_skill_includes_execution_contract(skill_path: Path) -> None:
    text = skill_path.read_text(encoding="utf-8")
    if _CONTRACT_HEADING not in text:
        rel = skill_path.relative_to(_REPO_ROOT)
        pytest.fail(
            f"{rel}: SKILL references {_BASH_TOOL_MARKER!r} but is missing {_CONTRACT_HEADING!r}. "
            "Add the Bash execution contract section so LLM calls include a valid reason."
        )
