from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from myrm_agent_harness.toolkits.web_search.web_searcher import SearchServiceConfig, SearchServiceType
from pydantic import BaseModel, Field

from app.core.utils.errors import external_service_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse
from app.services.agent.search import search_web_service

router = APIRouter()


class SearchEngineVerifyRequest(BaseModel):
    """搜索引擎验证请求模型"""

    search_service: SearchServiceType = Field(..., description="搜索服务类型（perplexity/tavily/exa_ai/searxng等）")
    num_results: int = Field(default=1, description="返回结果数量")
    api_key: str | None = Field(None, description="API密钥（tavily/exa_ai/perplexity等需要）")
    api_base: str | None = Field(None, description="API基础URL（已弃用，SearxNG URL 从环境变量读取）")
    query: str | None = Field(None, description="测试查询")


class SearchVerifyData(BaseModel):
    """搜索验证数据模型"""

    service_type: str = Field(..., description="搜索服务类型")
    results_count: int = Field(..., description="搜索结果数量")


# 验证搜索引擎配置是否有效
@router.post("/verify", response_model=StandardSuccessResponse)
async def verify_search_engine(request: SearchEngineVerifyRequest) -> JSONResponse:
    """验证搜索引擎配置是否有效

    此API验证用户在前端设置的搜索引擎配置是否有效。

    支持的搜索服务及其所需参数：
    - perplexity: 需要 API Key
    - tavily: 需要 API Key
    - exa_ai: 需要 API Key (注意：从 exa 改为 exa_ai)
    - parallel_ai: 需要 API Key
    - google_pse: 需要 API Key
    - dataforseo: 需要 API Key
    - firecrawl: 需要 API Key
    - searxng: 需要 api_base（WebUI 搜索服务配置，LiteLLM）
    """
    try:
        search_service_value = request.search_service

        # 验证必需参数
        if search_service_value == "searxng":
            if not request.api_base:
                raise validation_error("api_base is required when using searxng service")
        elif not request.api_key:
            raise validation_error(
                f"API key is required when using {search_service_value} service"
            )

        api_base = request.api_base

        results = await search_web_service(
            query=request.query or "北京故宫",
            search_service_cfg=SearchServiceConfig(
                search_service=search_service_value,
                api_key=request.api_key,
                api_base=api_base,
            ),
            num_results=request.num_results,
        )

        # 检查搜索结果是否有效
        if not results or len(results) == 0:
            raise external_service_error("Search service", "Search results are empty")

        data = SearchVerifyData(service_type=search_service_value, results_count=len(results))

        return success_response(data=data.model_dump())
    except HTTPException:
        # 重新抛出 HTTPException（包括 validation_error 等）
        raise
    except Exception as e:
        # 将其他异常转换为外部服务错误
        raise external_service_error("Search service", str(e)) from e
