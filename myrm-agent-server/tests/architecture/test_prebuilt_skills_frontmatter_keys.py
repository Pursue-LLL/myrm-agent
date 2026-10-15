"""Architecture guard: shipped prebuilt skills may only declare frontmatter keys the runtime reads.

The skill loader only logs a warning for an unknown frontmatter key, so a skill that declares a key
the runtime ignores (for example ``tools`` instead of ``allowed-tools``) installs cleanly and then
silently does nothing. This guard turns that warning into a CI failure for the assets we ship.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest
from myrm_agent_harness.api.skills import parse_skill_frontmatter

_SKILLS_ROOT = Path(__file__).resolve().parents[2] / "assets" / "prebuilt_skills"
_SKILL_DIRS = sorted(path.parent for path in _SKILLS_ROOT.glob("*/SKILL.md"))
# Read by server code instead of the skill runtime: app/services/kanban/pipeline/spec_io.py.
_SERVER_OWNED_KEYS = frozenset({"pipeline_spec"})
_UNKNOWN_KEYS_WARNING = re.compile(r"unknown frontmatter fields: (?P<keys>.+)$")


def _unknown_frontmatter_keys(content: str, skill_name: str, caplog: pytest.LogCaptureFixture) -> set[str]:
    """Return the frontmatter keys the loader reports as unknown for ``content``."""
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        parse_skill_frontmatter(content, skill_name)
    unknown: set[str] = set()
    for record in caplog.records:
        match = _UNKNOWN_KEYS_WARNING.search(record.getMessage())
        if match:
            unknown.update(key.strip() for key in match["keys"].split(","))
    return unknown


@pytest.mark.architecture
def test_prebuilt_skills_are_discovered() -> None:
    assert _SKILL_DIRS, f"no SKILL.md found under {_SKILLS_ROOT}"


@pytest.mark.architecture
def test_unknown_key_detector_reports_a_misspelled_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Self-check: the guard must be able to fail, otherwise it passes vacuously."""
    content = "---\nname: probe-skill\ndescription: Probe skill for the guard self-check.\ntools: [bash]\n---\nBody\n"
    assert _unknown_frontmatter_keys(content, "probe-skill", caplog) == {"tools"}


@pytest.mark.architecture
@pytest.mark.parametrize("skill_dir", _SKILL_DIRS, ids=lambda path: path.name)
def test_prebuilt_skill_declares_only_known_frontmatter_keys(skill_dir: Path, caplog: pytest.LogCaptureFixture) -> None:
    content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    unknown = _unknown_frontmatter_keys(content, skill_dir.name, caplog) - _SERVER_OWNED_KEYS
    assert not unknown, (
        f"{skill_dir.name}/SKILL.md declares frontmatter keys the skill runtime ignores: {sorted(unknown)}. "
        "Use a supported key (for example `allowed-tools`, `requires`, `metadata`) or remove it."
    )
