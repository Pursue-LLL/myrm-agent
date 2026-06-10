"""Pipeline Template API integration tests.

Tests the full HTTP stack (pipeline_router + pipeline_instantiator + KanbanService)
against a real SQLite database. No mocks for pipeline logic — exercises the full
path from HTTP request to task creation.

Covers:
- GET /kanban/pipelines — list available pipeline templates
- GET /kanban/pipelines/{skill_id} — get template detail + repeat_for field exposure
- POST /kanban/boards/{board_id}/pipeline/instantiate — create task graph
- repeat_for fan-out: all 3 templates (multi-topic / content-distribution / competitive-analysis)
- repeat_for error paths: empty selection (400) / exceeds MAX_REPEAT (400)
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.kanban.pipeline_router import pipeline_router
from app.api.kanban.router import router as kanban_router
from app.services.kanban import KanbanService


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """Ensure each test gets a fresh KanbanService singleton."""
    KanbanService._instance = None
    yield
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_agent_validation() -> None:  # type: ignore[misc]
    """Bypass agent_id validation for tests."""
    with patch.object(
        KanbanService,
        "_validate_agent_id",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(kanban_router, prefix="/api/v1")
    app.include_router(pipeline_router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c


def _create_board(client: TestClient, name: str = "Pipeline Test Board") -> dict[str, object]:
    resp = client.post("/api/v1/kanban/boards", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


class TestListPipelines:
    """GET /kanban/pipelines"""

    def test_returns_pipeline_templates(self, client: TestClient) -> None:
        resp = client.get("/api/v1/kanban/pipelines")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 3
        skill_ids = [item["skill_id"] for item in data["items"]]
        assert "video-production-pipeline" in skill_ids
        assert "code-review-pipeline" in skill_ids
        assert "data-analysis-pipeline" in skill_ids

    def test_excludes_non_pipeline_skills(self, client: TestClient) -> None:
        resp = client.get("/api/v1/kanban/pipelines")
        data = resp.json()
        skill_ids = [item["skill_id"] for item in data["items"]]
        assert "data-analysis" not in skill_ids
        assert "multi-agent-orchestration" not in skill_ids

    def test_template_fields(self, client: TestClient) -> None:
        resp = client.get("/api/v1/kanban/pipelines")
        data = resp.json()
        video = next(i for i in data["items"] if i["skill_id"] == "video-production-pipeline")
        assert video["category"] == "pipeline"
        assert video["task_count"] == 5
        assert len(video["roles"]) == 5
        assert "researcher" in video["roles"]


class TestGetPipelineDetail:
    """GET /kanban/pipelines/{skill_id}"""

    def test_returns_detail(self, client: TestClient) -> None:
        resp = client.get("/api/v1/kanban/pipelines/video-production-pipeline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["skill_id"] == "video-production-pipeline"
        assert len(data["discovery_questions"]) == 2
        assert len(data["role_templates"]) == 5
        assert len(data["task_graph_seed"]) == 5

    def test_discovery_questions_structure(self, client: TestClient) -> None:
        resp = client.get("/api/v1/kanban/pipelines/video-production-pipeline")
        data = resp.json()
        group = data["discovery_questions"][0]
        assert group["group"] == "basic_info"
        assert group["group_label"] == "基础信息"
        assert len(group["questions"]) == 3
        q = group["questions"][0]
        assert q["id"] == "video_type"
        assert q["type"] == "select"
        assert len(q["options"]) > 0

    def test_task_graph_seed_dag(self, client: TestClient) -> None:
        resp = client.get("/api/v1/kanban/pipelines/video-production-pipeline")
        data = resp.json()
        seeds = data["task_graph_seed"]
        assert seeds[0]["parents"] == []
        assert seeds[1]["parents"] == []
        assert seeds[2]["parents"] == [0]
        assert seeds[3]["parents"] == [1, 2]
        assert seeds[4]["parents"] == [3]

    def test_repeat_for_exposed_in_detail(self, client: TestClient) -> None:
        resp = client.get("/api/v1/kanban/pipelines/multi-topic-research-pipeline")
        assert resp.status_code == 200
        seeds = resp.json()["task_graph_seed"]
        assert seeds[0]["repeat_for"] == "topics"
        assert seeds[1]["repeat_for"] is None

    def test_not_found(self, client: TestClient) -> None:
        resp = client.get("/api/v1/kanban/pipelines/nonexistent")
        assert resp.status_code == 404

    def test_non_pipeline_returns_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/kanban/pipelines/data-analysis")
        assert resp.status_code == 404


class TestInstantiatePipeline:
    """POST /kanban/boards/{board_id}/pipeline/instantiate"""

    def test_creates_task_graph(self, client: TestClient) -> None:
        board = _create_board(client)
        board_id = board["board_id"]

        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/pipeline/instantiate",
            json={
                "skill_id": "video-production-pipeline",
                "answers": {
                    "video_type": "产品宣传",
                    "duration": "30s",
                    "platform": "抖音/TikTok",
                    "topic": "MyRM AI 助手",
                    "style": "简约现代",
                },
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["task_ids"]) == 5
        assert len(data["edges"]) == 4  # T0→T2, T1→T3, T2→T3, T3→T4

    def test_creates_task_graph_with_variant(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.kanban.pipeline_spec_io import PipelineSpec, TaskGraphVariant, TaskSeed

        # Mock get_pipeline_skill to return a spec with variants
        def mock_get_pipeline_skill(skill_id: str) -> PipelineSpec:
            return PipelineSpec(
                skill_id="mock-skill",
                name="Mock",
                description="Mock",
                category="pipeline",
                tags=[],
                discovery_questions=[],
                role_templates=[],
                task_graph_seed=[
                    TaskSeed("Default", "", "a", []),
                ],
                task_graph_variants=[
                    TaskGraphVariant(
                        id="quick",
                        label="Quick",
                        description="",
                        seeds=[
                            TaskSeed("Quick 1", "", "a", []),
                            TaskSeed("Quick 2", "", "b", [0]),
                        ],
                    )
                ],
            )

        monkeypatch.setattr("app.services.kanban.pipeline_instantiator.get_pipeline_skill", mock_get_pipeline_skill)

        board = _create_board(client)
        board_id = board["board_id"]

        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/pipeline/instantiate",
            json={
                "skill_id": "mock-skill",
                "answers": {},
                "variant_id": "quick",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["task_ids"]) == 2
        assert len(data["edges"]) == 1

    def test_instantiate_invalid_variant_id_returns_400(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.kanban.pipeline_spec_io import PipelineSpec, TaskGraphVariant, TaskSeed

        def mock_get_pipeline_skill(skill_id: str) -> PipelineSpec:
            return PipelineSpec(
                skill_id="mock-skill",
                name="Mock",
                description="Mock",
                category="pipeline",
                tags=[],
                discovery_questions=[],
                role_templates=[],
                task_graph_seed=[TaskSeed("Default", "", "a", [])],
                task_graph_variants=[
                    TaskGraphVariant(id="quick", label="Quick", description="", seeds=[TaskSeed("Quick", "", "a", [])])
                ],
            )

        monkeypatch.setattr("app.services.kanban.pipeline_instantiator.get_pipeline_skill", mock_get_pipeline_skill)

        board = _create_board(client)
        board_id = board["board_id"]

        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/pipeline/instantiate",
            json={
                "skill_id": "mock-skill",
                "answers": {},
                "variant_id": "invalid-id",
            },
        )
        assert resp.status_code == 400
        assert "Invalid variant_id: invalid-id" in resp.json()["detail"]

    def test_instantiate_empty_graph_returns_400(self, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.kanban.pipeline_spec_io import PipelineSpec

        def mock_get_pipeline_skill(skill_id: str) -> PipelineSpec:
            return PipelineSpec(
                skill_id="mock-empty",
                name="Mock Empty",
                description="Mock",
                category="pipeline",
                tags=[],
                discovery_questions=[],
                role_templates=[],
                task_graph_seed=[],
                task_graph_variants=[],
            )

        monkeypatch.setattr("app.services.kanban.pipeline_instantiator.get_pipeline_skill", mock_get_pipeline_skill)

        board = _create_board(client)
        board_id = board["board_id"]

        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/pipeline/instantiate",
            json={
                "skill_id": "mock-empty",
                "answers": {},
            },
        )
        assert resp.status_code == 400
        assert "No tasks defined" in resp.json()["detail"]

    def test_task_titles_substituted(self, client: TestClient) -> None:
        board = _create_board(client)
        board_id = board["board_id"]

        client.post(
            f"/api/v1/kanban/boards/{board_id}/pipeline/instantiate",
            json={
                "skill_id": "video-production-pipeline",
                "answers": {"video_type": "教程", "duration": "1min", "topic": "Python"},
            },
        )

        tasks_resp = client.get(f"/api/v1/kanban/boards/{board_id}/tasks")
        tasks = tasks_resp.json()["items"]
        titles = [t["title"] for t in tasks]
        assert any("教程" in title for title in titles)

    def test_dag_dependencies_created(self, client: TestClient) -> None:
        board = _create_board(client)
        board_id = board["board_id"]

        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/pipeline/instantiate",
            json={"skill_id": "code-review-pipeline", "answers": {"target": "app/"}},
        )
        data = resp.json()
        task_ids = data["task_ids"]
        assert len(task_ids) == 4

        edges_resp = client.get(f"/api/v1/kanban/boards/{board_id}/edges")
        edges = edges_resp.json()["items"]
        assert len(edges) >= 3

    def test_board_not_found(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/kanban/boards/nonexistent/pipeline/instantiate",
            json={"skill_id": "video-production-pipeline", "answers": {}},
        )
        assert resp.status_code == 400

    def test_skill_not_found(self, client: TestClient) -> None:
        board = _create_board(client)
        board_id = board["board_id"]
        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/pipeline/instantiate",
            json={"skill_id": "nonexistent-pipeline", "answers": {}},
        )
        assert resp.status_code == 400

    def test_empty_answers_still_creates(self, client: TestClient) -> None:
        board = _create_board(client)
        board_id = board["board_id"]
        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/pipeline/instantiate",
            json={"skill_id": "data-analysis-pipeline", "answers": {}},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["task_ids"]) == 4

    def test_repeat_for_fan_out_creates_correct_tasks(self, client: TestClient) -> None:
        board = _create_board(client)
        board_id = board["board_id"]

        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/pipeline/instantiate",
            json={
                "skill_id": "multi-topic-research-pipeline",
                "answers": {
                    "topics": "AI,Quantum,Bio",
                    "research_depth": "Standard analysis (3-5 pages)",
                    "perspective": "Technical / Engineering",
                    "output_format": "Markdown Report",
                },
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["task_ids"]) == 4  # 3 research + 1 synthesis
        assert len(data["edges"]) == 3  # each research → synthesis

        tasks_resp = client.get(f"/api/v1/kanban/boards/{board_id}/tasks")
        titles = [t["title"] for t in tasks_resp.json()["items"]]
        assert any("AI" in t for t in titles)
        assert any("Quantum" in t for t in titles)
        assert any("Bio" in t for t in titles)

    def test_repeat_for_content_distribution(self, client: TestClient) -> None:
        board = _create_board(client)
        board_id = board["board_id"]

        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/pipeline/instantiate",
            json={
                "skill_id": "content-distribution-pipeline",
                "answers": {
                    "source_content": "Product launch blog post",
                    "content_type": "Blog article",
                    "platforms": "Twitter,LinkedIn",
                    "tone": "Professional",
                },
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["task_ids"]) == 3  # 2 adapt + 1 check
        assert len(data["edges"]) == 2

        tasks_resp = client.get(f"/api/v1/kanban/boards/{board_id}/tasks")
        titles = [t["title"] for t in tasks_resp.json()["items"]]
        assert any("Twitter" in t for t in titles)
        assert any("LinkedIn" in t for t in titles)

    def test_repeat_for_competitive_analysis(self, client: TestClient) -> None:
        board = _create_board(client)
        board_id = board["board_id"]

        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/pipeline/instantiate",
            json={
                "skill_id": "competitive-analysis-pipeline",
                "answers": {
                    "our_product": "MyRM",
                    "competitors": "CompA,CompB,CompC",
                    "industry": "AI Agent",
                    "dimensions": "Feature,Price",
                    "output_format": "Matrix",
                },
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["task_ids"]) == 4  # 3 analyze + 1 synthesize
        assert len(data["edges"]) == 3

        tasks_resp = client.get(f"/api/v1/kanban/boards/{board_id}/tasks")
        titles = [t["title"] for t in tasks_resp.json()["items"]]
        assert any("CompA" in t for t in titles)
        assert any("CompB" in t for t in titles)
        assert any("CompC" in t for t in titles)

    def test_repeat_for_empty_selection_returns_400(self, client: TestClient) -> None:
        board = _create_board(client)
        board_id = board["board_id"]

        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/pipeline/instantiate",
            json={
                "skill_id": "multi-topic-research-pipeline",
                "answers": {"topics": ""},
            },
        )
        assert resp.status_code == 400
        assert "at least one selection" in resp.json()["detail"]

    def test_repeat_for_exceeds_max_returns_400(self, client: TestClient) -> None:
        board = _create_board(client)
        board_id = board["board_id"]

        items = ",".join(f"topic-{i}" for i in range(25))
        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/pipeline/instantiate",
            json={
                "skill_id": "multi-topic-research-pipeline",
                "answers": {"topics": items},
            },
        )
        assert resp.status_code == 400
        assert "exceeds limit" in resp.json()["detail"]
