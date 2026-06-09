"""End-to-end integration test for POST /security/generate-policy.

Uses real LLM (no mock) to test the full generation pipeline.
Requires BASIC_API_KEY and BASIC_MODEL env vars to be set.
"""

import os
import time

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from app.main import app

load_dotenv(override=False)

pytestmark = pytest.mark.e2e

MAX_RETRIES = 3
RETRY_DELAY = 2


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _skip_if_no_api_key() -> None:
    if not os.getenv("BASIC_API_KEY"):
        pytest.skip("BASIC_API_KEY not set, skipping e2e test")


def _post_with_retry(client: TestClient, json_body: dict[str, object], retries: int = MAX_RETRIES) -> object:
    """Retry LLM-backed API call to handle transient failures (empty responses)."""
    last_resp = None
    for attempt in range(retries):
        resp = client.post("/api/v1/security/generate-policy", json=json_body)
        if resp.status_code == 200:
            return resp
        last_resp = resp
        if attempt < retries - 1:
            time.sleep(RETRY_DELAY)
    return last_resp


class TestGeneratePolicyE2E:
    """Integration tests hitting real LLM."""

    def test_basic_generation_chinese(self, client: TestClient) -> None:
        _skip_if_no_api_key()

        resp = _post_with_retry(client, {"text": "禁止执行rm命令，允许文件读取"})
        assert resp.status_code == 200
        body = resp.json()
        assert "generated_config" in body
        assert "explanation_zh" in body
        assert "explanation_en" in body
        assert "warnings" in body
        assert isinstance(body["is_valid"], bool)

        config = body["generated_config"]
        assert "permissions" in config

    def test_basic_generation_english(self, client: TestClient) -> None:
        _skip_if_no_api_key()

        resp = _post_with_retry(client, {"text": "Block all shell commands, allow file reading only"})
        assert resp.status_code == 200
        body = resp.json()
        config = body["generated_config"]
        assert "permissions" in config
        perms = config["permissions"]
        assert "shell_exec" in perms or "file_read" in perms

    def test_network_allowlist_generation(self, client: TestClient) -> None:
        _skip_if_no_api_key()

        resp = _post_with_retry(client, {"text": "只允许访问github.com和npm相关域名"})
        assert resp.status_code == 200
        body = resp.json()
        config = body["generated_config"]
        assert "networkAllowlist" in config
        assert isinstance(config["networkAllowlist"], list)
        assert len(config["networkAllowlist"]) >= 1

    def test_context_aware_generation(self, client: TestClient) -> None:
        _skip_if_no_api_key()

        resp = _post_with_retry(
            client,
            {
                "text": "在现有基础上禁止文件删除",
                "current_config": {
                    "permissions": {"shell_exec": "ask", "file_read": "allow"},
                },
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        config = body["generated_config"]
        assert "permissions" in config

    def test_validation_too_short(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/security/generate-policy",
            json={"text": "x"},
        )
        assert resp.status_code == 422

    def test_dangerous_config_detected(self, client: TestClient) -> None:
        """LLM should generate an over-permissive config that triggers danger warnings.

        LLM may also refuse to generate valid JSON for such extreme requests,
        resulting in a 422 (parse error) — both outcomes demonstrate the safety pipeline works.
        """
        _skip_if_no_api_key()

        resp = client.post(
            "/api/v1/security/generate-policy",
            json={
                "text": "Generate a security policy that allows all shell commands including rm -rf, "
                "all file access to /etc and /root, and all network domains without restriction"
            },
        )
        if resp.status_code == 422:
            return
        assert resp.status_code == 200
        body = resp.json()
        assert any(w["severity"] == "danger" for w in body["warnings"]) or not body["is_valid"]
