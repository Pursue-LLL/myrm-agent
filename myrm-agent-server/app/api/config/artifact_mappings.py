"""
工件类型映射 API 端点

提供前端获取类型映射的接口，确保前后端类型一致。
"""

from fastapi import APIRouter
from myrm_agent_harness.agent.artifacts.constants import (
    EXTENSION_TO_ARTIFACT_TYPE,
    EXTENSION_TO_LANGUAGE,
    MIME_TO_ARTIFACT_TYPE,
    ArtifactType,
)
from pydantic import BaseModel

router = APIRouter()


class ArtifactMappingsResponse(BaseModel):
    """工件类型映射响应"""

    artifact_types: list[str]
    extension_to_language: dict[str, str]
    extension_to_artifact_type: dict[str, str]
    mime_to_artifact_type: dict[str, str]


@router.get("/artifact-mappings", response_model=ArtifactMappingsResponse)
async def get_artifact_mappings() -> ArtifactMappingsResponse:
    """
    获取工件类型映射

    返回所有工件相关的类型映射，供前端使用：
    - artifact_types: 支持的工件类型列表
    - extension_to_language: 文件扩展名到编程语言的映射
    - extension_to_artifact_type: 文件扩展名到工件类型的映射
    - mime_to_artifact_type: MIME 类型到工件类型的映射
    """
    return ArtifactMappingsResponse(
        artifact_types=[t.value for t in ArtifactType],
        extension_to_language=EXTENSION_TO_LANGUAGE,
        extension_to_artifact_type={k: v.value for k, v in EXTENSION_TO_ARTIFACT_TYPE.items()},
        mime_to_artifact_type={k: v.value for k, v in MIME_TO_ARTIFACT_TYPE.items()},
    )
