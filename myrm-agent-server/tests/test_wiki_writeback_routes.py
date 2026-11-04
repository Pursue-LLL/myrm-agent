import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security.auth.identity import LOCAL_USER_ID, ResolvedIdentity
from app.services.wiki.writeback.schemas import UsageLedgerItem, UsageLedgerRecord
from app.services.wiki.writeback.service import WikiWritebackService


@pytest.fixture(autouse=True)
def _bypass_auth():
    fake_identity = ResolvedIdentity(
        user_id=LOCAL_USER_ID,
        auth_source="loopback",
        client_ip="127.0.0.1",
        loopback=True,
        private_net=False,
        local_trusted=True,
        admission_path="loopback",
        trust_zone="local_trusted",
    )
    with patch("app.middleware.auth.resolve_identity", return_value=fake_identity):
        yield


@pytest.fixture
def client():
    from tests.support.minimal_app import build_minimal_app

    app = build_minimal_app(preset="wiki")
    return TestClient(app)


@pytest.fixture
def temp_vault():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_writeback_service_ledger_persistence(temp_vault):
    service = WikiWritebackService(workspace_root=temp_vault)

    with patch("app.services.wiki.writeback.service.resolve_wiki_vault_path", return_value=temp_vault):
        record = UsageLedgerRecord(
            task_id="task_bank_migration_01",
            title="银行核心系统迁移方案编制",
            executed_at="2026-09-23T12:00:00Z",
            items=[
                UsageLedgerItem(
                    concept_or_path="concepts/distributed-consensus.md",
                    contribution_type="referenced",
                    detail="引用了分布式强一致性保障章节",
                ),
                UsageLedgerItem(
                    concept_or_path="concepts/old-oracle-dump.md",
                    contribution_type="omitted",
                    detail="客户未采用 Oracle，跳过该概念",
                ),
            ],
            deliverable_paths=["deliverables/bank_migration_final.pdf"],
        )

        saved_path = service.record_usage_ledger("agent_test", record)
        assert saved_path.is_file()
        assert "task_bank_migration_01.json" in saved_path.name
        content = saved_path.read_text(encoding="utf-8")
        assert "银行核心系统迁移方案编制" in content
        assert "concepts/distributed-consensus.md" in content


def test_writeback_routes_e2e(client: TestClient, temp_vault: Path):
    with patch("app.services.wiki.vault.resolve_wiki_vault_path", return_value=temp_vault):
        # 1. POST /writeback/ledger
        ledger_res = client.post(
            "/api/v1/wiki/writeback/ledger?agent_id=default",
            json={
                "task_id": "task_api_01",
                "title": "API测试任务",
                "executed_at": "2026-09-23T12:00:00Z",
                "items": [
                    {
                        "concept_or_path": "concepts/test.md",
                        "contribution_type": "referenced",
                        "detail": "API测试引用",
                    }
                ],
                "deliverable_paths": ["deliverables/test.pdf"],
            },
        )
        assert ledger_res.status_code == 200
        assert ledger_res.json()["status"] == "ok"

        # 2. GET /writeback/layers-stats
        stats_res = client.get("/api/v1/wiki/writeback/layers-stats?agent_id=default")
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert "deliverables_count" in stats
        assert "methods_count" in stats

        # 3. GET /writeback/layer-items
        items_res = client.get("/api/v1/wiki/writeback/layer-items?layer=methods&agent_id=default")
        assert items_res.status_code == 200
        assert isinstance(items_res.json(), list)


def test_list_layer_items_deliverables_and_provenance(temp_vault):
    import json

    service = WikiWritebackService(workspace_root=temp_vault)

    with patch("app.services.wiki.writeback.service.resolve_wiki_vault_path", return_value=temp_vault):
        # 1. 模拟在 deliverables/ledgers/ 下生成任务审计 JSON 台账
        ledgers_dir = temp_vault / "deliverables" / "ledgers"
        ledgers_dir.mkdir(parents=True, exist_ok=True)
        ledger_file = ledgers_dir / "task_audit_9999.json"
        ledger_data = {
            "task_id": "task_audit_9999",
            "title": "大模型成本分析执行台账",
            "executed_at": "2026-09-23T20:00:00Z",
            "items": [
                {"concept_or_path": "methods/cost.md", "contribution_type": "referenced", "detail": "成本优化"}
            ],
            "deliverable_paths": ["deliverables/report.md"],
        }
        ledger_file.write_text(json.dumps(ledger_data), encoding="utf-8")

        # 2. 模拟在 methods/ 下生成带 source_task_id 的 markdown
        methods_dir = service._get_structure("agent_test").methods_dir
        methods_dir.mkdir(parents=True, exist_ok=True)
        method_file = methods_dir / "provenance_test.md"
        method_content = (
            "---\n"
            "title: \"成本控制核心法则\"\n"
            "publish_status: draft\n"
            "source_task_id: \"task_audit_9999\"\n"
            "---\n\n"
            "详细的方法论内容..."
        )
        method_file.write_text(method_content, encoding="utf-8")

        # 验证 deliverables 能够穿透扫描并解析 ledgers/*.json
        deliv_items = service.list_layer_items(agent_id="agent_test", layer_key="deliverables")
        assert len(deliv_items) >= 1
        ledger_item = next((item for item in deliv_items if item.file_type == "json"), None)
        assert ledger_item is not None
        assert ledger_item.source_task_id == "task_audit_9999"
        assert ledger_item.title == "大模型成本分析执行台账"
        assert "task_audit_9999" in ledger_item.content_snippet

        # 验证 methods 能够提取 frontmatter 中的 source_task_id
        method_items = service.list_layer_items(agent_id="agent_test", layer_key="methods")
        target_method = next((item for item in method_items if item.slug == "provenance_test"), None)
        assert target_method is not None
        assert target_method.source_task_id == "task_audit_9999"
        assert target_method.file_type == "markdown"
        assert target_method.publish_status == "draft"


