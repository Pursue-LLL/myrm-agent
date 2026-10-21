"""Widget KV Storage API unit tests.

Tests the REST API endpoints for widget localStorage persistence bridge:
- GET /{namespace}/all — retrieve all key-value pairs
- GET /{namespace}/{key} — retrieve single value
- PUT /{namespace}/batch — batch upsert with quota enforcement
- DELETE /{namespace}/all — clear namespace
- DELETE /{namespace}/{key} — delete single key
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("widget_storage")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


PREFIX = "/api/v1/widget-storage"


class TestBatchWrite:
    """PUT /{namespace}/batch tests."""

    def test_batch_write_single_entry(self, client: TestClient) -> None:
        resp = client.put(
            f"{PREFIX}/test-ns/batch",
            json={"chat_id": "chat-001", "entries": [{"key": "counter", "value": "42"}]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["written"] == 1

    def test_batch_write_multiple_entries(self, client: TestClient) -> None:
        entries = [{"key": f"k{i}", "value": f"v{i}"} for i in range(5)]
        resp = client.put(
            f"{PREFIX}/ns-multi/batch",
            json={"chat_id": "chat-002", "entries": entries},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["written"] == 5

    def test_batch_write_empty_entries(self, client: TestClient) -> None:
        resp = client.put(
            f"{PREFIX}/ns-empty/batch",
            json={"chat_id": "chat-003", "entries": []},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["written"] == 0

    def test_batch_write_upsert_updates_existing(self, client: TestClient) -> None:
        ns = "ns-upsert"
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-004", "entries": [{"key": "x", "value": "old"}]},
        )
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-004", "entries": [{"key": "x", "value": "new"}]},
        )
        resp = client.get(f"{PREFIX}/{ns}/x")
        assert resp.status_code == 200
        assert resp.json()["data"]["value"] == "new"

    def test_batch_write_quota_exceeded(self, client: TestClient) -> None:
        ns = "ns-quota"
        entries = [{"key": f"k{i}", "value": "v"} for i in range(101)]
        resp = client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-005", "entries": entries},
        )
        # Pydantic max_length=100 on entries list triggers 422 before reaching endpoint logic
        assert resp.status_code == 422

    def test_batch_write_value_too_large(self, client: TestClient) -> None:
        huge_value = "x" * 70_000
        resp = client.put(
            f"{PREFIX}/ns-big/batch",
            json={"chat_id": "chat-006", "entries": [{"key": "big", "value": huge_value}]},
        )
        # Pydantic max_length=65536 on value field triggers 422
        assert resp.status_code == 422

    def test_incremental_quota_exceeded(self, client: TestClient) -> None:
        """Quota enforced when existing + new keys > 100."""
        ns = "ns-incr-quota"
        # Write 99 keys
        entries = [{"key": f"k{i}", "value": "v"} for i in range(99)]
        resp = client.put(f"{PREFIX}/{ns}/batch", json={"chat_id": "c", "entries": entries})
        assert resp.status_code == 200
        # Adding 2 more new keys (total would be 101) should fail at runtime check
        new_entries = [{"key": "k99", "value": "v"}, {"key": "k100", "value": "v"}]
        resp = client.put(f"{PREFIX}/{ns}/batch", json={"chat_id": "c", "entries": new_entries})
        assert resp.status_code == 413


class TestGetAll:
    """GET /{namespace}/all tests."""

    def test_get_all_empty_namespace(self, client: TestClient) -> None:
        resp = client.get(f"{PREFIX}/empty-ns/all")
        assert resp.status_code == 200
        assert resp.json()["data"] == {}

    def test_get_all_returns_written_data(self, client: TestClient) -> None:
        ns = "ns-getall"
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={
                "chat_id": "chat-010",
                "entries": [
                    {"key": "a", "value": "1"},
                    {"key": "b", "value": "2"},
                ],
            },
        )
        resp = client.get(f"{PREFIX}/{ns}/all")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data == {"a": "1", "b": "2"}


class TestGetSingle:
    """GET /{namespace}/{key} tests."""

    def test_get_existing_key(self, client: TestClient) -> None:
        ns = "ns-single"
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-020", "entries": [{"key": "hello", "value": "world"}]},
        )
        resp = client.get(f"{PREFIX}/{ns}/hello")
        assert resp.status_code == 200
        assert resp.json()["data"]["value"] == "world"

    def test_get_nonexistent_key_returns_404(self, client: TestClient) -> None:
        resp = client.get(f"{PREFIX}/ns-404/nonexistent")
        assert resp.status_code == 404


class TestDeleteKey:
    """DELETE /{namespace}/{key} tests."""

    def test_delete_existing_key(self, client: TestClient) -> None:
        ns = "ns-del"
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-030", "entries": [{"key": "temp", "value": "data"}]},
        )
        resp = client.delete(f"{PREFIX}/{ns}/temp")
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted"] == "temp"

        verify = client.get(f"{PREFIX}/{ns}/temp")
        assert verify.status_code == 404

    def test_delete_nonexistent_key_returns_404(self, client: TestClient) -> None:
        resp = client.delete(f"{PREFIX}/ns-del2/ghost")
        assert resp.status_code == 404


class TestClearNamespace:
    """DELETE /{namespace}/all tests."""

    def test_clear_removes_all_keys(self, client: TestClient) -> None:
        ns = "ns-clear"
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={
                "chat_id": "chat-040",
                "entries": [
                    {"key": "a", "value": "1"},
                    {"key": "b", "value": "2"},
                    {"key": "c", "value": "3"},
                ],
            },
        )
        resp = client.delete(f"{PREFIX}/{ns}/all")
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted_count"] == 3

        verify = client.get(f"{PREFIX}/{ns}/all")
        assert verify.json()["data"] == {}

    def test_clear_empty_namespace(self, client: TestClient) -> None:
        resp = client.delete(f"{PREFIX}/ns-clear-empty/all")
        assert resp.status_code == 200
        assert resp.json()["data"]["deleted_count"] == 0


class TestNamespaceIsolation:
    """Verify different namespaces are fully isolated."""

    def test_namespaces_do_not_leak(self, client: TestClient) -> None:
        client.put(
            f"{PREFIX}/ns-a/batch",
            json={"chat_id": "chat-050", "entries": [{"key": "x", "value": "in-a"}]},
        )
        client.put(
            f"{PREFIX}/ns-b/batch",
            json={"chat_id": "chat-050", "entries": [{"key": "x", "value": "in-b"}]},
        )

        resp_a = client.get(f"{PREFIX}/ns-a/all")
        resp_b = client.get(f"{PREFIX}/ns-b/all")

        assert resp_a.json()["data"] == {"x": "in-a"}
        assert resp_b.json()["data"] == {"x": "in-b"}


class TestEdgeCases:
    """Edge cases and special characters."""

    def test_key_with_special_characters(self, client: TestClient) -> None:
        ns = "ns-special"
        special_key = "user:settings/theme"
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-060", "entries": [{"key": special_key, "value": "dark"}]},
        )
        resp = client.get(f"{PREFIX}/{ns}/all")
        assert resp.status_code == 200
        assert resp.json()["data"][special_key] == "dark"

    def test_value_with_json_content(self, client: TestClient) -> None:
        ns = "ns-json"
        json_value = '{"count":42,"items":["a","b"]}'
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-061", "entries": [{"key": "state", "value": json_value}]},
        )
        resp = client.get(f"{PREFIX}/{ns}/state")
        assert resp.status_code == 200
        assert resp.json()["data"]["value"] == json_value

    def test_value_with_html_and_script_tags(self, client: TestClient) -> None:
        """Ensure XSS-like content is stored/retrieved without corruption."""
        ns = "ns-xss"
        xss_value = '</script><script>alert("xss")</script>'
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-062", "entries": [{"key": "html", "value": xss_value}]},
        )
        resp = client.get(f"{PREFIX}/{ns}/html")
        assert resp.status_code == 200
        assert resp.json()["data"]["value"] == xss_value

    def test_unicode_value(self, client: TestClient) -> None:
        ns = "ns-unicode"
        unicode_value = "日本語テスト 🎉 émojis"
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-063", "entries": [{"key": "lang", "value": unicode_value}]},
        )
        resp = client.get(f"{PREFIX}/{ns}/lang")
        assert resp.status_code == 200
        assert resp.json()["data"]["value"] == unicode_value

    def test_empty_string_value(self, client: TestClient) -> None:
        ns = "ns-empty-val"
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-064", "entries": [{"key": "empty", "value": ""}]},
        )
        resp = client.get(f"{PREFIX}/{ns}/empty")
        assert resp.status_code == 200
        assert resp.json()["data"]["value"] == ""

    def test_delete_then_rewrite_same_key(self, client: TestClient) -> None:
        ns = "ns-rewrite"
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-065", "entries": [{"key": "k", "value": "v1"}]},
        )
        client.delete(f"{PREFIX}/{ns}/k")
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-065", "entries": [{"key": "k", "value": "v2"}]},
        )
        resp = client.get(f"{PREFIX}/{ns}/k")
        assert resp.status_code == 200
        assert resp.json()["data"]["value"] == "v2"

    def test_clear_then_write(self, client: TestClient) -> None:
        ns = "ns-clearwrite"
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-066", "entries": [{"key": "a", "value": "1"}]},
        )
        client.delete(f"{PREFIX}/{ns}/all")
        client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-066", "entries": [{"key": "b", "value": "2"}]},
        )
        resp = client.get(f"{PREFIX}/{ns}/all")
        assert resp.json()["data"] == {"b": "2"}

    def test_max_key_length_boundary(self, client: TestClient) -> None:
        """Key at exactly max_length=256 should succeed."""
        ns = "ns-maxkey"
        long_key = "k" * 256
        resp = client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-067", "entries": [{"key": long_key, "value": "ok"}]},
        )
        assert resp.status_code == 200

    def test_key_exceeds_max_length(self, client: TestClient) -> None:
        """Key exceeding max_length=256 should be rejected by Pydantic."""
        ns = "ns-longkey"
        too_long_key = "k" * 257
        resp = client.put(
            f"{PREFIX}/{ns}/batch",
            json={"chat_id": "chat-068", "entries": [{"key": too_long_key, "value": "x"}]},
        )
        assert resp.status_code == 422
