"""Reviewable corpus and package spec of an expert export (business layer).

Everything a recipient can read is reviewed by the same redaction pass: skill files,
workspace templates and the expert's free text. ``corpus_of`` flattens the plan into
that reviewable file map; ``spec_of`` folds the (possibly redacted) map back into the
declarative package description, so what was reviewed is exactly what ships.

[INPUT]
- ._export_models::ExportPlan (POS: the collected dependency closure.)
- myrm_agent_harness.agent.plugins::PluginBundleSpec (POS: declarative package description.)

[OUTPUT]
- corpus_of: plan -> {review path: bytes}.
- spec_of: plan + reviewed files -> PluginBundleSpec.
- PACKAGE_VERSION: version of exported packages.

[POS]
Pure functions, no I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from myrm_agent_harness.agent.plugins import PluginBundleSpec
from myrm_agent_harness.agent.plugins.models import PluginAgent

from ._export_models import ExpertDraft, ExportPlan

__all__ = ["PACKAGE_VERSION", "corpus_of", "spec_of"]

PACKAGE_VERSION = "1.0.0"
_SKILL_ORIGINS_NAMESPACE = "ai.myrm.skill"


def corpus_of(plan: ExportPlan) -> dict[str, bytes]:
    """Every text a recipient will read, keyed by the path shown in the review."""
    corpus: dict[str, bytes] = {}
    for skill in plan.skills:
        for rel, content in skill.files.items():
            corpus[_skill_path(skill.package_name, rel)] = content
    for index, draft in enumerate(plan.experts):
        agent = draft.agent
        corpus[_expert_path(index, agent, "system_prompt.md")] = agent.system_prompt.encode("utf-8")
        corpus[_expert_path(index, agent, "description.txt")] = agent.description.encode("utf-8")
        for number, prompt in enumerate(_suggestion_prompts(agent), start=1):
            corpus[_expert_path(index, agent, f"suggestion-{number}.txt")] = prompt.encode("utf-8")
    for rel, content in plan.workspace_files.items():
        corpus[_workspace_path(rel)] = content
    return corpus


def spec_of(plan: ExportPlan, files: Mapping[str, bytes]) -> PluginBundleSpec:
    """Package description built from the reviewed ``files`` (same keys as ``corpus_of``)."""
    agents = tuple(_reviewed_agent(index, draft, files) for index, draft in enumerate(plan.experts))
    origins = {skill.package_name: skill.origin_source for skill in plan.skills if skill.origin_source}
    return PluginBundleSpec(
        name=plan.plugin_name,
        version=PACKAGE_VERSION,
        description=agents[0].description,
        skills={
            skill.package_name: {rel: files[_skill_path(skill.package_name, rel)] for rel in skill.files} for skill in plan.skills
        },
        mcp_servers=tuple(plan.connectors),
        agents=agents,
        workspace_files={rel: files[_workspace_path(rel)] for rel in plan.workspace_files},
        extensions={_SKILL_ORIGINS_NAMESPACE: {"origins": origins}} if origins else {},
    )


def _reviewed_agent(index: int, draft: ExpertDraft, files: Mapping[str, bytes]) -> PluginAgent:
    agent = draft.agent
    metadata = dict(agent.metadata)
    prompts = _suggestion_prompts(agent)
    if prompts:
        metadata["suggestion_prompts"] = [
            files[_expert_path(index, agent, f"suggestion-{number}.txt")].decode("utf-8") for number in range(1, len(prompts) + 1)
        ]
    return replace(
        agent,
        description=files[_expert_path(index, agent, "description.txt")].decode("utf-8"),
        system_prompt=files[_expert_path(index, agent, "system_prompt.md")].decode("utf-8"),
        metadata=metadata,
    )


def _suggestion_prompts(agent: PluginAgent) -> list[str]:
    prompts = agent.metadata.get("suggestion_prompts")
    return [prompt for prompt in prompts if isinstance(prompt, str)] if isinstance(prompts, list) else []


def _skill_path(package_name: str, rel: str) -> str:
    return f"skills/{package_name}/{rel}"


def _expert_path(index: int, agent: PluginAgent, part: str) -> str:
    # The position keeps paths unique even when two names differ only by a character we replace.
    return f"experts/{index + 1}-{agent.name.replace('/', '-')}/{part}"


def _workspace_path(rel: str) -> str:
    return f"workspace/{rel}"
