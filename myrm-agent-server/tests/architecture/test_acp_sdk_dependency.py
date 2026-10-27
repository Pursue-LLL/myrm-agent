"""The server installs the harness' ACP SDK, because an external agent can be configured with ``type: "acp"``.

[POS]
tests/architecture/test_acp_sdk_dependency.py

[INPUT]
- myrm-agent-server/pyproject.toml: the ``myrm-agent-harness[...]`` dependency and ``[tool.uv] constraint-dependencies``

[OUTPUT]
- Fails when the server stops installing the ``acp`` extra (the first ACP turn would end in an import error) or lets
  the resolver pick the unreleased 1.x SDK the harness backend is not written against.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

_PYPROJECT = tomllib.loads((Path(__file__).resolve().parents[2] / "pyproject.toml").read_text())


def _harness_extras() -> set[str]:
    spec = next(dep for dep in _PYPROJECT["project"]["dependencies"] if dep.startswith("myrm-agent-harness["))
    match = re.search(r"\[(?P<extras>[^\]]*)\]", spec)
    assert match is not None
    return {extra.strip() for extra in match["extras"].split(",")}


def test_the_server_installs_the_harness_acp_extra() -> None:
    assert "acp" in _harness_extras()


def test_the_resolver_cannot_pick_the_unreleased_sdk_major() -> None:
    # The server resolves with prerelease = "allow", which would take 1.0 release candidates over the 0.x line.
    assert "agent-client-protocol<1" in _PYPROJECT["tool"]["uv"]["constraint-dependencies"]
