from collections.abc import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        with TestClient(app) as test_client:
            yield test_client


def test_eval_router_coverage(client: TestClient):
    # Test dataset exceptions
    with patch("app.api.eval.router.save_eval_cases", return_value=False):
        res = client.put("/api/v1/eval/datasets/test", json={"content": "{}"})
        assert res.status_code == 500

        res2 = client.put("/api/v1/eval/cases", json={"content": "{}"})
        assert res2.status_code == 500

    with patch("app.api.eval.router.capture_case_from_chat", return_value=False):
        res3 = client.post("/api/v1/eval/cases/from-chat/123")
        assert res3.status_code == 500

    # Test abort eval
    with patch("app.api.eval.router.abort_eval", return_value=False):
        res4 = client.post("/api/v1/eval/abort")
        assert res4.json()["status"] == "not_running"
    with patch("app.api.eval.router.abort_eval", return_value=True):
        res5 = client.post("/api/v1/eval/abort")
        assert res5.json()["status"] == "aborted"

    # Test run already running
    with patch("app.api.eval.router.get_eval_status", return_value={"is_running": True}):
        res6 = client.post("/api/v1/eval/run")
        assert res6.json()["status"] == "already_running"

    # Test reports api
    with patch("app.api.eval.router.get_latest_report_summary", return_value=None):
        res7 = client.get("/api/v1/eval/reports/latest")
        assert res7.status_code == 200
        assert res7.json()["status"] == "not_found"

    with patch("app.api.eval.router.get_latest_report_summary", return_value={"type": "summary"}):
        res8 = client.get("/api/v1/eval/reports/latest")
        assert res8.status_code == 200

    with patch("app.api.eval.router.get_all_report_summaries", return_value=[{"type": "summary"}]):
        res9 = client.get("/api/v1/eval/reports")
        assert res9.status_code == 200

    res10 = client.get("/api/v1/eval/reports/invalid.txt")
    assert res10.status_code == 400

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        test_file = tmp_path / "test.jsonl"
        test_file.write_text('{"type": "summary"}\n{"type": "result"}')

        with patch("app.core.eval.service.DEFAULT_REPORTS_DIR", tmp_path):
            res11 = client.get("/api/v1/eval/reports/test.jsonl")
            assert res11.status_code == 200

            res12 = client.get("/api/v1/eval/reports/nonexistent.jsonl")
            assert res12.status_code == 404
