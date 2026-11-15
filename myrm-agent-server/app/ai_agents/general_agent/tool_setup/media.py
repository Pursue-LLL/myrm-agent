"""[INPUT]
- app.ai_agents.general_agent.tool_setup.base::ToolSetupBaseMixin (POS: 各工具族 mixin 共同继承，避免重复声明宿主属性。)
- app.ai_agents.general_agent.tool_setup.common::_is_media_credential_configured / _video_generation_credential_configured (POS: 只放无 self 依赖的判断/构造工具，供各工具族 mixin 复用。)
- app.core.media.selection::is_image_model_selected / is_video_selected / is_tts_selected (POS: 用户的选择是否指向引擎能运行的目录项)

[OUTPUT]
- MediaToolsMixin: 图像、视频与 TTS 工具。

[POS]
ToolSetupMixin 的一个工具族；由 mixin.py 组合。三个工具都要求用户已选择模型（供应商、音色）且凭据就绪才挂载，不补默认值。
"""

from __future__ import annotations

import logging

from app.core.media.selection import is_image_model_selected, is_tts_selected, is_video_selected

from .base import ToolSetupBaseMixin
from .common import (
    _is_media_credential_configured,
    _media_api_key,
    _media_gateway,
    _video_generation_credential_configured,
)

logger = logging.getLogger(__name__)


class MediaToolsMixin(ToolSetupBaseMixin):
    """图像、视频与 TTS 工具。"""

    def _media_chat_id(self) -> str | None:
        """Chat the generated media is filed under."""
        return self.chat_id or getattr(self, "_current_chat_id", None)

    def _setup_image_generation_tools(
        self,
        tools: list[object],
        *,
        task_user_id: str = "default",
    ) -> None:
        """Register image generation/editing tools once a model is selected and credentials are ready."""
        params = self.image_generation_params
        if params is None:
            return
        model = params.model
        if not is_image_model_selected(model):
            logger.debug("Image generation tool skipped: no usable model selected")
            return
        if not _is_media_credential_configured(params.api_key, params.gateway_config):
            logger.debug("Image generation tool skipped: no API key or gateway configured")
            return

        try:
            from myrm_agent_harness.toolkits.llms.image import ImageGenerationConfig

            from app.ai_agents.media_tools import create_image_generation_tool, create_media_persist_callback

            chat_id = self._media_chat_id()
            fallback_models = [name for name in params.fallback_models if is_image_model_selected(name)]
            config = ImageGenerationConfig(
                model=model,
                api_key=_media_api_key(params.api_key),
                fallback_models=fallback_models,
                default_size=params.default_size,
                timeout_seconds=params.timeout_seconds,
                max_retries=params.max_retries,
                gateway_config=_media_gateway(params.gateway_config),
                # Edits answer in the call, so this config stores their result itself; generation tasks rebuild
                # their own callback from the task snapshot.
                media_callback=create_media_persist_callback(chat_id=chat_id, model_name=model, source="generate"),
            )
            tools.append(
                create_image_generation_tool(
                    config,
                    allowed_roots=self.declared_allowed_roots,
                    task_user_id=task_user_id,
                    agent_id=getattr(self, "agent_id", None),
                    chat_id=chat_id,
                )
            )
            logger.info("Image generation tool loaded (model=%s, fallbacks=%s)", model, fallback_models)
        except Exception as e:
            logger.warning("Image generation tools failed to load: %s", e)

    def _setup_video_generation_tools(
        self,
        tools: list[object],
        *,
        task_user_id: str = "default",
    ) -> None:
        """Register video generation tools once a provider and model are selected and credentials are ready."""
        params = self.video_generation_params
        if params is None:
            return
        provider, model = params.provider, params.model
        if provider is None or model is None or not is_video_selected(provider, model):
            logger.debug("Video generation tool skipped: no usable provider and model selected")
            return
        if not _video_generation_credential_configured(params):
            logger.debug("Video generation tool skipped: no API key or gateway configured")
            return

        try:
            from myrm_agent_harness.toolkits.llms.video import VideoGenerationConfig

            from app.ai_agents.media_tools import create_video_generation_tool

            fallback_configs: list[VideoGenerationConfig] = []
            for fallback in params.fallback_providers:
                fallback_provider, fallback_model = fallback.get("provider"), fallback.get("model")
                if (
                    fallback_provider is None
                    or fallback_model is None
                    or not is_video_selected(fallback_provider, fallback_model)
                ):
                    continue
                fallback_configs.append(
                    VideoGenerationConfig(
                        provider=fallback_provider,
                        model=fallback_model,
                        api_key=_media_api_key(fallback.get("api_key")),
                        gateway_config=_media_gateway(params.gateway_config),
                    )
                )

            # Videos are generated by queued tasks, which rebuild their own persistence from the task snapshot.
            config = VideoGenerationConfig(
                provider=provider,
                model=model,
                api_key=_media_api_key(params.api_key),
                timeout_seconds=params.timeout_seconds,
                max_retries=params.max_retries,
                fallback_configs=fallback_configs,
                default_aspect_ratio=params.default_aspect_ratio,
                default_resolution=params.default_resolution,
                default_duration_seconds=params.default_duration_seconds,
                gateway_config=_media_gateway(params.gateway_config),
            )
            tools.append(
                create_video_generation_tool(
                    config,
                    allowed_roots=self.declared_allowed_roots,
                    task_user_id=task_user_id,
                    agent_id=getattr(self, "agent_id", None),
                    chat_id=self._media_chat_id(),
                )
            )
            logger.info("Video generation tool loaded (provider=%s, model=%s)", provider, model)
        except Exception as e:
            logger.warning("Video generation tools failed to load: %s", e)

    def _setup_tts_tools(self, tools: list[object]) -> None:
        """Register the TTS tool once a provider, model and voice are selected and credentials are ready."""
        params = self.tts_params
        if params is None:
            return
        provider, model, voice = params.provider, params.model, params.voice
        if provider is None or model is None or voice is None or not is_tts_selected(provider, model, voice):
            logger.debug("TTS tool skipped: no usable provider, model and voice selected")
            return
        if not _is_media_credential_configured(params.api_key, params.gateway_config):
            logger.debug("TTS tool skipped: no API key or gateway configured")
            return

        try:
            from myrm_agent_harness.toolkits.llms.tts import TTSConfig

            from app.ai_agents.media_tools import create_media_persist_callback, create_tts_tool

            config = TTSConfig(
                provider=provider,
                model=model,
                voice=voice,
                api_key=_media_api_key(params.api_key),
                timeout_seconds=params.timeout_seconds,
                max_retries=params.max_retries,
                gateway_config=_media_gateway(params.gateway_config),
                media_callback=create_media_persist_callback(
                    chat_id=self._media_chat_id(), model_name=model, source="tts_generate"
                ),
            )
            tools.append(create_tts_tool(config))
            logger.info("TTS tool loaded (provider=%s, model=%s, voice=%s)", provider, model, voice)
        except Exception as e:
            logger.warning("TTS tool failed to load: %s", e)
