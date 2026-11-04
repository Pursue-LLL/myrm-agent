import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.security.auth.identity import LOCAL_USER_ID, ResolvedIdentity
from app.services.wiki.layers.service import WikiLayersService


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


def test_layers_routes_e2e(client: TestClient, temp_vault: Path):
    service = WikiLayersService(workspace_root=temp_vault)
    with (
        patch("app.api.wiki.layers_routes.resolve_wiki_vault_path", return_value=temp_vault),
        patch("app.services.wiki.layers.service.resolve_wiki_vault_path", return_value=temp_vault),
    ):
        methods_dir = service._get_structure("default").methods_dir
        methods_dir.mkdir(parents=True, exist_ok=True)
        (methods_dir / "retry-policy.md").write_text("---\ntitle: Retry policy\n---\n\nBackoff with jitter.", encoding="utf-8")

        stats_res = client.get("/api/v1/wiki/layers/stats?agent_id=default")
        assert stats_res.status_code == 200
        stats = stats_res.json()
        assert stats["methods_count"] == 1
        assert stats["deliverables_count"] == 0

        items_res = client.get("/api/v1/wiki/layers/items?layer=methods&agent_id=default")
        assert items_res.status_code == 200
        items = items_res.json()
        assert [item["title"] for item in items] == ["Retry policy"]
        assert items[0]["content_snippet"] == "Backoff with jitter."


def test_list_layer_items_reads_frontmatter_and_skips_non_markdown(temp_vault):
    service = WikiLayersService(workspace_root=temp_vault)

    with patch("app.services.wiki.layers.service.resolve_wiki_vault_path", return_value=temp_vault):
        deliverables_dir = service._get_structure("agent_test").deliverables_dir
        deliverables_dir.mkdir(parents=True, exist_ok=True)
        (deliverables_dir / "cost_report.md").write_text(
            '---\ntitle: "成本控制核心法则"\npublish_status: draft\n---\n\n详细的方法论内容...',
            encoding="utf-8",
        )
        (deliverables_dir / "plain-note.md").write_text("no frontmatter here", encoding="utf-8")
        (deliverables_dir / "export.json").write_text('{"title": "not a document"}', encoding="utf-8")
        (deliverables_dir / ".hidden.md").write_text("hidden", encoding="utf-8")

        items = {item.slug: item for item in service.list_layer_items(agent_id="agent_test", layer_key="deliverables")}

        assert set(items) == {"cost_report", "plain-note"}
        assert items["cost_report"].title == "成本控制核心法则"
        assert items["cost_report"].publish_status == "draft"
        assert items["cost_report"].content_snippet == "详细的方法论内容..."
        assert items["plain-note"].title == "Plain Note"
        assert items["plain-note"].publish_status == "published"
