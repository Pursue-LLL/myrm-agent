from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.health import update_status
from app.api.health.update_status import is_stale, split_changelog


def test_split_changelog_groups_fixed_and_other() -> None:
    body = "## Fixed\n- Fix crash on boot\n- Repair login\n## Other Improvements\n- Faster search\n- New theme"
    grouped = split_changelog(body)
    assert grouped["grouped"] is True
    assert grouped["fixed"] == ["Fix crash on boot", "Repair login"]
    assert grouped["other"] == ["Faster search", "New theme"]


def test_split_changelog_detects_fix_bullets_without_headers() -> None:
    body = "- Fix typo\n- Add dark mode"
    grouped = split_changelog(body)
    assert grouped["grouped"] is True
    assert grouped["fixed"] == ["Fix typo"]
    assert grouped["other"] == ["Add dark mode"]


def test_split_changelog_empty_body_is_ungrouped() -> None:
    grouped = split_changelog("")
    assert grouped["grouped"] is False
    assert grouped["fixed"] == []
    assert grouped["other"] == []


def test_is_stale_compares_versions() -> None:
    assert is_stale("0.1.0", "0.2.0") is True
    assert is_stale("0.2.0", "0.2.0") is False
    assert is_stale("0.3.0", "0.2.0") is False
    assert is_stale("0.1.0", None) is None
    assert is_stale("dev", "0.2.0") is None


def test_update_status_endpoint_shape(monkeypatch) -> None:
    async def fake_latest(repo: str) -> dict[str, object]:
        assert repo
        return {
            "release": {
                "version": "v0.2.0",
                "published_at": "2026-09-01T00:00:00Z",
                "url": "https://example.invalid/r",
                "body": "## Fixed\n- Fix crash",
            },
            "error": None,
        }

    async def fake_git() -> dict[str, object]:
        return {"behind_count": 3, "log": ["abc123 fix thing"]}

    monkeypatch.setattr(update_status, "_fetch_latest_release", fake_latest)
    monkeypatch.setattr(update_status, "_git_behind", fake_git)
    monkeypatch.setattr(
        update_status, "_latest_cache", {"fetched_at": 0.0, "payload": None}
    )

    app = FastAPI()
    app.include_router(update_status.router, prefix="/health")
    client = TestClient(app)
    response = client.get("/health/update-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["stale"] is True
    assert payload["changelog"]["grouped"] is True
    assert payload["changelog"]["fixed"] == ["Fix crash"]
    assert payload["git"] == {"behind_count": 3, "log": ["abc123 fix thing"]}
    assert payload["cloud"]["state"] == "unknown"
    assert "server_version" in payload
    assert "harness_version" in payload


def test_update_status_endpoint_unknown_when_fetch_fails(monkeypatch) -> None:
    async def fake_latest(repo: str) -> dict[str, object]:
        assert repo
        return {"release": None, "error": "ConnectError"}

    async def fake_git() -> dict[str, object] | None:
        return None

    monkeypatch.setattr(update_status, "_fetch_latest_release", fake_latest)
    monkeypatch.setattr(update_status, "_git_behind", fake_git)
    monkeypatch.setattr(
        update_status, "_latest_cache", {"fetched_at": 0.0, "payload": None}
    )

    app = FastAPI()
    app.include_router(update_status.router, prefix="/health")
    client = TestClient(app)
    response = client.get("/health/update-status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest"] is None
    assert payload["fetch_error"] == "ConnectError"
    assert payload["stale"] is None
    assert payload["git"] is None
