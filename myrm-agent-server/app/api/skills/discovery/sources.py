"""自定义技能来源的读取、探测与删除。

[POS]
技能发现域的子模块；由 routes.py 按原顺序挂载。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.api.skills.discovery.schemas import (
    CustomSourceListResponse,
    CustomSourceProbeResponse,
    CustomSourceRequest,
    CustomSourceResponse,
)
from app.core.skills.marketplace.market_service import (
    market_service,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/sources", response_model=CustomSourceListResponse)
async def list_custom_sources() -> CustomSourceListResponse:
    """List all user-configured custom skill sources."""
    from app.core.skills.marketplace.custom_source_config import load_custom_sources

    config = load_custom_sources()
    return CustomSourceListResponse(
        sources=[
            CustomSourceResponse(
                url=s.url,
                source_type=s.source_type,
                label=s.label,
                healthy=s.healthy,
            )
            for s in config.sources
        ]
    )


@router.post("/sources", response_model=CustomSourceProbeResponse)
async def add_custom_source(
    request: CustomSourceRequest,
) -> CustomSourceProbeResponse:
    """Add a custom skill source after probing for reachability."""
    from app.core.skills.marketplace.custom_source_config import (
        add_custom_source as _add_source,
    )

    if request.source_type == "well-known":
        from myrm_agent_harness.agent.skills.market.sources.wellknown import (
            WellKnownSkillSource,
        )

        source = WellKnownSkillSource(request.url)
        reachable, skill_count = await source.probe()

        if not reachable:
            raise HTTPException(status_code=422, detail=f"Cannot reach source: {request.url}")

        try:
            _add_source(request.url, request.source_type, request.label or request.url)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

        market_service._base.register_source(source)
        return CustomSourceProbeResponse(reachable=True, skill_count=skill_count, url=request.url)

    elif request.source_type in ("github-tap", "tap"):
        from myrm_agent_harness.agent.skills.market.taps import (
            TapDirectoryScanner,
            TapSubscription,
        )

        tap_sub = TapSubscription(repo=request.url, label=request.label or request.url)
        scanner = TapDirectoryScanner(tap_sub)
        skills = await scanner.scan_skills(force_refresh=True)

        try:
            _add_source(request.url, "github-tap", request.label or request.url)
        except ValueError as e:
            raise HTTPException(status_code=409, detail=str(e)) from e

        return CustomSourceProbeResponse(reachable=True, skill_count=len(skills), url=request.url)

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported source type: {request.source_type}")


@router.delete("/sources")
async def remove_custom_source_endpoint(
    url: str = Query(..., description="Source URL to remove"),
) -> dict[str, bool]:
    """Remove a custom skill source."""
    from urllib.parse import urlparse

    from app.core.skills.marketplace.custom_source_config import remove_custom_source

    removed = remove_custom_source(url)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Source not found: {url}")

    parsed = urlparse(url.rstrip("/"))
    if parsed.scheme and parsed.netloc:
        source_name = f"well-known:{parsed.scheme}://{parsed.netloc}"
    else:
        source_name = f"github-tap:{url.strip('/')}"
    market_service._base.unregister_source(source_name)

    return {"removed": True}
