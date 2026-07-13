"""GitHub API helpers for security dashboard PR/SBOM supplements."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from app.schemas.security.dashboard import DependabotPR, SecurityMetrics

logger = logging.getLogger(__name__)

_DEFAULT_REPO = "Pursue-LLL/myrm-agent"
_GITHUB_TIMEOUT = 10.0
_MAX_REPOS = 3


def repos_from_cp_payload(
    payload: dict[str, object],
    *,
    fallback_default: bool = True,
) -> list[str]:
    """Derive repository slugs from control-plane dashboard JSON."""
    seen: set[str] = set()
    ordered: list[str] = []

    def add(repo: object) -> None:
        if not isinstance(repo, str):
            return
        slug = repo.strip()
        if slug and slug not in seen:
            seen.add(slug)
            ordered.append(slug)

    top_repos = payload.get("top_vulnerable_repos")
    if isinstance(top_repos, list):
        for item in top_repos:
            if isinstance(item, dict):
                add(item.get("repo"))

    recent = payload.get("recent_alerts")
    if isinstance(recent, list):
        for item in recent:
            if isinstance(item, dict):
                add(item.get("repo"))

    if not ordered and fallback_default:
        ordered.append(_DEFAULT_REPO)
    return ordered[:_MAX_REPOS]


def resolve_github_repos(
    payload: dict[str, object],
    *,
    monitored_repos: list[str] | None = None,
    fallback_default: bool = True,
) -> list[str]:
    """Prefer CP-derived repos, then user-configured repos, then optional default."""
    from_cp = repos_from_cp_payload(payload, fallback_default=False)
    if from_cp:
        return from_cp[:_MAX_REPOS]

    if monitored_repos:
        cleaned = [repo.strip() for repo in monitored_repos if repo.strip()]
        if cleaned:
            return cleaned[:_MAX_REPOS]

    if fallback_default:
        return [_DEFAULT_REPO]
    return []


def _parse_github_obj(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items()}


def _github_user(pr: dict[str, object]) -> dict[str, object]:
    return _parse_github_obj(pr.get("user"))


def _github_labels(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        return []
    return [{str(k): v for k, v in item.items()} for item in raw if isinstance(item, dict)]


def _github_int(value: object, *, default: int = 0) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return default


def _github_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00") if value.endswith("Z") else value
        return datetime.fromisoformat(normalized)
    return datetime.fromtimestamp(0, tz=UTC)


async def _fetch_github_list(endpoint: str, token: str | None) -> list[dict[str, object]]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.github.com{endpoint}",
            headers=headers,
            timeout=_GITHUB_TIMEOUT,
        )
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, list):
        return []
    return [{str(k): v for k, v in item.items()} for item in body if isinstance(item, dict)]


async def _fetch_github_mapping(endpoint: str, token: str | None) -> dict[str, object]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.github.com{endpoint}",
            headers=headers,
            timeout=_GITHUB_TIMEOUT,
        )
        response.raise_for_status()
        return _parse_github_obj(response.json())


async def check_sbom_available(repo: str, token: str | None) -> bool:
    try:
        artifacts = await _fetch_github_mapping(
            f"/repos/{repo}/actions/artifacts?name=sbom",
            token,
        )
        total = artifacts.get("total_count", 0)
        return isinstance(total, int) and total > 0
    except Exception as exc:
        logger.warning("SBOM check failed for %s: %s", repo, exc)
        return False


async def fetch_dependabot_prs_for_repo(repo: str, token: str | None) -> list[DependabotPR]:
    prs_data = await _fetch_github_list(f"/repos/{repo}/pulls?state=open", token)
    dependabot = [pr for pr in prs_data if _github_user(pr).get("login") == "dependabot[bot]"]
    return [
        DependabotPR(
            number=_github_int(pr.get("number")),
            title=str(pr.get("title", "")),
            state=str(pr.get("state", "")),
            labels=[str(lbl.get("name", "")) for lbl in _github_labels(pr.get("labels", []))],
            html_url=str(pr.get("html_url", "")),
            created_at=_github_datetime(pr.get("created_at")),
        )
        for pr in dependabot
    ]


def _count_security_prs(prs: list[DependabotPR]) -> int:
    return sum(1 for pr in prs if any("security" in label.lower() for label in pr.labels))


async def fetch_github_supplement(
    repos: list[str],
    token: str | None,
) -> tuple[list[DependabotPR], SecurityMetrics, bool]:
    """Aggregate Dependabot PR metrics across up to `_MAX_REPOS` repositories."""
    all_prs: list[DependabotPR] = []
    sbom_available = False

    for repo in repos:
        try:
            repo_prs = await fetch_dependabot_prs_for_repo(repo, token)
            all_prs.extend(repo_prs)
            if not sbom_available:
                sbom_available = await check_sbom_available(repo, token)
        except httpx.HTTPStatusError as exc:
            logger.warning("GitHub PR fetch failed for %s: %s", repo, exc.response.status_code)
        except Exception as exc:
            logger.warning("GitHub PR fetch failed for %s: %s", repo, exc)

    all_prs.sort(key=lambda pr: pr.created_at, reverse=True)
    recent = all_prs[:10]
    security_prs = _count_security_prs(all_prs)

    metrics = SecurityMetrics(
        total_alerts=0,
        critical_count=0,
        high_count=0,
        medium_count=0,
        low_count=0,
        open_dependabot_prs=len(all_prs),
        security_prs=security_prs,
    )
    return recent, metrics, sbom_available
