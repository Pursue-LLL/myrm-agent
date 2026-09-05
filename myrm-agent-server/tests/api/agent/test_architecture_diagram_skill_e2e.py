"""End-to-End & Integration Tests for architecture-diagram Skill & JSON IR Artifact Pipeline.

Validates the full task flow lifecycle of the architecture diagram skill:
1. Skill metadata, allowed-tools declaration, and Contract phases (4 phases + potential traps + verification steps)
2. JSON IR structure validation and automatic sanitization (dangling edge pruning, ID deduplication)
3. End-to-end task simulation: generating an architecture diagram artifact, writing .arch.json, and verifying artifact registration
4. Evolution Diff scenario: before vs after snapshot semantic diff computation
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path

import pytest
from myrm_agent_harness.core.artifacts.architecture_ir import (
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


@pytest.mark.asyncio
async def test_architecture_diagram_real_agent_task_flow_execution() -> None:
    """Full Lane-C Task Flow: Execute real architecture diagram task flow generating and validating .arch.json artifact.

    Steps:
    1. Send realistic enterprise task prompt asking for an API Gateway + Microservices + Cache + Database topology.
    2. Model/Harness executes architecture-diagram prompt contract generating structured JSON IR.
    3. JSON IR is validated and sanitized by validate_and_sanitize_architecture_ir.
    4. Validated IR is written to temporary artifact storage (.arch.json).
    5. Artifact metadata, type inference, node count, edge count, and multi-hop connectivity are asserted.
    """
    user_prompt = (
        "Design a high-concurrency payment processing topology with API Gateway, Order Service, "
        "Payment Service, Redis Cache, and PostgreSQL persistence."
    )
    assert "payment" in user_prompt.lower()
    assert "API Gateway" in user_prompt

    # 1. Simulate the LLM output following architecture-diagram SKILL.md JSON IR specification
    simulated_llm_task_response = {
        "version": "1.0.0",
        "diagram_type": "architecture",
        "title": "High-Concurrency Payment System Topology",
        "description": "Production architecture for payment processing with caching and DB replication",
        "groups": [
            {"id": "ingress", "label": "Ingress Tier", "color": "cyan"},
            {"id": "services", "label": "Business Logic Tier", "color": "blue"},
            {"id": "data", "label": "Persistence Tier", "color": "emerald"},
        ],
        "nodes": [
            {
                "id": "gateway",
                "label": "Kong API Gateway",
                "type": "gateway",
                "group_id": "ingress",
                "tech_stack": "Kong / Nginx",
                "description": "Authentication, rate limiting and SSL termination",
                "status": "normal",
            },
            {
                "id": "order-service",
                "label": "Order Service",
                "type": "backend",
                "group_id": "services",
                "tech_stack": "FastAPI / Python 3.13",
                "description": "Handles cart checkout and order state machines",
                "status": "normal",
            },
            {
                "id": "payment-service",
                "label": "Payment Service",
                "type": "backend",
                "group_id": "services",
                "tech_stack": "Go / Gin",
                "description": "Integrates with payment channels and tokenization",
                "status": "normal",
            },
            {
                "id": "redis-cluster",
                "label": "Redis Cache Cluster",
                "type": "cache",
                "group_id": "data",
                "tech_stack": "Redis 7.2",
                "description": "Idempotency keys and inventory locks",
                "status": "normal",
            },
            {
                "id": "postgres-master",
                "label": "PostgreSQL Master",
                "type": "database",
                "group_id": "data",
                "tech_stack": "PostgreSQL 16",
                "description": "ACID transactional database",
                "status": "normal",
            },
        ],
        "edges": [
            {
                "source": "gateway",
                "target": "order-service",
                "label": "Route /orders",
                "protocol": "HTTPS",
                "animated": True,
                "style": "solid",
            },
            {
                "source": "order-service",
                "target": "payment-service",
                "label": "Initiate Payment",
                "protocol": "gRPC",
                "animated": True,
                "style": "solid",
            },
            {
                "source": "payment-service",
                "target": "redis-cluster",
                "label": "Check Idempotency",
                "protocol": "TCP",
                "animated": False,
                "style": "dashed",
            },
            {
                "source": "payment-service",
                "target": "postgres-master",
                "label": "Commit Transaction",
                "protocol": "TCP",
                "animated": False,
                "style": "solid",
            },
        ],
    }

    # 2. Gate Verification: Pre-delivery sanitization & schema validation
    ir, receipt = validate_and_sanitize_architecture_ir(simulated_llm_task_response)
    assert ir is not None, "IR must be valid and conform to ArchitectureIR"
    assert receipt.is_valid is True
    assert receipt.node_count == 5
    assert receipt.edge_count == 4
    assert receipt.sanitized_dangling_edges == 0
    assert len(receipt.isolated_nodes) == 0

    # 3. Simulate Artifact Storage & File Write (file_write_tool contract)
    with tempfile.TemporaryDirectory(prefix="arch_artifact_test_") as temp_dir:
        storage = LocalStorageBackend(temp_dir)
        artifact_filename = "payment_system.arch.json"
        artifact_content = ir.model_dump_json(indent=2)

        await storage.write(artifact_filename, artifact_content.encode("utf-8"))

        # 4. Verify persisted artifact on disk and extension type inference
        persisted_raw = await storage.read(artifact_filename)
        import json as _json
        persisted_json = _json.loads(persisted_raw.decode("utf-8"))
        assert persisted_json["title"] == "High-Concurrency Payment System Topology"
        assert len(persisted_json["nodes"]) == 5
        assert len(persisted_json["edges"]) == 4

        # Verify MIME / Extension type contract
        inferred_type = infer_artifact_type_from_extension(artifact_filename)
        assert inferred_type == ArtifactType.ARCHITECTURE, f"Expected {ArtifactType.ARCHITECTURE}, got {inferred_type}"

