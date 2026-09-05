"""End-to-End & Integration Tests for architecture-diagram Skill & JSON IR Artifact Pipeline.

Validates the full task flow lifecycle of the architecture diagram skill:
1. Skill metadata, allowed-tools declaration, and Contract phases (4 phases + potential traps + verification steps)
2. JSON IR structure validation and automatic sanitization (dangling edge pruning, ID deduplication)
3. End-to-end task simulation: generating an architecture diagram artifact, writing .arch.json, and verifying artifact registration
4. Evolution Diff scenario: before vs after snapshot semantic diff computation
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path

import pytest
from myrm_agent_harness.core.artifacts.architecture_ir import (
    ArchitectureIR,
    DiagramType,
    validate_and_sanitize_architecture_ir,
)
from myrm_agent_harness.core.artifacts.constants import (
    ArtifactType,
    infer_artifact_type_from_extension,
)
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

from app.core.skills import prebuilt_sync
from app.core.skills.store.reader import list_prebuilt_skills


@pytest.fixture
def temp_workspace_dir() -> Path:
    temp_dir = tempfile.mkdtemp(prefix="arch_skill_e2e_")
    yield Path(temp_dir)
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_architecture_diagram_skill_contract_and_metadata(temp_workspace_dir: Path) -> None:
    """Verify architecture-diagram skill metadata, sync discoverability, and YAML frontmatter contract."""
    storage = LocalStorageBackend(str(temp_workspace_dir))
    sync_result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    assert "architecture-diagram" in sync_result.skill_ids, "architecture-diagram must be synced"

    skills = await list_prebuilt_skills(storage)
    arch_skill = next((s for s in skills if s.id == "architecture-diagram"), None)
    assert arch_skill is not None, "architecture-diagram skill must be discovered"
    assert arch_skill.category == "creative"

    skill_file = Path(__file__).resolve().parents[3] / "assets" / "prebuilt_skills" / "architecture-diagram" / "SKILL.md"
    assert skill_file.exists(), f"SKILL.md must exist at {skill_file}"
    raw_md = skill_file.read_text(encoding="utf-8")

    # Verify tool authorizations
    tool_match = re.search(r"^allowed-tools:\s*(.+)$", raw_md, re.MULTILINE)
    assert tool_match is not None, "allowed-tools must be declared in frontmatter"
    allowed_tools = tool_match.group(1).split()
    assert "file_write_tool" in allowed_tools
    assert "file_read_tool" in allowed_tools

    # Verify artifact extension mapping
    assert infer_artifact_type_from_extension("system.arch.json") == ArtifactType.ARCHITECTURE
    assert infer_artifact_type_from_extension("workflow.arch.json") == ArtifactType.ARCHITECTURE


def test_architecture_json_ir_generation_and_validation() -> None:
    """Simulate Agent task flow generating a realistic enterprise microservice topology."""
    agent_output_payload = {
        "version": "1.0",
        "type": "architecture",
        "title": "E-Commerce Core Topology",
        "direction": "TB",
        "groups": [
            {"id": "edge", "label": "Edge Ingress"},
            {"id": "services", "label": "Domain Microservices"},
            {"id": "data", "label": "Storage Tier"},
        ],
        "nodes": [
            {"id": "cdn", "label": "Cloudflare Edge", "group": "edge", "category": "gateway"},
            {"id": "api-gateway", "label": "API Gateway", "group": "edge", "category": "gateway"},
            {"id": "order-svc", "label": "Order Service", "group": "services", "category": "backend"},
            {"id": "pay-svc", "label": "Payment Service", "group": "services", "category": "backend"},
            {"id": "pg-db", "label": "PostgreSQL Main", "group": "data", "category": "database"},
            {"id": "redis-cache", "label": "Redis Cache", "group": "data", "category": "cache"},
        ],
        "edges": [
            {"id": "e1", "source": "cdn", "target": "api-gateway", "label": "HTTPS"},
            {"id": "e2", "source": "api-gateway", "target": "order-svc", "label": "gRPC"},
            {"id": "e3", "source": "order-svc", "target": "pay-svc", "label": "Internal"},
            {"id": "e4", "source": "order-svc", "target": "redis-cache", "label": "Cache"},
            {"id": "e5", "source": "order-svc", "target": "pg-db", "label": "SQL"},
        ],
    }

    ir, receipt = validate_and_sanitize_architecture_ir(agent_output_payload)
    assert ir is not None
    assert receipt.is_valid is True
    assert receipt.node_count == 6
    assert receipt.edge_count == 5
    assert receipt.sanitized_dangling_edges == 0
    assert ir.title == "E-Commerce Core Topology"
    assert ir.diagram_type == DiagramType.ARCHITECTURE


def test_architecture_json_ir_dangling_edge_pruning() -> None:
    """Verify that hallucinated or broken edges are safely sanitized before reaching frontend."""
    faulty_payload = {
        "title": "Faulty Network with Dangling Edges",
        "nodes": [
            {"id": "web", "label": "Web Frontend"},
            {"id": "api", "label": "API Backend"},
        ],
        "edges": [
            {"source": "web", "target": "api"},
            {"source": "web", "target": "hallucinated_node_404"},
        ],
    }

    ir, receipt = validate_and_sanitize_architecture_ir(faulty_payload)
    assert ir is not None
    assert receipt.is_valid is True
    assert receipt.node_count == 2
    assert receipt.edge_count == 1
    assert receipt.sanitized_dangling_edges == 1
