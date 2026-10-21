import os

import pytest
from fastapi.testclient import TestClient


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestWikiGraphE2E:
    """Wiki Graph Endpoint E2E Test without mocks (using real models)."""

    def test_get_global_graph(self, client: TestClient):
        """Test getting the full knowledge graph (with limit)."""
        response = client.get("/api/v1/wiki/graph?limit=500")
        assert response.status_code == 200, f"Error: {response.text}"

        data = response.json()
        assert "nodes" in data, "Response should contain nodes"
        assert "edges" in data, "Response should contain edges"
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)
        print(f"\n✅ Global graph retrieved successfully: {len(data['nodes'])} nodes, {len(data['edges'])} edges")

    def test_get_progressive_graph(self, client: TestClient):
        """Test progressive bounded BFS graph fetching."""
        # 1. First get some node to act as center
        initial_res = client.get("/api/v1/wiki/graph?limit=10")
        assert initial_res.status_code == 200

        data = initial_res.json()
        if not data["nodes"]:
            pytest.skip("No nodes in Wiki DB to test progressive loading.")

        center_node = data["nodes"][0]["id"]

        # 2. Query progressive graph
        response = client.get(f"/api/v1/wiki/graph?center_node={center_node}&depth=1&limit=50")
        assert response.status_code == 200

        prog_data = response.json()
        assert "nodes" in prog_data
        assert "edges" in prog_data
        assert len(prog_data["nodes"]) <= 50

        node_ids = [n["id"] for n in prog_data["nodes"]]
        assert center_node in node_ids, "Center node should be included in the progressive response"
        print(f"\n✅ Progressive graph retrieved successfully for center '{center_node}': {len(prog_data['nodes'])} nodes")
