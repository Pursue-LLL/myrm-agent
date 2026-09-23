import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security.auth.identity import LOCAL_USER_ID, ResolvedIdentity
from app.services.wiki.writeback.schemas import (
    UsageLedgerItem,
    UsageLedgerRecord,
    WritebackApplyRequest,
    WritebackDecisionItem,
)
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


def test_writeback_service_review_slip_negative_filtering(temp_vault):
    service = WikiWritebackService(workspace_root=temp_vault)

    with patch("app.services.wiki.writeback.service.resolve_wiki_vault_path", return_value=temp_vault):
        candidates = [
            {
                "topic": "演示环境配置",
                "content": "使用内网测试节点部署命令：curl http://192.168.1.50:8080/test",
                "rationale": "测试部署",
            },
            {
                "topic": "单向数据流三步同步法",
                "content": "在分布式网络抖动时，按阶段一双写、阶段二回放校验、阶段三平滑切读三步执行。",
                "rationale": "高可用平滑迁移标准步骤",
                "recommended_layer": "methods",
            },
            {
                "topic": "会议演讲逐字稿",
                "content": "请大家看大屏幕，欢迎大家来到直播间，下面我宣读开场白主持词...",
                "rationale": "主持人串场",
            },
        ]

        batch = service.generate_review_slip(
            agent_id="agent_test",
            task_id="task_02",
            task_title="高可用方案交付",
            candidate_insights=candidates,
        )

        # 演示环境IP与演讲逐字稿应被负向规则拦截
        assert batch.excluded_matches_count == 2
        assert len(batch.questions) == 1
        q = batch.questions[0]
        assert q.topic == "单向数据流三步同步法"
        assert len(q.options) == 3


def test_writeback_service_apply_decisions(temp_vault):
    service = WikiWritebackService(workspace_root=temp_vault)

    with patch("app.services.wiki.writeback.service.resolve_wiki_vault_path", return_value=temp_vault):
        request = WritebackApplyRequest(
            task_id="task_03",
            decisions=[
                WritebackDecisionItem(
                    question_id="q_1",
                    selected_option_id="opt_method",
                    target_layer="methods",
                    candidate_title="双写平滑迁移四部曲",
                    candidate_content="详细的四步平滑迁移实操步骤...",
                ),
                WritebackDecisionItem(
                    question_id="q_2",
                    selected_option_id="opt_claim",
                    target_layer="claims",
                    candidate_title="架构师对未来数据库的研判",
                    candidate_content="未来分布式数据库可能会被内存网格替代。",
                ),
                WritebackDecisionItem(
                    question_id="q_3",
                    selected_option_id="opt_deliverable_only",
                    target_layer="deliverables_only",
                    candidate_title="特定合同违约金条款",
                    candidate_content="违约赔偿金为100万元。",
                ),
            ],
        )

        result = service.apply_writeback("agent_test", request)
        assert result.committed_count == 2
        assert result.discarded_count == 1
        assert len(result.created_paths) == 2

        # 验证物理文件生成与 frontmatter 及 evidence 凭据链
        method_file = temp_vault / "wiki" / "concepts" / "methods" / "双写平滑迁移四部曲.md"
        assert method_file.is_file()
        content = method_file.read_text(encoding="utf-8")
        assert "type: method" in content
        assert "publish_status: draft" in content
        assert "evidence:" in content
        assert "negative_exclusion_verified: true" in content

        # 验证层级条目查询
        items = service.list_layer_items("agent_test", "methods")
        assert len(items) == 1
        assert items[0].title == "双写平滑迁移四部曲"
        assert items[0].publish_status == "draft"



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

        # 2. POST /writeback/review-slips
        slip_res = client.post(
            "/api/v1/wiki/writeback/review-slips?agent_id=default",
            json={
                "task_id": "task_api_01",
                "task_title": "API测试任务",
                "candidate_insights": [
                    {
                        "topic": "安全测试方法论",
                        "content": "使用静态分析与动态模糊测试相结合",
                        "rationale": "提升系统健壮性",
                    }
                ],
            },
        )
        assert slip_res.status_code == 200
        batch = slip_res.json()
        assert len(batch["questions"]) == 1

        # 3. GET /writeback/layers-stats
        stats_res = client.get("/api/v1/wiki/writeback/layers-stats?agent_id=default")
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert "deliverables_count" in stats
        assert "methods_count" in stats

        # 4. GET /writeback/layer-items
        items_res = client.get("/api/v1/wiki/writeback/layer-items?layer=methods&agent_id=default")
        assert items_res.status_code == 200
        assert isinstance(items_res.json(), list)
