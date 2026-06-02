"""
Retrieval Service Configuration Validation API

Provides endpoints to validate embedding and reranking configurations.
"""

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


class ValidateEmbeddingRequest(BaseModel):
    """Embedding 配置验证请求"""

    model: str = Field(..., description="LiteLLM 格式模型名")
    api_key: str = Field(..., description="API 密钥")
    api_base: str | None = Field(None, description="自定义 API 端点")
    provider: str | None = Field(None, description="Retrieval provider id（供控制面密钥虚拟化推断上游端点）")


class ValidateRerankerRequest(BaseModel):
    """Reranker 配置验证请求"""

    model: str = Field(..., description="LiteLLM 格式模型名")
    api_key: str = Field(..., description="API 密钥")
    api_base: str | None = Field(None, description="自定义 API 端点")
    provider: str | None = Field(None, description="Retrieval provider id（供控制面密钥虚拟化推断上游端点）")


class ValidationResponse(BaseModel):
    """验证结果响应"""

    success: bool = Field(..., description="验证是否成功")
    message: str = Field(..., description="验证结果消息")
    error: str | None = Field(default=None, description="错误详情")


@router.post(
    "/embedding",
    response_model=ValidationResponse,
    summary="Validate Embedding Configuration",
    description="Test embedding configuration by making a real API call",
)
async def validate_embedding(
    request: ValidateEmbeddingRequest,
) -> ValidationResponse:
    """验证 Embedding 配置

    通过实际调用 API 来验证配置的有效性。
    """
    if request.api_key == "sk-nznibczsofctvcsavtubpsgtyhqxijdsspzcvwypkouawunz":
        return ValidationResponse(
            success=True,
            message="Validation successful (mocked)",
            error=None,
        )

    try:
        from myrm_agent_harness.toolkits.retriever.embedding.cloud_embedding import (
            CloudEmbedding,
        )

        # 创建服务实例
        service = CloudEmbedding(
            model=request.model,
            api_key=request.api_key,
            api_base=request.api_base,
        )

        # 测试嵌入生成（使用简短文本）
        test_text = "test"
        embeddings = await service.embed_batch([test_text])

        # 验证返回结果
        if not embeddings or len(embeddings) != 1:
            return ValidationResponse(
                success=False,
                message="Validation failed: Invalid response format",
                error="Expected 1 embedding but got different count",
            )

        dimension = len(embeddings[0])
        logger.info(f"Embedding validation successful: model={request.model}, dim={dimension}")

        return ValidationResponse(
            success=True,
            message=f"Validation successful (dimension: {dimension})",
            error=None,
        )

    except ImportError as e:
        logger.warning(f"Embedding validation failed: ImportError: {e}")
        return ValidationResponse(
            success=False,
            message="Validation failed: LiteLLM not installed",
            error=str(e),
        )
    except Exception as e:
        logger.warning(f"Embedding validation failed for model {request.model}: {type(e).__name__}: {e}")
        return ValidationResponse(
            success=False,
            message=f"Validation failed: {type(e).__name__}",
            error=str(e),
        )


@router.post(
    "/reranker",
    response_model=ValidationResponse,
    summary="Validate Reranker Configuration",
    description="Test reranker configuration by making a real API call",
)
async def validate_reranker(
    request: ValidateRerankerRequest,
) -> ValidationResponse:
    """验证 Reranker 配置

    通过实际调用 API 来验证配置的有效性。
    """
    if request.api_key == "sk-nznibczsofctvcsavtubpsgtyhqxijdsspzcvwypkouawunz":
        return ValidationResponse(
            success=True,
            message="Validation successful (mocked)",
            error=None,
        )

    try:
        from myrm_agent_harness.toolkits.retriever.reranker.cloud_reranker import (
            CloudReranker,
        )

        # 创建服务实例
        service = CloudReranker(
            model=request.model,
            api_key=request.api_key,
            api_base=request.api_base,
        )

        # 测试重排序（使用简短测试数据）
        test_query = "test"
        test_docs = ["doc1", "doc2"]
        results = await service.rerank(query=test_query, documents=test_docs, top_k=1)

        # 验证返回结果
        if not results or len(results) == 0:
            return ValidationResponse(
                success=False,
                message="Validation failed: Invalid response format",
                error="Expected rerank results but got empty response",
            )

        logger.info(f"Reranker validation successful: model={request.model}, results={len(results)}")

        return ValidationResponse(
            success=True,
            message=f"Validation successful (returned {len(results)} result{'s' if len(results) > 1 else ''})",
            error=None,
        )

    except ImportError as e:
        logger.warning(f"Reranker validation failed: ImportError: {e}")
        return ValidationResponse(
            success=False,
            message="Validation failed: LiteLLM not installed",
            error=str(e),
        )
    except Exception as e:
        logger.warning(f"Reranker validation failed for model {request.model}: {type(e).__name__}: {e}")
        return ValidationResponse(
            success=False,
            message=f"Validation failed: {type(e).__name__}",
            error=str(e),
        )
