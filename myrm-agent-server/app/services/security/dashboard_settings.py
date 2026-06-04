"""User-configured GitHub repos for security dashboard PR/SBOM supplement.

[INPUT] app.core.channel_bridge.config_loader::load_user_config_entry (POS: Omni-Config 读取)

[OUTPUT] load_monitored_github_repos: 最多 3 个 owner/repo 列表

[POS] Security Center 用户配置的 GitHub 仓库列表（Omni-Config 读取）。
"""

from __future__ import annotations

from app.core.channel_bridge.config_loader import load_user_config_entry

_CONFIG_KEY = "securityDashboardSettings"
_MAX_REPOS = 3


def _normalize_repo_slug(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    slug = raw.strip()
    if not slug or "/" not in slug:
        return None
    owner, name = slug.split("/", 1)
    if not owner.strip() or not name.strip():
        return None
    return f"{owner.strip()}/{name.strip()}"


def parse_monitored_repos_from_value(raw: dict[str, object] | None) -> list[str]:
    if not raw:
        return []
    repos_raw = raw.get("monitoredGithubRepos")
    if repos_raw is None:
        repos_raw = raw.get("monitored_github_repos")
    if not isinstance(repos_raw, list):
        return []

    seen_lower: set[str] = set()
    ordered: list[str] = []
    for item in repos_raw:
        slug = _normalize_repo_slug(item)
        if not slug:
            continue
        key = slug.lower()
        if key in seen_lower:
            continue
        seen_lower.add(key)
        ordered.append(slug)
        if len(ordered) >= _MAX_REPOS:
            break
    return ordered


async def load_monitored_github_repos() -> list[str]:
    """Load up to three owner/repo slugs from Omni-Config."""
    entry = await load_user_config_entry(_CONFIG_KEY)
    return parse_monitored_repos_from_value(entry)
