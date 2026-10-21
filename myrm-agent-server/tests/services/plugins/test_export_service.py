"""Expert export end to end: nothing secret leaves, decisions are honoured, the package re-imports."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Mapping, Sequence
from typing import cast
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.plugins import PluginPackageResult

from app.services.plugins._export_models import ExportError, ExportErrorCode
from app.services.plugins._preview import build_preview_result
from app.services.plugins._preview_context import PreviewContext
from app.services.plugins.export_service import (
    ExportedPackage,
    export_expert,
    preview_expert_export,
)
from app.services.plugins.import_service import parse_plugin_zip
from app.services.plugins.template_workspace import TEMPLATE_FILES_KEY, encode_template_files
from tests.support.export_world import SKILL_MD, ExportWorld

# Each canary sits on a different surface a recipient can read.
SKILL_FILE_CANARY = "ghp_SkillFileCanary0123456789"
PROMPT_CANARY = "sk-ant-api03-SystemPromptCanary0123456789"
DESCRIPTION_CANARY = "AKIAIOSFODNN7EXAMPLE"
SUGGESTION_CANARY = "hf_SuggestionCanary0123456789"
WORKSPACE_CANARY = "ntn_WorkspaceCanary0123456789"
HEADER_CANARY = "live-header-secret-canary-9f31"
CANARIES = (SKILL_FILE_CANARY, PROMPT_CANARY, DESCRIPTION_CANARY, SUGGESTION_CANARY, WORKSPACE_CANARY, HEADER_CANARY)

SKILL_PATH = "skills/notes/scripts/run.sh"
PROMPT_PATH = "experts/1-Lead/system_prompt.md"
DESCRIPTION_PATH = "experts/1-Lead/description.txt"
SUGGESTION_PATH = "experts/1-Lead/suggestion-1.txt"
WORKSPACE_PATH = "workspace/README.md"
LEAKY_PATHS = {SKILL_PATH, PROMPT_PATH, DESCRIPTION_PATH, SUGGESTION_PATH, WORKSPACE_PATH}


@pytest.fixture
def leaky(world: ExportWorld) -> ExportWorld:
    """An expert that leaks one secret on every surface that ships."""
    world.custom_skill(
        "local::a1",
        "notes",
        {"SKILL.md": SKILL_MD, "scripts/run.sh": f"#!/bin/sh\nexport GITHUB_TOKEN={SKILL_FILE_CANARY}\n".encode()},
        directory="notes",
    )
    world.preset_skill("web-research", "web-research")
    world.server(
        name="docs",
        type="streamable_http",
        url="https://docs.example.com/mcp",
        headers={"Authorization": f"Bearer {HEADER_CANARY}"},
    )
    templates = encode_template_files({"README.md": f"# Team notes\nkey: {WORKSPACE_CANARY}\n".encode()})
    world.expert(
        "lead",
        "Lead",
        skills=("local::a1", "web-research"),
        mcps=("docs",),
        subagents=("worker",),
        model="gpt-4o",
        description=f"Lead with credentials {DESCRIPTION_CANARY}",
        system_prompt=f"Call the API with {PROMPT_CANARY} when asked.",
        metadata={
            "suggestion_prompts": [f"Use {SUGGESTION_CANARY} to sync"],
            "engine_params": {TEMPLATE_FILES_KEY: templates.files},
        },
    )
    world.expert("worker", "Worker", skills=("local::a1",))
    return world


def _entries(package: ExportedPackage) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(package.zip_content)) as archive:
        return {info.filename: archive.read(info) for info in archive.infolist() if not info.is_dir()}


def _everything(package: ExportedPackage) -> str:
    """All names and (decompressed) contents of the package as one searchable text."""
    entries = _entries(package)
    return "\n".join(list(entries) + [content.decode("utf-8", "replace") for content in entries.values()])


async def _export(
    agent_id: str = "lead",
    *,
    apply: bool = False,
    ignored: Mapping[str, Sequence[int]] | None = None,
    digest: str | None = None,
) -> ExportedPackage:
    return await export_expert(agent_id, apply_redactions=apply, ignored_redactions=ignored, review_digest=digest)


class TestPreview:
    @pytest.mark.asyncio
    async def test_findings_are_listed_for_every_surface_that_ships(self, leaky: ExportWorld) -> None:
        preview = await preview_expert_export("lead")

        assert set(preview.redactions) == LEAKY_PATHS
        assert all(preview.redactions[path] for path in LEAKY_PATHS)

    @pytest.mark.asyncio
    async def test_the_package_is_dry_run_built(self, leaky: ExportWorld) -> None:
        preview = await preview_expert_export("lead")

        assert preview.build_error is None
        assert preview.package_bytes and preview.package_bytes > 0
        assert preview.version == "1.0.0"

    @pytest.mark.asyncio
    async def test_a_failed_dry_run_is_reported_instead_of_raised(self, leaky: ExportWorld) -> None:
        failure = PluginPackageResult(success=False, zip_content=None, filename=None, error="unsafe path")
        with patch("app.services.plugins.export_service.build_plugin_bundle", return_value=failure):
            preview = await preview_expert_export("lead")

        assert (preview.package_bytes, preview.build_error) == (None, "unsafe path")

    @pytest.mark.asyncio
    async def test_the_digest_follows_the_reviewed_content(self, leaky: ExportWorld) -> None:
        first = await preview_expert_export("lead")
        again = await preview_expert_export("lead")
        leaky.profiles["lead"].system_prompt = "Changed prompt."
        changed = await preview_expert_export("lead")

        assert first.review_digest == again.review_digest
        assert first.review_digest != changed.review_digest


class TestNothingSecretLeaves:
    @pytest.mark.asyncio
    async def test_findings_must_be_decided_before_anything_is_built(self, leaky: ExportWorld) -> None:
        with pytest.raises(ExportError) as caught:
            await _export()

        assert caught.value.code is ExportErrorCode.REVIEW_REQUIRED

    @pytest.mark.asyncio
    async def test_applying_redactions_removes_every_canary_from_every_part_of_the_package(self, leaky: ExportWorld) -> None:
        package = await _export(apply=True)

        text = _everything(package)
        leaked = [canary for canary in CANARIES if canary in text]
        assert leaked == []
        assert package.zip_content.count(b"PK") >= 1  # sanity: a real archive was produced

    @pytest.mark.asyncio
    async def test_header_values_never_reach_the_package_even_though_they_are_not_scanned(self, leaky: ExportWorld) -> None:
        # Connectors are declarations: literal header values are replaced by placeholders before any scan.
        preview = await preview_expert_export("lead")

        assert not any("docs" in path for path in preview.redactions)
        assert HEADER_CANARY not in _everything(await _export(apply=True))

    @pytest.mark.asyncio
    async def test_a_kept_finding_is_the_authors_explicit_decision(self, leaky: ExportWorld) -> None:
        preview = await preview_expert_export("lead")
        keep_everything = {path: list(range(len(findings))) for path, findings in preview.redactions.items()}

        package = await _export(ignored=keep_everything, digest=preview.review_digest)

        text = _everything(package)
        assert all(canary in text for canary in CANARIES if canary != HEADER_CANARY)

    @pytest.mark.asyncio
    async def test_keeping_some_findings_still_redacts_the_others_when_asked(self, leaky: ExportWorld) -> None:
        preview = await preview_expert_export("lead")
        keep_prompt = {PROMPT_PATH: list(range(len(preview.redactions[PROMPT_PATH])))}

        package = await _export(apply=True, ignored=keep_prompt, digest=preview.review_digest)

        text = _everything(package)
        assert PROMPT_CANARY in text
        assert all(canary not in text for canary in CANARIES if canary not in {PROMPT_CANARY})

    @pytest.mark.asyncio
    async def test_keeping_only_some_findings_without_redacting_the_rest_is_still_a_review_gap(self, leaky: ExportWorld) -> None:
        preview = await preview_expert_export("lead")
        keep_prompt = {PROMPT_PATH: list(range(len(preview.redactions[PROMPT_PATH])))}

        with pytest.raises(ExportError) as caught:
            await _export(ignored=keep_prompt, digest=preview.review_digest)

        assert caught.value.code is ExportErrorCode.REVIEW_REQUIRED

    @pytest.mark.asyncio
    async def test_decisions_are_void_when_the_expert_changed_after_the_preview(self, leaky: ExportWorld) -> None:
        preview = await preview_expert_export("lead")
        leaky.profiles["lead"].system_prompt = f"A different prompt with {PROMPT_CANARY}."
        keep_prompt = {PROMPT_PATH: [0]}

        with pytest.raises(ExportError) as caught:
            await _export(ignored=keep_prompt, digest=preview.review_digest)

        assert caught.value.code is ExportErrorCode.CHANGED_SINCE_PREVIEW

    @pytest.mark.asyncio
    async def test_decisions_without_a_digest_are_refused(self, leaky: ExportWorld) -> None:
        with pytest.raises(ExportError) as caught:
            await _export(ignored={PROMPT_PATH: [0]})

        assert caught.value.code is ExportErrorCode.CHANGED_SINCE_PREVIEW

    @pytest.mark.asyncio
    async def test_a_clean_expert_exports_without_any_decision(self, world: ExportWorld) -> None:
        world.custom_skill("local::a1", "notes", directory="notes")
        world.expert("lead", "Lead", skills=("local::a1",))

        package = await _export()

        assert package.filename.endswith(".zip")


class TestPackage:
    @pytest.mark.asyncio
    async def test_the_same_expert_always_produces_the_same_bytes(self, leaky: ExportWorld) -> None:
        first = await _export(apply=True)
        second = await _export(apply=True)

        assert first.zip_content == second.zip_content
        assert first.filename == second.filename

    @pytest.mark.asyncio
    async def test_the_package_reimports_with_every_dependency_resolved(self, leaky: ExportWorld) -> None:
        package = await _export(apply=True)

        parsed = parse_plugin_zip(package.zip_content)
        preview = build_preview_result(parsed, PreviewContext(skill_ids_by_name={"web-research": "web-research"}))

        assert [agent.name for agent in parsed.agents] == ["Lead", "Worker"]
        assert [skill.name for skill in parsed.skills] == ["notes"]
        assert [server.name for server in parsed.servers] == ["docs"]
        assert sorted(parsed.workspace_files) == ["README.md"]
        entry = next(a for a in cast("list[dict[str, object]]", preview["agents"]) if a["name"] == "Lead")
        assert entry["unresolved_skills"] == []
        assert entry["unresolved_connectors"] == []
        assert entry["unresolved_subagents"] == []
        assert entry["recommended_model"] == "gpt-4o"
        assert entry["is_entry_agent"] is True

    @pytest.mark.asyncio
    async def test_connectors_travel_as_declarations_with_secret_placeholders(self, leaky: ExportWorld) -> None:
        parsed = parse_plugin_zip((await _export(apply=True)).zip_content)

        (server,) = parsed.servers
        assert server.url == "https://docs.example.com/mcp"
        assert server.headers == {"Authorization": "{{secret:Authorization}}"}

    @pytest.mark.asyncio
    async def test_third_party_provenance_is_recorded_for_updates(self, leaky: ExportWorld) -> None:
        leaky.custom_skill("local::b2", "borrowed", directory="borrowed", source="clawhub")
        leaky.profiles["worker"].skills = ["local::a1", "local::b2"]

        text = _everything(await _export(apply=True))

        assert "ai.myrm.skill" in text
        assert "clawhub" in text

    @pytest.mark.asyncio
    async def test_a_rejected_build_is_reported_as_a_package_error(self, leaky: ExportWorld) -> None:
        failure = PluginPackageResult(success=False, zip_content=None, filename=None, error="verification failed")
        with patch("app.services.plugins.export_service.build_plugin_bundle", return_value=failure):
            with pytest.raises(ExportError) as caught:
                await _export(apply=True)

        assert caught.value.code is ExportErrorCode.PACKAGE_REJECTED
        assert "verification failed" in str(caught.value)

    @pytest.mark.asyncio
    async def test_refusals_of_the_closure_surface_unchanged(self, world: ExportWorld) -> None:
        with pytest.raises(ExportError) as caught:
            await _export("missing")

        assert caught.value.code is ExportErrorCode.EXPERT_NOT_FOUND
