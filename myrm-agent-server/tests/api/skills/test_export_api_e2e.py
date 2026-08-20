"""API E2E Tests for Skills Export endpoint (/api/v1/skills/{skill_id}/export).

Validates:
1. POST /api/v1/skills/{id}/export with default export_format='agent_plugin' returns valid Agent Plugins 1.0.0 ZIP.
2. POST /api/v1/skills/{id}/export with export_format='raw_skill' returns valid single-skill ZIP.
3. Redactions during export (apply_redactions=True vs False).
4. evals.json lifecycle (user evals.json is sanitized/ignored, synthetic evals from evolution are properly placed in skills/<name>/evals.json).
5. Non-existent skill returns 404.
6. Preview endpoint consistency with export.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.plugins.parser import AgentPluginParser
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EnvironmentFingerprint,
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.api.skills.packaging import router as packaging_router
from app.core.skills import prebuilt_sync
from app.core.skills.models import SkillType
from app.core.skills.store.service import SkillsService


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI(title="Skill Export Test App")
    test_app.include_router(packaging_router, prefix="/api/v1/skills")
    return test_app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.mark.asyncio
async def test_api_export_skill_as_agent_plugin_and_raw(
    app: FastAPI,
    tmp_path: Path,
) -> None:
    storage = LocalStorageBackend(str(tmp_path))
    svc = SkillsService(storage=storage)

    # Sync prebuilt seeds
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    with patch("app.core.skills.packaging.skills_service", svc), \
         patch("app.core.skills.store.service.skills_service", svc), \
         patch("app.api.skills.packaging.skill_packaging_service._skills_svc", svc):

        client = TestClient(app)

        # 1. 默认或显式 export_format = "agent_plugin"
        res_plugin = client.post(
            "/api/v1/skills/code-review/export",
            json={"apply_redactions": False, "export_format": "agent_plugin"},
        )
        assert res_plugin.status_code == 200
        assert res_plugin.headers["content-type"] == "application/zip"
        assert "code-review" in res_plugin.headers.get("content-disposition", "")

        parser = AgentPluginParser()
        parsed = parser.parse_zip(res_plugin.content)
        assert parsed.meta is not None
        assert parsed.meta.name == "code-review"
        assert len(parsed.skills) == 1
        assert parsed.skills[0].name == "code-review"
        assert len(parsed.diagnostics) == 0

        # 2. 显式 export_format = "raw_skill"
        res_raw = client.post(
            "/api/v1/skills/code-review/export",
            json={"apply_redactions": False, "export_format": "raw_skill"},
        )
        assert res_raw.status_code == 200
        with zipfile.ZipFile(io.BytesIO(res_raw.content), "r") as zf:
            names = zf.namelist()
            assert "code-review/SKILL.md" in names
            assert "code-review/plugin.json" not in names

        # 3. 边界用例：不存在的技能返回 404
        res_404 = client.post(
            "/api/v1/skills/non-existent-skill-xyz/export",
            json={"export_format": "agent_plugin"},
        )
        assert res_404.status_code == 404


@pytest.mark.asyncio
async def test_api_export_skill_redactions_and_evals(
    app: FastAPI,
    tmp_path: Path,
) -> None:
    storage = LocalStorageBackend(str(tmp_path))
    svc = SkillsService(storage=storage)

    # Write a custom skill with sensitive content and user evals.json
    skill_content = """---
name: sensitive-analyzer
description: A skill with secret keys
---
sk-proj-1234567890abcdef1234567890abcdef12345678
"""
    await svc.create_skill(
        name="sensitive-analyzer",
        description="A skill with secret keys",
        skill_type=SkillType.PREBUILT,
        files={
            "SKILL.md": skill_content.encode("utf-8"),
            "evals.json": json.dumps({"user_evals": "should_be_stripped"}).encode("utf-8"),
        },
    )

    record = SkillRecord(
        skill_id="sensitive-analyzer",
        name="sensitive-analyzer",
        description="A skill with secret keys",
        content=skill_content,
        path="skills/prebuilt/sensitive-analyzer/SKILL.md",
        lineage=SkillLineage(
            evolution_type=EvolutionType.DERIVED,
            version=2,
            change_summary="v2",
            created_by="test",
        ),
        eval_cases=[
            {
                "message": "Test secret sk-proj-1234567890abcdef1234567890abcdef12345678",
                "expected_tools": ["code_interpreter"],
            }
        ],
        is_active=True,
        environment=EnvironmentFingerprint(),
    )

    with patch("app.core.skills.packaging.skills_service", svc), \
         patch("app.core.skills.store.service.skills_service", svc), \
         patch("app.api.skills.packaging.skill_packaging_service._skills_svc", svc), \
         patch("app.core.skills.packaging._load_evolution_record", return_value=record):

        client = TestClient(app)

        # 1. Preview checks
        prev_res = client.get("/api/v1/skills/sensitive-analyzer/preview")
        assert prev_res.status_code == 200
        prev_data = prev_res.json()
        assert prev_data["is_safe"] is False
        assert prev_data["eval_cases_count"] == 1
        assert "SKILL.md" in prev_data["redactions"]

        # 2. Export with redactions applied in Agent Plugin format
        export_res = client.post(
            "/api/v1/skills/sensitive-analyzer/export",
            json={"apply_redactions": True, "export_format": "agent_plugin"},
        )
        assert export_res.status_code == 200

        with zipfile.ZipFile(io.BytesIO(export_res.content), "r") as zf:
            namelist = zf.namelist()
            assert "sensitive-analyzer/plugin.json" in namelist
            assert "sensitive-analyzer/skills/sensitive-analyzer/SKILL.md" in namelist
            assert "sensitive-analyzer/skills/sensitive-analyzer/evals.json" in namelist

            skill_md_text = zf.read("sensitive-analyzer/skills/sensitive-analyzer/SKILL.md").decode("utf-8")
            assert "sk-proj-1234567890abcdef1234567890abcdef12345678" not in skill_md_text
            assert "<REDACTED_TOKEN>" in skill_md_text or "[REDACTED:" in skill_md_text

            evals_json = json.loads(zf.read("sensitive-analyzer/skills/sensitive-analyzer/evals.json").decode("utf-8"))
            assert "should_be_stripped" not in json.dumps(evals_json)
            assert "sk-proj-1234567890abcdef1234567890abcdef12345678" not in json.dumps(evals_json)
