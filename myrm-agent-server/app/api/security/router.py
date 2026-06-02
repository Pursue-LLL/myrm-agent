"""
Security Dashboard API

提供安全态势的聚合视图，包括：
- Code scanning alerts统计
- Dependabot PR状态
- SBOM下载链接
"""

import logging
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config.settings import settings as _settings

logger = logging.getLogger(__name__)

# 从环境变量获取配置，支持多个repo用逗号分隔
GITHUB_TOKEN = _settings.services.github_token.get_secret_value()
DEFAULT_REPO = "yululiu/AI-open-perplexity"

router = APIRouter(prefix="/security", tags=["security"])


class SecurityAlert(BaseModel):
    """安全告警模型"""

    id: int
    severity: str  # critical, high, medium, low
    rule_id: str
    rule_description: str
    state: str  # open, fixed, dismissed
    created_at: datetime
    html_url: str


class DependabotPR(BaseModel):
    """Dependabot PR模型"""

    number: int
    title: str
    state: str  # open, closed
    labels: list[str]
    html_url: str
    created_at: datetime


class SecurityMetrics(BaseModel):
    """安全指标"""

    total_alerts: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    open_dependabot_prs: int
    security_prs: int


class SecurityDashboard(BaseModel):
    """安全仪表盘数据"""

    metrics: SecurityMetrics
    recent_alerts: list[SecurityAlert]
    recent_prs: list[DependabotPR]
    sbom_available: bool


def _parse_github_obj(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        return {}
    return {str(k): v for k, v in raw.items()}


def _github_rule(alert: dict[str, object]) -> dict[str, object]:
    return _parse_github_obj(alert.get("rule"))


def _github_user(pr: dict[str, object]) -> dict[str, object]:
    return _parse_github_obj(pr.get("user"))


def _github_labels(raw: object) -> list[dict[str, object]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, object]] = []
    for item in raw:
        if isinstance(item, dict):
            out.append({str(k): v for k, v in item.items()})
    return out


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
    return datetime.utcfromtimestamp(0)


async def _fetch_github_list(endpoint: str, token: str | None = None) -> list[dict[str, object]]:
    """从GitHub API获取JSON数组响应"""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.github.com{endpoint}", headers=headers, timeout=10.0)
        response.raise_for_status()
        body = response.json()
    if not isinstance(body, list):
        return []
    out: list[dict[str, object]] = []
    for item in body:
        if isinstance(item, dict):
            out.append({str(k): v for k, v in item.items()})
    return out


async def _fetch_github_mapping(endpoint: str, token: str | None = None) -> dict[str, object]:
    """从GitHub API获取JSON对象响应"""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient() as client:
        response = await client.get(f"https://api.github.com{endpoint}", headers=headers, timeout=10.0)
        response.raise_for_status()
        return _parse_github_obj(response.json())


async def _check_sbom_availability(repo: str, token: str | None = None) -> bool:
    """检查SBOM artifacts是否存在"""
    try:
        artifacts = await _fetch_github_mapping(f"/repos/{repo}/actions/artifacts?name=sbom", token)
        total = artifacts.get("total_count", 0)
        return isinstance(total, int) and total > 0
    except Exception as e:
        logger.warning(f"Failed to check SBOM availability: {e}")
        return False


@router.get("/dashboard", response_model=SecurityDashboard)
async def get_security_dashboard() -> SecurityDashboard:
    """
    获取安全仪表盘数据

    聚合GitHub Security API数据：
    - Code scanning alerts
    - Dependabot pull requests
    - SBOM artifacts
    """
    try:
        github_token = GITHUB_TOKEN
        repo = DEFAULT_REPO

        # 获取code scanning alerts
        alerts_data = await _fetch_github_list(f"/repos/{repo}/code-scanning/alerts", github_token)

        # 统计各级别告警
        critical_count = sum(
            1
            for a in alerts_data
            if _github_rule(a).get("security_severity_level") == "critical" and a.get("state") == "open"
        )
        high_count = sum(
            1
            for a in alerts_data
            if _github_rule(a).get("security_severity_level") == "high" and a.get("state") == "open"
        )
        medium_count = sum(
            1
            for a in alerts_data
            if _github_rule(a).get("security_severity_level") == "medium" and a.get("state") == "open"
        )
        low_count = sum(
            1
            for a in alerts_data
            if _github_rule(a).get("security_severity_level") == "low" and a.get("state") == "open"
        )

        # 转换为SecurityAlert模型
        recent_alerts = [
            SecurityAlert(
                id=_github_int(alert.get("number")),
                severity=str(_github_rule(alert).get("security_severity_level", "unknown")),
                rule_id=str(_github_rule(alert).get("id", "")),
                rule_description=str(_github_rule(alert).get("description", "")),
                state=str(alert.get("state", "")),
                created_at=_github_datetime(alert.get("created_at")),
                html_url=str(alert.get("html_url", "")),
            )
            for alert in alerts_data[:10]  # 只返回最近10条
        ]

        # 获取Dependabot PRs
        prs_data = await _fetch_github_list(f"/repos/{repo}/pulls?state=open", github_token)

        # 筛选Dependabot PRs
        dependabot_prs = [pr for pr in prs_data if _github_user(pr).get("login") == "dependabot[bot]"]

        security_prs = sum(
            1
            for pr in dependabot_prs
            if any(
                "security" in str(lbl.get("name", "")).lower()
                for lbl in _github_labels(pr.get("labels", []))
            )
        )

        recent_prs = [
            DependabotPR(
                number=_github_int(pr.get("number")),
                title=str(pr.get("title", "")),
                state=str(pr.get("state", "")),
                labels=[str(lbl.get("name", "")) for lbl in _github_labels(pr.get("labels", []))],
                html_url=str(pr.get("html_url", "")),
                created_at=_github_datetime(pr.get("created_at")),
            )
            for pr in dependabot_prs[:10]
        ]

        # 构建响应
        return SecurityDashboard(
            metrics=SecurityMetrics(
                total_alerts=len(alerts_data),
                critical_count=critical_count,
                high_count=high_count,
                medium_count=medium_count,
                low_count=low_count,
                open_dependabot_prs=len(dependabot_prs),
                security_prs=security_prs,
            ),
            recent_alerts=recent_alerts,
            recent_prs=recent_prs,
            sbom_available=await _check_sbom_availability(repo, github_token),
        )

    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"GitHub API error: {e.response.text}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch security data: {str(e)}") from e


@router.get("/alerts", response_model=list[SecurityAlert])
async def get_security_alerts(
    severity: str | None = None, state: str | None = "open"
) -> list[SecurityAlert]:
    """
    获取安全告警列表

    参数：
    - severity: 过滤级别 (critical, high, medium, low)
    - state: 过滤状态 (open, fixed, dismissed)
    """
    try:
        github_token = GITHUB_TOKEN
        repo = DEFAULT_REPO

        alerts_data = await _fetch_github_list(f"/repos/{repo}/code-scanning/alerts?state={state}", github_token)

        # 过滤严重性
        if severity:
            alerts_data = [
                a for a in alerts_data if _github_rule(a).get("security_severity_level") == severity
            ]

        return [
            SecurityAlert(
                id=_github_int(alert.get("number")),
                severity=str(_github_rule(alert).get("security_severity_level", "unknown")),
                rule_id=str(_github_rule(alert).get("id", "")),
                rule_description=str(_github_rule(alert).get("description", "")),
                state=str(alert.get("state", "")),
                created_at=_github_datetime(alert.get("created_at")),
                html_url=str(alert.get("html_url", "")),
            )
            for alert in alerts_data
        ]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"GitHub API error: {e.response.text}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch alerts: {str(e)}") from e


@router.get("/dependabot-prs", response_model=list[DependabotPR])
async def get_dependabot_prs() -> list[DependabotPR]:
    """获取所有Dependabot PRs"""
    try:
        github_token = GITHUB_TOKEN
        repo = DEFAULT_REPO

        prs_data = await _fetch_github_list(f"/repos/{repo}/pulls?state=open", github_token)

        dependabot_prs = [pr for pr in prs_data if _github_user(pr).get("login") == "dependabot[bot]"]

        return [
            DependabotPR(
                number=_github_int(pr.get("number")),
                title=str(pr.get("title", "")),
                state=str(pr.get("state", "")),
                labels=[str(lbl.get("name", "")) for lbl in _github_labels(pr.get("labels", []))],
                html_url=str(pr.get("html_url", "")),
                created_at=_github_datetime(pr.get("created_at")),
            )
            for pr in dependabot_prs
        ]
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"GitHub API error: {e.response.text}") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch Dependabot PRs: {str(e)}") from e
