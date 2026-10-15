"""Tests for FAL.ai provider id normalization, key resolution and the prebuilt Flux 3 skill."""

from __future__ import annotations

from pathlib import Path


def test_flux3_prompting_guide_skill_valid() -> None:
    """Verify prebuilt skill flux3-prompting-guide exists and is well-formed."""
    from myrm_agent_harness.backends.skills._utils import parse_skill_frontmatter

    server_root = Path(__file__).resolve().parents[3]
    skill_file = server_root / "assets" / "prebuilt_skills" / "flux3-prompting-guide" / "SKILL.md"
    assert skill_file.is_file(), f"Skill file missing at {skill_file}"

    data = parse_skill_frontmatter(skill_file.read_text(encoding="utf-8"), "flux3-prompting-guide")
    assert data.name == "flux3-prompting-guide"
    assert data.version == "1.0.0"
    assert "video_tool" in data.allowed_tools


def test_fal_provider_id_normalization() -> None:
    from app.services.agent.params.providers import normalize_storage_provider_id

    assert normalize_storage_provider_id("fal") == "fal"
    assert normalize_storage_provider_id("fal_ai") == "fal"
    assert normalize_storage_provider_id("fal-ai") == "fal"


def test_find_fal_provider_api_key() -> None:
    from app.services.agent.params import _find_provider_api_key

    providers_dict = {
        "providers": [
            {
                "id": "fal",
                "isEnabled": True,
                "apiKeys": [
                    {
                        "key": "fal-secret-key-123",
                        "isActive": True,
                    }
                ],
            }
        ]
    }
    assert _find_provider_api_key(providers_dict, "fal") == "fal-secret-key-123"
    assert _find_provider_api_key(providers_dict, "fal_ai") == "fal-secret-key-123"
    assert _find_provider_api_key(providers_dict, "fal-ai") == "fal-secret-key-123"
