"""A built-in domain skill's tool files are exactly the ones its manifest registers.

Domain tools run only through ``manifest.json`` ``python_tools``; a file the manifest does not name can never
be called, yet it reads in review as a tool the skill offers. The reverse (a registration whose file is gone)
fails ``test_cn_social_tool_script_paths_resolve`` in ``test_domain_skill_store.py``; this test closes the
other direction for every built-in skill, so a new skill cannot leave an unregistered tool behind.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.browser.domain_skills import DomainSkillStore

_BUILTIN_DIR = Path(__file__).resolve().parents[4] / "src/myrm_agent_harness/toolkits/browser/domain_skills/builtin"
_SKILL_IDS = sorted(path.name for path in _BUILTIN_DIR.iterdir() if (path / "manifest.json").is_file())


@pytest.mark.parametrize("skill_id", _SKILL_IDS)
def test_a_builtin_tool_file_exists_only_where_its_manifest_registers_it(skill_id: str) -> None:
    manifest = DomainSkillStore(load_builtin=True, user_dir="/nonexistent").get(skill_id)
    assert manifest is not None

    registered = {tool.script_path for tool in manifest.python_tools.values()}
    on_disk = {f"tools/{path.name}" for path in (_BUILTIN_DIR / skill_id / "tools").glob("*.py")}

    assert on_disk == registered
