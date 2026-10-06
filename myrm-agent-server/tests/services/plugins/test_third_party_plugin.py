"""A real third-party Agent Plugins package imports the way the standard says it should.

Every other plugin suite feeds the parser what this repository writes. This package (Hindsight,
MIT, see the fixture's NOTICE) was written by someone else, so an assumption that only holds
for our own output fails here.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import jsonschema
import pytest
from myrm_agent_harness.agent.plugins.models import PluginDiagnosticLevel, PluginParseResult

from app.services.plugins._preview import build_preview_result
from app.services.plugins._preview_context import PreviewContext
from app.services.plugins.import_service import parse_plugin_zip

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "agent_plugins"
_PACKAGE = _FIXTURES / "third_party" / "hindsight"


def _archive(wrapper: str) -> bytes:
    """The package as one archive: flat, or inside a wrapper directory like a repository download."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(_PACKAGE.rglob("*")):
            if path.is_file() and path.name != "NOTICE":
                archive.writestr(wrapper + path.relative_to(_PACKAGE).as_posix(), path.read_bytes())
    return buffer.getvalue()


@pytest.fixture(params=["", "hindsight-main/"], ids=["flat", "wrapped"])
def parsed(request: pytest.FixtureRequest) -> PluginParseResult:
    return parse_plugin_zip(_archive(request.param))


def test_the_package_itself_conforms_to_the_frozen_official_schemas() -> None:
    for document, schema in (("plugin.json", "plugin.schema.json"), ("mcp.json", "mcp.schema.json")):
        jsonschema.validate(json.loads((_PACKAGE / document).read_text()), json.loads((_FIXTURES / schema).read_text()))


def test_the_manifest_is_read_as_declared_and_foreign_extensions_stay_foreign(parsed: PluginParseResult) -> None:
    assert parsed.meta is not None
    assert (parsed.meta.name, parsed.meta.version, parsed.meta.license) == ("hindsight", "1.0.0", "MIT")
    assert parsed.meta.repository == "https://github.com/vectorize-io/hindsight"
    assert "memory" in parsed.meta.keywords
    assert set(parsed.meta.extensions) == {"io.vectorize.hindsight"}
    assert parsed.agents == [] and parsed.workspace_files == {}
    assert [d for d in parsed.diagnostics if d.level is not PluginDiagnosticLevel.INFO] == []


def test_the_skill_arrives_with_its_text(parsed: PluginParseResult) -> None:
    (skill,) = parsed.skills

    assert skill.name == "hindsight-memory"
    assert set(skill.files) == {"SKILL.md"}
    assert skill.description.startswith("Long-term memory for the agent")


def test_the_connector_keeps_the_placeholders_its_author_wrote(parsed: PluginParseResult) -> None:
    (server,) = parsed.servers

    assert (server.name, server.server_type, server.url) == (
        "hindsight",
        "streamable_http",
        "https://api.hindsight.vectorize.io/mcp",
    )
    assert server.headers == {"Authorization": "Bearer ${HINDSIGHT_API_KEY}", "X-Bank-Id": "${HINDSIGHT_BANK_ID}"}
    assert server.is_runnable


@pytest.mark.parametrize("allow_stdio", [True, False], ids=["local", "cloud"])
def test_the_preview_offers_everything_and_a_remote_connector_is_never_blocked(
    parsed: PluginParseResult, allow_stdio: bool
) -> None:
    preview = build_preview_result(parsed, PreviewContext(allow_stdio=allow_stdio))

    assert preview["is_valid"] is True
    assert preview["agents"] == []
    (skill,) = preview["skills"]
    assert skill["blocked_reason"] is None and skill["security_issues"] == [] and skill["conflict"] is False
    (server,) = preview["servers"]
    assert server["blocked_reason"] is None
