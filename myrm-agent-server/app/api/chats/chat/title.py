from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.errors import internal_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.dto import (
    GenerateTitleRequest,
    UpdateTitleRequest,
)
from app.database.standard_responses import StandardSuccessResponse
from app.services.chat.chat_service import ChatService

router = APIRouter()


@router.put("/{chat_id}/title", response_model=StandardSuccessResponse)
async def update_chat_title(
    chat_id: str,
    title_data: UpdateTitleRequest,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """更新聊天标题"""
    if not chat_id.strip():
        raise validation_error("Chat ID cannot be empty")

    try:
        chat = await ChatService.get_chat_metadata(chat_id)
        if not chat:
            raise not_found_error("Chat session")

        updated_chat = await ChatService.update_chat_title(chat_id, title_data.title)
        if not updated_chat:
            raise not_found_error("Chat session")
        return success_response()
    except HTTPException:
        raise
    except Exception as e:
        raise internal_error(operation="Update title", exception=e) from e


@router.post("/generate-title", response_model=StandardSuccessResponse)
async def generate_chat_title(
    title_data: GenerateTitleRequest,
) -> JSONResponse:
    """生成聊天标题

    从 UserConfig 表读取 filter model 配置，不再从请求中接收 API Key。
    """
    if not title_data.messages:
        raise validation_error("Messages cannot be empty")

    try:
        from app.core.channel_bridge.config_loader import load_user_configs
        from app.core.channel_bridge.config_parsers import (
            extract_fallback_model_configs,
            extract_lite_model_config,
        )
        from app.database.dto import _TitleModelConfig

        configs = await load_user_configs()
        lite_model_cfg = extract_lite_model_config(configs.providers_dict)
        _, fallback_filter_cfg = extract_fallback_model_configs(configs.providers_dict)

        title_model: _TitleModelConfig | None = None
        if lite_model_cfg:
            title_model = _TitleModelConfig.model_validate(
                {
                    "model": lite_model_cfg.model,
                    "apiKey": lite_model_cfg.api_key,
                    "baseUrl": lite_model_cfg.base_url,
                }
            )

        fallback_title_model: _TitleModelConfig | None = None
        if fallback_filter_cfg:
            fallback_title_model = _TitleModelConfig.model_validate(
                {
                    "model": fallback_filter_cfg.model,
                    "apiKey": fallback_filter_cfg.api_key,
                    "baseUrl": fallback_filter_cfg.base_url,
                }
            )

        title = await ChatService.generate_chat_title(
            title_data.messages,
            title_model=title_model,
            fallback_title_model=fallback_title_model,
        )
        return success_response(data={"title": title})
    except Exception as e:
        raise internal_error(operation="Generate chat title", exception=e) from e
