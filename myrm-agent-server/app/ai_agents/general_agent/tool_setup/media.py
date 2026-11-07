"""[INPUT]
- app.ai_agents.general_agent.tool_setup::tool_setup_common (POS: `app.ai_agents.general_agent.tool_setup` 的唯一入口；实现按工具族分层。)
- app.ai_agents.general_agent.tool_setup.base::ToolSetupBaseMixin (POS: 各工具族 mixin 共同继承，避免重复声明宿主属性。)
- app.ai_agents.general_agent.tool_setup.common::_is_media_credential_configured / _video_generation_credential_configured (POS: 只放无 self 依赖的判断/构造工具，供各工具族 mixin 复用。)

[OUTPUT]
- MediaToolsMixin: 图像、视频与 TTS 工具。

[POS]
ToolSetupMixin 的一个工具族；由 mixin.py 组合。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from . import common as tool_setup_common
from .base import ToolSetupBaseMixin

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.llms.image.models import MediaCallback


from app.ai_agents.general_agent.tool_setup.common import (
    _is_media_credential_configured,
    _video_generation_credential_configured,
)

logger = logging.getLogger(__name__)


class MediaToolsMixin(ToolSetupBaseMixin):
    """图像、视频与 TTS 工具。"""

    def _setup_image_generation_tools(
        self,
        tools: list[object],
        *,
        task_user_id: str = "default",
    ) -> None:
        """Register image generation/editing tools if configured (AgentDeclared eager mount)."""
        if not self.image_generation_params:
            return

        params = self.image_generation_params
        if not _is_media_credential_configured(params.api_key, params.gateway_config):
            logger.debug("Image generation tool skipped: no API key or gateway configured")
            return

        try:
            from myrm_agent_harness.toolkits.llms.image import (
                ImageGenerationConfig,
                ImageGenerationTools,
            )

            from app.ai_agents.media_tools import (
                create_image_generation_tool,
                create_media_persist_callback,
            )
            from app.config.deploy_mode import is_local_mode

            chat_id = self.chat_id or getattr(self, "_current_chat_id", None)
            agent_id = getattr(self, "agent_id", None)
            config = ImageGenerationConfig(
                model=params.model,
                api_key=params.api_key,
                fallback_models=params.fallback_models,
                default_size=params.default_size,
                default_quality=params.default_quality,
                timeout_seconds=params.timeout_seconds,
                max_retries=params.max_retries,
                gateway_config=params.gateway_config,
                media_callback=create_media_persist_callback(
                    chat_id=chat_id,
                    model_name=params.model,
                    source="generate",
                ),
            )
            img_engine = ImageGenerationTools(
                config,
                allow_private_networks=is_local_mode(),
                on_artifact_created=tool_setup_common._get_artifact_push_fn(),
            )
            tools.append(
                create_image_generation_tool(
                    img_engine,
                    allow_private_networks=is_local_mode(),
                    async_config=config,
                    task_user_id=task_user_id,
                    agent_id=agent_id,
                    chat_id=chat_id,
                )
            )
            logger.warning(
                "🖼️ Image generation tool loaded (model=%s, fallbacks=%s) [AgentDeclared]",
                params.model,
                params.fallback_models,
            )
        except Exception as e:
            logger.warning("⚠️ Image generation tools failed to load: %s", e)

    def _setup_video_generation_tools(
        self,
        tools: list[object],
        *,
        task_user_id: str = "default",
    ) -> None:
        """Register video generation tools if configured (AgentDeclared eager mount)."""
        if not self.video_generation_params:
            return

        params = self.video_generation_params
        if not _video_generation_credential_configured(params):
            logger.debug("Video generation tool skipped: no API key or gateway configured")
            return

        try:
            from myrm_agent_harness.toolkits.llms.video import (
                VideoGenerationConfig,
                VideoGenerationTools,
            )

            from app.ai_agents.media_tools import (
                create_video_generation_tool,
            )

            fallback_configs = []
            for fb in params.fallback_providers:
                fallback_configs.append(
                    VideoGenerationConfig(
                        provider=fb.get("provider", "openai"),
                        model=fb.get("model", "sora"),
                        api_key=fb.get("api_key"),
                        gateway_config=params.gateway_config,
                    )
                )

            config = VideoGenerationConfig(
                provider=params.provider,
                model=params.model,
                api_key=params.api_key,
                timeout_seconds=params.timeout_seconds,
                max_retries=params.max_retries,
                fallback_configs=fallback_configs,
                default_aspect_ratio=params.default_aspect_ratio,
                default_resolution=params.default_resolution,
                default_duration_seconds=params.default_duration_seconds,
                gateway_config=params.gateway_config,
                media_callback=self._create_video_media_callback(),
            )
            video_engine = VideoGenerationTools(
                config,
                on_artifact_created=tool_setup_common._get_artifact_push_fn(),
            )
            tools.append(
                create_video_generation_tool(
                    video_engine,
                    async_config=config,
                    task_user_id=task_user_id,
                    agent_id=getattr(self, "agent_id", None),
                    chat_id=self.chat_id or getattr(self, "_current_chat_id", None),
                )
            )
            logger.warning(
                "🎬 Video generation tool loaded (provider=%s, model=%s) [AgentDeclared]",
                params.provider,
                params.model,
            )
        except Exception as e:
            logger.warning("⚠️ Video generation tools failed to load: %s", e)

    def _create_video_media_callback(self) -> MediaCallback | None:
        """Create a media_callback for persisting generated videos to the media library."""
        return self._create_media_persist_callback(
            model_name=(self.video_generation_params.model if self.video_generation_params else None),
            source="video_generate",
        )

    def _setup_tts_tools(self, tools: list[object]) -> None:
        """Register TTS tools if configured (AgentDeclared eager mount)."""
        if not self.tts_params:
            return

        params = self.tts_params
        if not _is_media_credential_configured(params.api_key, params.gateway_config):
            logger.debug("TTS tool skipped: no API key or gateway configured")
            return

        try:
            from myrm_agent_harness.toolkits.llms.tts import TTSConfig

            from app.ai_agents.media_tools import create_tts_tool

            config = TTSConfig(
                provider=params.provider,
                model=params.model,
                voice=params.voice,
                api_key=params.api_key,
                timeout_seconds=params.timeout_seconds,
                max_retries=params.max_retries,
                gateway_config=params.gateway_config,
                media_callback=self._create_tts_media_callback(),
            )
            tts_tool = create_tts_tool(
                config,
                on_artifact_created=tool_setup_common._get_artifact_push_fn(),
            )
            tools.append(tts_tool)
            logger.warning(
                "🔊 TTS tool loaded (provider=%s, model=%s, voice=%s) [AgentDeclared]",
                params.provider,
                params.model,
                params.voice,
            )
        except Exception as e:
            logger.warning("⚠️ TTS tool failed to load: %s", e)

    def _create_tts_media_callback(self) -> MediaCallback | None:
        """Create a media_callback for persisting generated audio to the media library."""
        return self._create_media_persist_callback(
            model_name=(self.tts_params.model if self.tts_params else None),
            source="tts_generate",
        )

    def _create_media_persist_callback(
        self,
        *,
        model_name: str | None,
        source: str,
    ) -> MediaCallback | None:
        """Generic media persist callback factory."""
        from app.ai_agents.media_tools import (
            create_media_persist_callback,
        )

        chat_id = self._current_chat_id if hasattr(self, "_current_chat_id") else self.chat_id
        return create_media_persist_callback(
            chat_id=chat_id,
            model_name=model_name,
            source=source,
        )
