from __future__ import annotations

import asyncio

import pytest
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


def test_split_changelog_detects_security_cve() -> None:
    body = "## Fixed\n- Fix CVE-2026-1234 remote sandbox escape vulnerability\n- Regular fix"
    grouped = split_changelog(body)
    assert grouped["grouped"] is True
    assert grouped["is_security"] is True

    normal_body = "## Fixed\n- Fix UI color layout"
    normal_grouped = split_changelog(normal_body)
    assert normal_grouped["is_security"] is False


def test_update_status_endpoint_force_bypasses_cache(monkeypatch) -> None:
    fetch_count = 0

    async def fake_latest(repo: str) -> dict[str, object]:
        nonlocal fetch_count
        fetch_count += 1
        return {
            "release": {
                "version": f"v0.2.{fetch_count}",
                "published_at": "2026-09-01T00:00:00Z",
                "url": "https://example.invalid/r",
                "body": "## Fixed\n- Security patch CVE-2026-9999",
            },
            "error": None,
        }

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

    # First fetch: populates cache
    res1 = client.get("/health/update-status")
    assert res1.status_code == 200
    assert res1.json()["latest"]["version"] == "v0.2.1"
    assert res1.json()["changelog"]["is_security"] is True
    assert fetch_count == 1

    # Second fetch without force: hits cache
    res2 = client.get("/health/update-status")
    assert res2.status_code == 200
    assert res2.json()["latest"]["version"] == "v0.2.1"
    assert fetch_count == 1

    # Third fetch with force=true: bypasses cache and increments fetch_count
    res3 = client.get("/health/update-status?force=true")
    assert res3.status_code == 200
    assert res3.json()["latest"]["version"] == "v0.2.2"
    assert fetch_count == 2


@pytest.mark.asyncio
async def test_update_status_singleflight_concurrent_probes(monkeypatch) -> None:
    fetch_count = 0

    async def slow_fetch(repo: str) -> dict[str, object]:
        nonlocal fetch_count
        fetch_count += 1
        await asyncio.sleep(0.05)
        return {
            "release": {"version": f"v0.3.{fetch_count}", "body": "fix"},
            "error": None,
        }

    async def fake_git() -> dict[str, object] | None:
        return None

    monkeypatch.setattr(update_status, "_fetch_latest_release", slow_fetch)
    monkeypatch.setattr(update_status, "_git_behind", fake_git)
    monkeypatch.setattr(update_status, "_latest_cache", {"fetched_at": 0.0, "payload": None})
    monkeypatch.setattr(update_status, "_force_in_flight", None)

    r1, r2 = await asyncio.gather(
        update_status.update_status(force=True),
        update_status.update_status(force=True),
    )
    assert isinstance(r1["latest"], dict)
    assert isinstance(r2["latest"], dict)
    assert r1["latest"]["version"] == "v0.3.1"
    assert r2["latest"]["version"] == "v0.3.1"
    assert fetch_count == 1
