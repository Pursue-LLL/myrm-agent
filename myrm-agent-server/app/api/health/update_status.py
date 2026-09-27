"""Stack update truth for the Settings → System → About Stack Update Panel.

Single endpoint behind the panel's Web leg — version compare is the primary
behind signal (production images ship without .git, so rev-list cannot be
primary); git rev-list/log is a best-effort enrichment for source checkouts.
Every unreachable source degrades to an honest unknown instead of a guess.

- GET /api/v1/health/update-status (public, same as the rest of /health)
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])

_RELEASE_REPO_ENV = "MYRM_GITHUB_RELEASE_REPO"
_DEFAULT_RELEASE_REPO = "Pursue-LLL/myrm-agent"
_LATEST_TTL_SEC = 3600.0
_FETCH_TIMEOUT_SEC = 8.0
_GIT_TIMEOUT_SEC = 10.0
_CHANGELOG_CAP = 50

_latest_cache: dict[str, object] = {"fetched_at": 0.0, "payload": None}
_last_prebuilt: dict[str, object] = {"synced_count": None, "at": None}


def note_prebuilt_sync_result(synced_count: int) -> None:
    """Stash the startup prebuilt-sync outcome for the panel summary."""
    _last_prebuilt["synced_count"] = synced_count
    _last_prebuilt["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def split_changelog(body: str) -> dict[str, object]:
    """Split a release body into FIXED / OTHER groups.

    Section headers win; otherwise fix-like bullets go to fixed. Anything
    unparseable degrades to grouped=False with the raw body truncated.
    """
    fixed: list[str] = []
    other: list[str] = []
    section: str | None = None
    for raw_line in (body or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lowered = line.lower().lstrip("#").strip()
        if lowered in {"fixed", "fixes", "bug fixes", "bugfixes"}:
            section = "fixed"
            continue
        if lowered in {
            "other",
            "other improvements",
            "improvements",
            "features",
            "new features",
            "changes",
        }:
            section = "other"
            continue
        if not line.startswith(("-", "*")):
            section = None
            continue
        item = line[1:].strip()
        if not item:
            continue
        if section == "fixed":
            fixed.append(item)
        elif section == "other":
            other.append(item)
        elif item.lower().startswith(("fix", "bug", "repair", " hotfix")):
            fixed.append(item)
        else:
            other.append(item)
    if not fixed and not other:
        return {"fixed": [], "other": [], "grouped": False, "raw": (body or "")[:2000]}
    return {
        "fixed": fixed[:_CHANGELOG_CAP],
        "other": other[:_CHANGELOG_CAP],
        "grouped": True,
        "raw": "",
    }


def _parse_version_tuple(version: str) -> tuple[int, ...] | None:
    cleaned = (version or "").strip().lstrip("vV")
    if not cleaned:
        return None
    parts: list[int] = []
    for chunk in cleaned.split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits and chunk != "0":
            return None
        parts.append(int(digits or 0))
    return tuple(parts) if parts else None


def is_stale(current: str, latest: str | None) -> bool | None:
    """True when latest is strictly newer; None when incomparable."""
    if not latest:
        return None
    current_tuple = _parse_version_tuple(current)
    latest_tuple = _parse_version_tuple(latest)
    if current_tuple is None or latest_tuple is None:
        return None
    length = max(len(current_tuple), len(latest_tuple))
    current_padded = current_tuple + (0,) * (length - len(current_tuple))
    latest_padded = latest_tuple + (0,) * (length - len(latest_tuple))
    return latest_padded > current_padded


async def _fetch_latest_release(repo: str) -> dict[str, object]:
    """Fetch the latest GitHub release; network failure → honest unknown."""
    import httpx

    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        async with httpx.AsyncClient(timeout=_FETCH_TIMEOUT_SEC) as client:
            response = await client.get(url, headers={"Accept": "application/vnd.github+json"})
            response.raise_for_status()
            data = response.json()
    except Exception as exc:
        logger.warning("Latest-release fetch failed: %s", exc)
        return {"release": None, "error": type(exc).__name__}
    if not isinstance(data, dict):
        return {"release": None, "error": "unexpected_shape"}
    tag = data.get("tag_name")
    release = {
        "version": tag if isinstance(tag, str) else None,
        "published_at": data.get("published_at"),
        "url": data.get("html_url"),
        "body": data.get("body") if isinstance(data.get("body"), str) else "",
    }
    return {"release": release, "error": None}


async def _git_behind() -> dict[str, object] | None:
    """Best-effort rev-list enrichment; None when git/repo is unavailable."""
    if shutil.which("git") is None:
        return None

    def _collect() -> dict[str, object] | None:
        directory = Path.cwd().resolve()
        repo_root: Path | None = None
        for parent in (directory, *directory.parents):
            if (parent / ".git").exists():
                repo_root = parent
                break
        if repo_root is None:
            return None
        try:
            count_out = subprocess.run(
                ["git", "rev-list", "--count", "HEAD..@{u}"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SEC,
            )
            log_out = subprocess.run(
                ["git", "log", "--oneline", "-5", "HEAD..@{u}"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_SEC,
            )
        except Exception:
            return None
        if count_out.returncode != 0:
            return None
        try:
            behind_count = int(count_out.stdout.strip())
        except ValueError:
            return None
        log_lines = [line for line in log_out.stdout.splitlines() if line.strip()][:5]
        return {"behind_count": behind_count, "log": log_lines}

    try:
        return await asyncio.to_thread(_collect)
    except Exception:
        return None


@router.get("/update-status")
async def update_status() -> dict[str, object]:
    """Stack update truth: versions, latest release, changelog groups, prebuilt."""
    from myrm_agent_harness import __version__ as harness_version

    from app.config.settings import settings

    server_version = settings.app_version
    repo = os.getenv(_RELEASE_REPO_ENV, _DEFAULT_RELEASE_REPO)

    now = time.monotonic()
    cached_at = float(_latest_cache.get("fetched_at") or 0.0)
    cached_payload = _latest_cache.get("payload")
    if cached_payload is not None and now - cached_at < _LATEST_TTL_SEC:
        latest_result = cached_payload
    else:
        latest_result = await _fetch_latest_release(repo)
        _latest_cache["fetched_at"] = now
        _latest_cache["payload"] = latest_result

    release = latest_result.get("release")
    release_dict = release if isinstance(release, dict) else None
    latest_version = release_dict.get("version") if release_dict else None
    body = release_dict.get("body") if release_dict else ""
    changelog = split_changelog(body if isinstance(body, str) else "")

    stale = is_stale(server_version, latest_version if isinstance(latest_version, str) else None)
    git = await _git_behind()

    return {
        "server_version": server_version,
        "harness_version": harness_version,
        "repo": repo,
        "latest": release_dict,
        "fetch_error": latest_result.get("error"),
        "stale": stale,
        "changelog": changelog,
        "git": git,
        "prebuilt": dict(_last_prebuilt),
        "cloud": {"state": "unknown", "reason": "no control-plane version contract yet"},
    }
