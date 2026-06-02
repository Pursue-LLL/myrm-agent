"""搜索服务 - Web搜索工具"""

import logging
from typing import cast

from myrm_agent_harness.toolkits.web_search.common import SearchResult
from myrm_agent_harness.toolkits.web_search.engine import SearchServiceConfig, WebSearchTools

logger = logging.getLogger(__name__)


async def search_web_service(
    query: str,
    search_service_cfg: SearchServiceConfig,
    num_results: int = 5,
) -> list[SearchResult]:
    """使用指定的搜索服务执行Web搜索

    Args:
        query: 用户查询
        search_service_cfg: 搜索服务配置（包含服务类型、API密钥等）
        num_results: 返回结果数量

    Returns:
        搜索结果列表
    """
    web_search_tool = WebSearchTools(search_service_cfg)
    return cast(
        list[SearchResult],
        await web_search_tool.search(
            query=query,
            num_results=num_results,
        ),
    )
