from collections.abc import Generator
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="eval")
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

    # --- benchmark_mode integration: HTTP → router → background task ---
    with (
        patch("app.api.eval.router.get_eval_status", return_value={"is_running": False}),
        patch("app.api.eval.router.run_eval_suite_background") as mock_bg,
    ):
        res_bm = client.post(
            "/api/v1/eval/run",
            json={"benchmark_mode": True},
        )
        assert res_bm.status_code == 200
        assert res_bm.json()["status"] == "started"
        _, call_kwargs = mock_bg.call_args
        assert call_kwargs["benchmark_mode"] is True
        assert call_kwargs["profile_id"] is None
        assert call_kwargs["dataset_id"] is None

    with (
        patch("app.api.eval.router.get_eval_status", return_value={"is_running": False}),
        patch("app.api.eval.router.run_eval_suite_background") as mock_bg2,
    ):
        res_default = client.post("/api/v1/eval/run", json={})
        assert res_default.json()["status"] == "started"
        _, call_kwargs2 = mock_bg2.call_args
        assert call_kwargs2["benchmark_mode"] is False

    with (
        patch("app.api.eval.router.get_eval_status", return_value={"is_running": False}),
        patch("app.api.eval.router.run_eval_suite_background") as mock_bg3,
    ):
        res_combined = client.post(
            "/api/v1/eval/run",
            json={
                "benchmark_mode": True,
                "profile_id": "agent_abc",
                "dataset_id": "ds_001",
            },
        )
        assert res_combined.json()["status"] == "started"
        _, call_kwargs3 = mock_bg3.call_args
        assert call_kwargs3["benchmark_mode"] is True
        assert call_kwargs3["profile_id"] == "agent_abc"
        assert call_kwargs3["dataset_id"] == "ds_001"

    # Edge: no request body → benchmark_mode defaults to False
    with (
        patch("app.api.eval.router.get_eval_status", return_value={"is_running": False}),
        patch("app.api.eval.router.run_eval_suite_background") as mock_bg4,
    ):
        res_no_body = client.post("/api/v1/eval/run")
        assert res_no_body.status_code == 200
        assert res_no_body.json()["status"] == "started"
        _, call_kwargs4 = mock_bg4.call_args
        assert call_kwargs4["benchmark_mode"] is False

    # Edge: already_running even when benchmark_mode=true
    with patch("app.api.eval.router.get_eval_status", return_value={"is_running": True}):
        res_busy = client.post(
            "/api/v1/eval/run", json={"benchmark_mode": True}
        )
        assert res_busy.json()["status"] == "already_running"

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

        with patch("app.core.eval.reports.DEFAULT_REPORTS_DIR", tmp_path):
            res11 = client.get("/api/v1/eval/reports/test.jsonl")
            assert res11.status_code == 200

            res12 = client.get("/api/v1/eval/reports/nonexistent.jsonl")
            assert res12.status_code == 404

            # Empty report file → 404
            empty_file = tmp_path / "empty.jsonl"
            empty_file.write_text("")
            res_empty = client.get("/api/v1/eval/reports/empty.jsonl")
            assert res_empty.status_code == 404

            # Non-summary first line → error status
            result_file = tmp_path / "result.jsonl"
            result_file.write_text('{"type": "result"}')
            res_result = client.get("/api/v1/eval/reports/result.jsonl")
            assert res_result.status_code == 200
            assert res_result.json()["status"] == "error"

            # Corrupt report → 500
            corrupt_file = tmp_path / "corrupt.jsonl"
            corrupt_file.write_text("{broken json")
            res_corrupt = client.get("/api/v1/eval/reports/corrupt.jsonl")
            assert res_corrupt.status_code == 500


def test_eval_router_remaining_branches(client: TestClient):
    """Cover wb-bench run/download, datasets read, cases read, metrics, stream."""
    from app.core.eval import wb_bench as wb

    # --- wb-bench/run: already running ---
    with patch("app.api.eval.router.get_eval_status", return_value={"is_running": True}):
        res = client.post("/api/v1/eval/wb-bench/run", json={"subset_id": "web"})
        assert res.json()["status"] == "already_running"

    # --- wb-bench/run: started (synchronous state init + background task) ---
    subset_id = next(iter(wb.WB_BENCH_SUBSETS))
    with (
        patch("app.api.eval.router.get_eval_status", return_value={"is_running": False}),
        patch("app.api.eval.router.run_wb_bench_background") as mock_bg,
    ):
        res = client.post(
            "/api/v1/eval/wb-bench/run",
            json={"subset_id": subset_id, "profile_id": "agent_x", "benchmark_mode": True},
        )
        assert res.status_code == 200
        assert res.json()["status"] == "started"
        _, call_kwargs = mock_bg.call_args
        assert call_kwargs["subset_id"] == subset_id
        assert call_kwargs["profile_id"] == "agent_x"
        assert call_kwargs["benchmark_mode"] is True

    # --- wb-bench/download: already running ---
    with patch("app.api.eval.router.get_eval_status", return_value={"is_running": True}):
        res = client.post("/api/v1/eval/wb-bench/download", json={"subset_id": "web"})
        assert res.json()["status"] == "already_running"

    # --- wb-bench/download: started ---
    with (
        patch("app.api.eval.router.get_eval_status", return_value={"is_running": False}),
        patch("app.api.eval.router.run_wb_bench_download_background") as mock_dl,
    ):
        res = client.post(
            "/api/v1/eval/wb-bench/download", json={"subset_id": subset_id}
        )
        assert res.status_code == 200
        assert res.json()["status"] == "started"
        _, call_kwargs = mock_dl.call_args
        assert call_kwargs["subset_id"] == subset_id

    # --- datasets read + cases read ---
    with patch("app.api.eval.router.get_all_datasets", return_value=[]):
        res = client.get("/api/v1/eval/datasets")
        assert res.json()["status"] == "success"

    with patch("app.api.eval.router.get_eval_cases", return_value="x"):
        res = client.get("/api/v1/eval/datasets/custom")
        assert res.json()["content"] == "x"
        res = client.get("/api/v1/eval/cases")
        assert res.json()["content"] == "x"

    # --- dataset write failure → 500 ---
    with patch("app.api.eval.router.save_eval_cases", return_value=False):
        res = client.put("/api/v1/eval/datasets/x", json={"content": "{}"})
        assert res.status_code == 500

    # --- metrics: not found ---
    with patch("app.api.eval.router.get_latest_report_summary", return_value=None):
        res = client.get("/api/v1/eval/internal/metrics/eval")
        assert res.json()["status"] == "not_found"

    # --- metrics: found ---
    with patch(
        "app.api.eval.router.get_latest_report_summary",
        return_value={"total_cases": 10, "pass_rate": 0.8, "pass_count": 8},
    ):
        res = client.get("/api/v1/eval/internal/metrics/eval")
        assert res.json()["status"] == "success"
        assert res.json()["metrics"]["total_cases"] == 10

    # --- status + stream endpoints ---
    with patch("app.api.eval.router.get_eval_status", return_value={"is_running": False}):
        res = client.get("/api/v1/eval/status")
        assert res.json()["is_running"] is False

    with patch("app.api.eval.router.get_eval_status", return_value={"is_running": False}):
        res = client.get("/api/v1/eval/stream")
        assert res.status_code == 200
        assert "text/event-stream" in res.headers["content-type"]
