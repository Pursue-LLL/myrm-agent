"""ChannelAgentExecutor — bridge between IM channel inbound messages and the SkillAgent runtime.

[INPUT]
- myrm_agent_harness.agent (POS: Agent execution engine framework)
- app.channels.types (POS: Session identity, message types, reset policy definitions)
- app.channels.i18n (POS: i18n text resolution for channel messages)
- app.core.channel_bridge.config_loader (POS: UserConfig table loader)
- app.core.channel_bridge.config_parsers (POS: Typed config extraction from frontend dicts)
- app.core.channel_bridge.executor_helpers (POS: Stream accumulation, history, title generation)
- app.services.agent.profile_resolver (POS: Agent profile resolution for multi-agent routing)
- app.services.artifacts.share_token (POS: HMAC share token for artifact deep links)
- app.remote_access.mobile_deep_link (POS: Public URL resolution for deep links)

[OUTPUT]
- ChannelAgentExecutor: async generator that processes an InboundMessage through
  config resolution → session management → Agent invocation → streaming response.
- _build_artifact_deep_links: generates ActionButton deep links for shareable artifacts
- _fetch_artifact_versions: batch DB lookup for artifact version IDs

[POS]
Business-layer executor for IM/channel inbound messages. Bridges channel routing
to the SkillAgent runtime with session-aware context, auto-reset notification,
streaming response assembly, and artifact deep link injection.
"""

from __future__ import annotations

import asyncio
import base64 as b64
import logging
import mimetypes
import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.channels.types.components import ComponentRow

from myrm_agent_harness.agent.config import ConfigIncompleteError
from myrm_agent_harness.agent.middlewares._session_context import (
    set_approval_user_id,
)
from myrm_agent_harness.agent.middlewares.approval.scheduler import (
    ApprovalTimeoutScheduler,
)
from myrm_agent_harness.toolkits.code_execution.interceptor import set_execution_interceptor
from myrm_agent_harness.toolkits.llms.errors import MyrmLLMError
from myrm_agent_harness.utils.locale import is_chinese
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken
from myrm_agent_harness.utils.runtime.steering import SteeringToken
from myrm_agent_harness.utils.text_utils import strip_internal_markers

from app.channels.i18n import get_text, resolve_message_locale
from app.channels.types import (
    InboundMessage,
    MediaAttachment,
    MediaType,
    OutboundMessage,
    ProgressUpdate,
    QuickReply,
    SessionResetMode,
    StreamingText,
    ToolStep,
    TopicContext,
    guess_media_type,
)
from app.channels.types.thread_sharing import ThreadSharingMode
from app.core.channel_bridge.config_loader import load_user_configs
from app.core.memory.proactive.settings import resolve_memory_enabled
from app.core.channel_bridge.config_parsers import (
    extract_fallback_model_configs,
    extract_lite_model_config,
    extract_mcp_configs,
    extract_retrieval_models,
    extract_session_policy,
    extract_user_instructions,
    session_policy_from_agent_dict,
    verify_search_service_available,
)
from app.core.channel_bridge.executor_helpers import (
    StreamAccumulator,
    build_chat_history_with_metadata,
    extract_external_agents,
    generate_channel_title,
    load_history_without_persist,
    persist_and_load_history,
    persist_assistant_message,
    schedule_channel_approval_timeout,
    step_to_label,
    suggest_quick_replies,
)
from app.services.agent.profile_resolver import (
    ResolvedAgentProfile,
    get_agent_profile_resolver,
)
from app.services.checkpoint.snapshot_service import SnapshotInterceptor

from .helpers import (
    _extract_code_exec_network,
    _resolve_inbound_memory_identity,
    build_channel_inbound_query,
)
from .session import resolve_session_key

logger = logging.getLogger(__name__)

_MAX_CHANNEL_ARTIFACT_BYTES = 5 * 1024 * 1024  # 5MB, matches BaseArtifactProcessor limit

# Initialize and register the snapshot interceptor
set_execution_interceptor(SnapshotInterceptor())


def _collect_channel_artifacts(event: dict[str, object], acc: StreamAccumulator) -> None:
    """Extract deliverable file artifacts from an 'artifacts' event into the accumulator.

    The stream_pipeline's LocalArtifactProcessor already resolved local file paths.
    We convert those into MediaAttachments for IM channel outbound delivery.
    Shareable artifacts (HTML/PDF/Document) are also tracked for deep link injection.
    """
    from app.services.artifacts.share_token import is_shareable_artifact

    artifacts_data = event.get("data")
    if not isinstance(artifacts_data, list):
        return
    for item in artifacts_data:
        if not isinstance(item, dict):
            continue
        file_path = item.get("file_path")
        filename = item.get("filename", "")
        content_type = item.get("content_type", "")
        artifact_id = item.get("id")
        artifact_type = item.get("type")
        if not file_path or not isinstance(file_path, str):
            continue
        if not os.path.isfile(file_path):
            continue
        try:
            file_size = os.path.getsize(file_path)
        except OSError:
            continue
        if file_size > _MAX_CHANNEL_ARTIFACT_BYTES or file_size == 0:
            continue
        fname = str(filename)
        mime = str(content_type) if content_type else (mimetypes.guess_type(fname)[0] or "application/octet-stream")
        acc.file_attachments.append(
            MediaAttachment(
                media_type=guess_media_type(fname, mime),
                path=file_path,
                filename=fname,
                mime_type=mime,
            )
        )
        if isinstance(artifact_id, str) and artifact_id:
            atype = str(artifact_type) if artifact_type else None
            if is_shareable_artifact(fname, atype):
                acc.shareable_artifacts.append((artifact_id, fname, atype or ""))


async def _build_artifact_deep_links(
    acc: StreamAccumulator,
    media_list: list[MediaAttachment],
    locale: str,
) -> tuple[ComponentRow, ...]:
    """Generate public share link buttons for shareable artifacts.

    For each shareable artifact (HTML/PDF/Document), creates an ActionButton
    with a signed share URL and removes the redundant raw file attachment.
    Returns empty tuple when no public URL is available (safe degradation).
    """
    if not acc.shareable_artifacts:
        return ()

    from app.channels.i18n import channel_t
    from app.channels.types.components import ActionButton, ButtonStyle
    from app.core.infra.ingress import get_public_ingress_base_url
    from app.remote_access.mobile_deep_link import resolve_mobile_remote_base_url
    from app.services.artifacts.share_token import create_artifact_share_token

    try:
        ingress = await get_public_ingress_base_url()
    except Exception:
        ingress = ""
    base_url = resolve_mobile_remote_base_url(public_ingress_base_url=ingress)
    if not base_url:
        return ()

    version_map = await _fetch_artifact_versions(
        [aid for aid, _, _ in acc.shareable_artifacts],
    )
    if not version_map:
        return ()

    buttons: list[ActionButton] = []
    linked_filenames: set[str] = set()
    multi = len(acc.shareable_artifacts) > 1

    for artifact_id, filename, artifact_type in acc.shareable_artifacts:
        version_id = version_map.get(artifact_id)
        if not version_id:
            continue
        try:
            token, _ = create_artifact_share_token(
                artifact_id, version_id, artifact_type=artifact_type or None,
            )
        except Exception:
            logger.warning("Failed to create share token for artifact %s", artifact_id)
            continue

        share_url = f"{base_url}/public/artifact-share/{token}"
        if multi:
            label = channel_t(locale, "artifact_deep_link_named", filename=filename)
        else:
            label = channel_t(locale, "artifact_deep_link")
        buttons.append(ActionButton(
            label=str(label),
            action_id=f"artifact:share:{artifact_id}",
            style=ButtonStyle.PRIMARY,
            url=share_url,
        ))
        linked_filenames.add(filename)

    if linked_filenames:
        media_list[:] = [
            m for m in media_list
            if m.filename not in linked_filenames
        ]

    if not buttons:
        return ()
    return (tuple(buttons),)


async def _fetch_artifact_versions(artifact_ids: list[str]) -> dict[str, str]:
    """Batch-fetch latest version_id for each artifact_id from DB."""
    if not artifact_ids:
        return {}
    try:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.database.connection import get_session
        from app.database.models.artifact import Artifact

        async with get_session() as db:
            stmt = (
                select(Artifact)
                .where(Artifact.id.in_(artifact_ids), Artifact.is_deleted.is_(False))
                .options(selectinload(Artifact.versions))
            )
            result = await db.execute(stmt)
            artifacts = result.scalars().all()

        version_map: dict[str, str] = {}
        for artifact in artifacts:
            if artifact.versions:
                latest = sorted(artifact.versions, key=lambda v: v.created_at, reverse=True)[0]
                version_map[artifact.id] = latest.id
        return version_map
    except Exception:
        logger.warning("Failed to fetch artifact versions for deep links", exc_info=True)
        return {}


class ChannelAgentExecutor:
    """Executes Agent tasks for inbound channel messages.

    Reads all user configs from the UserConfig table (same configs the
    frontend stores) to ensure channel messages have full Agent capabilities:
    model, filter model, search, MCP, retrieval, memory, and user instructions.
    """

    def _build_security_config(
        self,
        base_config: dict[str, object] | None,
        metadata: dict[str, object],
    ) -> dict[str, object]:
        """Build security config with YOLO state from metadata."""
        config = dict(base_config) if base_config else {}

        yolo_state = metadata.get("yolo_state")
        if yolo_state and isinstance(yolo_state, tuple) and len(yolo_state) == 2:
            enabled_at, timeout = yolo_state
            config["yolo_mode_enabled"] = True
            config["yolo_mode_enabled_at"] = enabled_at
            config["yolo_mode_timeout"] = timeout

        return config

    async def execute_stream(
        self,
        msg: InboundMessage,
        user_id: str = "",
        *,
        cancel_token: CancellationToken | None = None,
        steering_token: SteeringToken | None = None,
        topic_context: TopicContext | None = None,
    ) -> AsyncGenerator[ProgressUpdate | StreamingText | OutboundMessage, None]:
        agent = None
        configs = None
        token_ctx = None
        is_resume = bool(msg.resume_value)
        approval_timeout_info: dict[str, object] | None = None

        # Bind the resolved user_id into the harness approval ContextVar so the
        # downstream allow-always path (`add_to_allowlist_if_needed`) keys the
        # allowlist entry on the real user instead of `DEFAULT_USER_ID`.
        # This is the single integration point where channel-resolved identity
        # crosses into the harness approval subsystem.
        set_approval_user_id(user_id or msg.user_id or msg.sender_id)

        try:
            from myrm_agent_harness.toolkits.retriever.embedding.factory import (
                EmbeddingConfig,
            )
            from myrm_agent_harness.toolkits.retriever.reranker.factory import (
                RerankerConfig,
            )

            from app.ai_agents.agents import AgentFactory, GeneralAgentParams

            GeneralAgentParams.model_rebuild(
                _types_namespace={
                    "EmbeddingConfig": EmbeddingConfig,
                    "RerankerConfig": RerankerConfig,
                }
            )

            from app.services.budget.enforcer import should_block_execution

            if await should_block_execution():
                logger.warning(
                    "Channel execution blocked: daily budget exceeded (block policy), channel=%s chat_id=%s",
                    msg.channel,
                    msg.chat_id,
                )
                yield msg.get_or_create_correlation_context().create_reply(
                    content=get_text(msg, "daily_budget_blocked"),
                )
                return

            from app.services.budget.channel_budget import should_block_channel

            from .session import build_channel_budget_key

            channel_budget_key = build_channel_budget_key(msg)
            if channel_budget_key and should_block_channel(channel_budget_key):
                logger.warning(
                    "Channel execution blocked: channel budget exceeded, channel=%s chat_id=%s sender=%s",
                    msg.channel,
                    msg.chat_id,
                    msg.sender_id,
                )
                yield msg.get_or_create_correlation_context().create_reply(
                    content=get_text(msg, "channel_budget_blocked"),
                )
                return

            configs = await load_user_configs()

            query = build_channel_inbound_query(msg)

            embedding_cfg, reranker_cfg = extract_retrieval_models(configs.retrieval_dict)
            memory_settings = configs.personal_settings_dict or {}
            mcp_configs = extract_mcp_configs(configs.mcp_dict)
            lite_model_cfg = extract_lite_model_config(configs.providers_dict)
            fallback_model_cfg, fallback_lite_model_cfg = extract_fallback_model_configs(configs.providers_dict)
            user_instructions = extract_user_instructions(configs.personal_settings_dict)

            agent_skill_ids: list[str] = []
            agent_subagent_ids: list[str] | None = None
            agent_max_iterations: int | None = None
            resolved_agent_id: str | None = None
            resolved_profile: ResolvedAgentProfile | None = None
            agent_engine_params: dict[str, object] | None = None
            from app.services.agent.profile_resolver import (
                DEFAULT_ENABLED_BUILTIN_TOOLS,
                resolve_builtin_tool_flags,
            )

            enabled_builtin_tools: list[str] = list(DEFAULT_ENABLED_BUILTIN_TOOLS)
            auto_restore_domains: list[str] = []
            memory_decay_profile: str | None = None

            if topic_context and topic_context.agent_id:
                resolved_agent_id = topic_context.agent_id
                resolved_profile = await get_agent_profile_resolver().resolve(topic_context.agent_id)
                if resolved_profile:
                    if resolved_profile.system_prompt:
                        user_instructions = (
                            f"{user_instructions}\n\n{resolved_profile.system_prompt}"
                            if user_instructions
                            else resolved_profile.system_prompt
                        )
                    agent_skill_ids = list(resolved_profile.skill_ids)
                    agent_subagent_ids = list(resolved_profile.subagent_ids) if resolved_profile.subagent_ids else None
                    agent_max_iterations = resolved_profile.max_iterations
                    agent_engine_params = resolved_profile.engine_params
                    enabled_builtin_tools = list(resolved_profile.enabled_builtin_tools)
                    auto_restore_domains = list(resolved_profile.auto_restore_domains)
                    raw_decay = resolved_profile.memory_decay_profile
                    memory_decay_profile = raw_decay if isinstance(raw_decay, str) else None

            if resolved_profile and resolved_profile.agent_type == "team":
                from app.ai_agents.team_protocol import build_leader_protocol_prompt

                leader_protocol = await build_leader_protocol_prompt(
                    agent_subagent_ids or [],
                    leader_id=resolved_agent_id,
                    dynamic_discovery=True,
                )
                user_instructions = f"{user_instructions}\n\n{leader_protocol}" if user_instructions else leader_protocol

            # Inject channel capability constraints into system prompt
            if hasattr(msg, "channel_capabilities") and msg.channel_capabilities:
                caps = msg.channel_capabilities
                warnings = []
                if not caps.media:
                    warnings.append("- DO NOT attempt to generate or send any images, video, or audio.")
                if not caps.file_upload:
                    warnings.append("- DO NOT attempt to generate or send any files or documents (like CSV, PDF, etc.).")
                if not caps.markdown:
                    warnings.append(
                        "- DO NOT use Markdown formatting (like bold, italics, links, or code blocks). Use plain text only."
                    )

                if warnings:
                    warning_str = (
                        "IMPORTANT: You are communicating via a channel with the following limitations:\n"
                        + "\n".join(warnings)
                        + "\nDescribe things using text instead."
                    )
                    user_instructions = f"{user_instructions}\n\n{warning_str}" if user_instructions else warning_str

            # Inject personality style: metadata (temp command) > agent config > default
            from app.ai_agents.personality_templates import (
                DEFAULT_PERSONALITY_STYLE,
                PERSONALITY_TEMPLATES,
                get_personality_template,
            )

            raw_ps = (
                msg.metadata.get("personality_style")
                or (resolved_profile.personality_style if resolved_profile else None)
                or DEFAULT_PERSONALITY_STYLE
            )
            personality_style_key = str(raw_ps)
            if personality_style_key != DEFAULT_PERSONALITY_STYLE and personality_style_key in PERSONALITY_TEMPLATES:
                try:
                    template = get_personality_template(personality_style_key)  # key validated against template map
                    personality_suffix = f"\n\n**Communication Style**: {template.system_prompt_suffix}"
                    user_instructions = (
                        f"{user_instructions}{personality_suffix}" if user_instructions else personality_suffix.strip()
                    )
                except Exception as e:
                    logger.warning(
                        "Failed to load personality template '%s': %s",
                        personality_style_key,
                        e,
                    )

            session_policy = extract_session_policy(configs.personal_settings_dict)
            if resolved_profile and resolved_profile.session_policy and isinstance(resolved_profile.session_policy, dict):
                session_policy = session_policy_from_agent_dict(resolved_profile.session_policy)

            force_new = bool(msg.metadata.get("force_new_epoch"))
            thread_sharing_mode = topic_context.thread_sharing_mode if topic_context else ThreadSharingMode.ISOLATED
            session_key = await resolve_session_key(
                msg,
                session_policy,
                agent_id=resolved_agent_id,
                force_new_epoch=force_new,
                thread_sharing_mode=thread_sharing_mode,
            )

            # Concurrent backfill locking and cold-start detection to prevent duplicate insertions
            if not hasattr(self, "_backfill_locks"):
                self._backfill_locks = set()

            is_cold_start = False
            from app.services.chat.chat_service import ChatService

            try:
                existing_chat = await ChatService.get_channel_chat_by_key(session_key)
                if not existing_chat:
                    is_cold_start = True
                else:
                    existing_hist = await ChatService.load_channel_history(existing_chat.id, api_key=None)
                    if not existing_hist:
                        is_cold_start = True
            except Exception as e:
                logger.warning("Error checking cold-start for session %s: %s", session_key, e)

            if is_cold_start and session_key not in self._backfill_locks:
                self._backfill_locks.add(session_key)
                try:
                    from app.core.channel_bridge import get_channel_gateway

                    gateway = get_channel_gateway()
                    if gateway and gateway.bus:
                        channel_inst = gateway.bus.channels.get(msg.channel)
                        if channel_inst and hasattr(channel_inst, "fetch_history"):
                            backfill_limit = 15
                            if msg.metadata and isinstance(msg.metadata.get("backfill_limit"), int):
                                backfill_limit = msg.metadata["backfill_limit"]

                            if backfill_limit > 0:
                                hist_msgs = await channel_inst.fetch_history(msg.chat_id, limit=backfill_limit)
                                if hist_msgs:
                                    chat = await ChatService.get_or_create_channel_chat(
                                        session_key,
                                        msg.channel,
                                        agent_id=resolved_agent_id,
                                    )
                                    base_time = msg.sent_at - (len(hist_msgs) * 0.001) - 1.0

                                    for i, h_msg in enumerate(hist_msgs):
                                        truncated_content = h_msg.content
                                        if truncated_content and len(truncated_content) > 500:
                                            truncated_content = truncated_content[:500] + "..."

                                        if not truncated_content and not h_msg.media:
                                            continue

                                        smoothed_time = datetime.fromtimestamp(base_time + (i * 0.001), tz=timezone.utc)

                                        await ChatService.append_message(
                                            chat.id,
                                            "user",
                                            truncated_content,
                                            smoothed_time,
                                            h_msg.sent_timezone or "UTC",
                                            message_id=h_msg.message_id,
                                        )
                                    logger.warning(
                                        "Channel history backfilled successfully for chat_id=%s, count=%d",
                                        chat.id,
                                        len(hist_msgs),
                                    )
                except Exception as ex:
                    logger.warning(
                        "Failed to perform channel history backfill for session %s: %s",
                        session_key,
                        ex,
                    )
                finally:
                    self._backfill_locks.discard(session_key)

            # Prevent LLM hallucination after silent session reset (DAILY/IDLE)
            # by injecting a context note and notifying the IM user.
            session_was_auto_reset = (
                is_cold_start
                and not force_new
                and session_policy.mode != SessionResetMode.PERSISTENT
            )
            if session_was_auto_reset and session_policy.notify_on_reset:
                context_note = (
                    "[System note: This is a fresh conversation with no prior context. "
                    "Do not reference any previous conversation.]"
                )
                query = f"{context_note}\n{query}"

                if session_policy.mode == SessionResetMode.IDLE:
                    reset_label = get_text(
                        msg, "session_reset_notify_idle",
                        minutes=session_policy.idle_minutes,
                    )
                else:
                    reset_label = get_text(
                        msg, "session_reset_notify_daily",
                        hour=session_policy.daily_reset_hour,
                    )
                yield ProgressUpdate(label=reset_label)

            if is_resume:
                chat_id, history_entries = await load_history_without_persist(
                    channel_session_key=session_key,
                )
            else:
                sent_at_utc = datetime.fromtimestamp(msg.sent_at, tz=timezone.utc)
                chat_id, history_entries = await persist_and_load_history(
                    channel_session_key=session_key,
                    source=msg.channel,
                    content=msg.content,
                    sent_at=sent_at_utc,
                    sent_timezone=msg.sent_timezone,
                    agent_id=resolved_agent_id,
                )

            chat_history = build_chat_history_with_metadata(history_entries)

            user_timezone = str(memory_settings.get("timezone", "")) or None
            memory_identity = _resolve_inbound_memory_identity(
                msg,
                fallback_chat_id=chat_id,
                fallback_task_id=session_key,
            )
            memory_shared_context_ids: list[str] = []
            try:
                from app.services.memory.shared_context import (
                    resolve_shared_context_ids,
                )

                memory_shared_context_ids = await resolve_shared_context_ids(
                    agent_id=resolved_agent_id,
                    channel_id=memory_identity.channel_id,
                    conversation_id=memory_identity.conversation_id,
                    task_id=memory_identity.task_id,
                )
            except Exception as e:
                logger.warning(
                    "Failed to resolve shared memory contexts for channel message: %s",
                    e,
                )

            # Resolve model: agent-specific model > global default
            if resolved_profile and resolved_profile.model:
                from app.core.channel_bridge.model_resolver import (
                    enrich_model_context_window,
                    resolve_model_config,
                )

                agent_model_cfg = resolve_model_config(
                    configs.providers_dict,
                    model_override=resolved_profile.model,
                )
                agent_model_cfg = enrich_model_context_window(agent_model_cfg, configs.providers_dict)
            else:
                agent_model_cfg = configs.model_cfg

            if mcp_configs and resolved_profile:
                from app.services.agent.params.mcp_selection import apply_agent_mcp_selection

                mcp_configs = apply_agent_mcp_selection(
                    mcp_configs,
                    mcp_ids=resolved_profile.mcp_ids or None,
                    mcp_tool_selections=resolved_profile.mcp_tool_selections or None,
                )

            agent_wants_search = "web_search" in enabled_builtin_tools
            search_available = (
                agent_wants_search
                and configs.search_is_user_configured
                and await verify_search_service_available(configs.search_cfg)
            )
            if agent_wants_search and not search_available:
                if not configs.search_is_user_configured:
                    err_msg = get_text(msg, "search_not_configured")
                else:
                    err_msg = get_text(msg, "search_unreachable")
                yield msg.get_or_create_correlation_context().create_reply(content=err_msg)
                return

            from app.ai_agents.general_agent.context import set_current_agent_id, set_current_chat_id, set_current_turn_id

            # Set context for snapshot interceptor
            turn_id = msg.metadata.get("turn_id") or msg.message_id or "unknown"
            set_current_turn_id(turn_id)
            set_current_chat_id(chat_id)
            set_current_agent_id(resolved_agent_id or "default")

            params = GeneralAgentParams(
                query=query,
                model_cfg=agent_model_cfg,
                fallback_model_cfg=fallback_model_cfg,
                lite_model_cfg=lite_model_cfg,
                fallback_lite_model_cfg=fallback_lite_model_cfg,
                search_service_cfg=configs.search_cfg,
                mcp_cfg=mcp_configs or None,
                user_instructions=user_instructions,
                chat_id=chat_id,
                agent_id=resolved_agent_id,
                embedding_config=embedding_cfg,
                enable_memory=resolve_memory_enabled(memory_settings),
                reranker_config=reranker_cfg,
                agent_skill_ids=agent_skill_ids,
                subagent_ids=agent_subagent_ids,
                fetch_raw_webpage=bool(memory_settings.get("fetchRawWebpage")),
                enable_web_search=search_available,
                **resolve_builtin_tool_flags(enabled_builtin_tools),
                auto_restore_domains=auto_restore_domains,
                enable_advanced_retrieval=bool(
                    configs.retrieval_dict.get("enableAdvancedRetrieval") if configs.retrieval_dict else False
                ),
                memory_require_confirmation=bool(memory_settings.get("memoryRequireConfirmation")),
                enable_memory_auto_extraction=bool(memory_settings.get("enableMemoryAutoExtraction")),
                security_config_raw=self._build_security_config(configs.security_config_dict, msg.metadata),
                agent_security_raw=(
                    {str(k): v for k, v in resolved_profile.security_overrides.items()}
                    if resolved_profile and resolved_profile.security_overrides
                    else None
                ),
                memory_policy=(resolved_profile.memory_policy if resolved_profile else None),
                memory_decay_profile=memory_decay_profile,
                engine_params=agent_engine_params,
                max_iterations=agent_max_iterations,
                channel_name=msg.channel,
                memory_channel_id=memory_identity.channel_id,
                memory_conversation_id=memory_identity.conversation_id,
                memory_task_id=memory_identity.task_id,
                memory_shared_context_ids=memory_shared_context_ids,
                timezone=user_timezone,
                external_agents_config=extract_external_agents(configs.external_agents_dict),
                code_execution_allow_network=_extract_code_exec_network(memory_settings),
                notify_targets=(resolved_profile.notify_targets if resolved_profile else ()),
            )

            agent = AgentFactory.create_general_agent(params)
            approval_peer = msg.chat_id or msg.sender_id
            agent.approval_session_key = f"{msg.channel}:{approval_peer}"

            from langgraph.types import Command

            query_input: str | Command[object]
            if is_resume:
                approval_peer = msg.chat_id or msg.sender_id
                approval_key = f"{msg.channel}:{approval_peer}"
                if not ApprovalTimeoutScheduler.get().resolve_if_first(approval_key):
                    logger.warning("Channel resume rejected (timeout already resolved): key=%s", approval_key)
                    yield msg.get_or_create_correlation_context().create_reply(
                        content=get_text(msg, "approval_timeout_resolved"),
                    )
                    return
                query_input = Command(resume=msg.resume_value)
            else:
                query_input = query

            from myrm_agent_harness.agent.security import user_credentials_ctx

            from app.services.agent.session_credential_assembler import assemble_session_credentials

            credentials_list = await assemble_session_credentials(
                oauth_credentials_dict=configs.oauth_credentials_dict,
                providers_dict=configs.providers_dict,
                channel=msg.channel,
            )
            token_ctx = user_credentials_ctx.set(credentials_list)

            acc = StreamAccumulator()
            first_message_seen = False

            async def _open_channel_stream(
                q: object,
            ) -> AsyncGenerator[dict[str, object], None]:
                async for event in agent.process_stream(
                    query=q,
                    chat_history=chat_history or None,
                    chat_id=chat_id,
                    cancel_token=cancel_token,
                    steering_token=steering_token,
                    timezone=user_timezone,
                ):
                    if isinstance(event, dict):
                        yield event

            from app.services.agent.fission_config import (
                max_parallel_from_engine_params,
            )
            from app.services.agent.swarm_fission_resume import (
                stream_with_swarm_fission_resume,
            )

            async for event in stream_with_swarm_fission_resume(
                agent,
                query_input,
                _open_channel_stream,
                max_concurrent=max_parallel_from_engine_params(agent_engine_params),
            ):
                event_type = event.get("type", "")

                if event_type == "fission_topology":
                    yield event["data"]

                elif event_type == "tasks_steps":
                    step_key = str(event.get("step_key", ""))
                    label = step_to_label(step_key, event)
                    if label:
                        yield ProgressUpdate(label=label)
                        tool_name = str(event.get("tool_name", "")) or step_key
                        acc.tool_steps.append(ToolStep(name=tool_name, label=label))

                elif event_type == "reasoning" and isinstance(event.get("data"), str):
                    acc.reasoning_chunks.append(str(event["data"]))

                elif event_type == "message" and isinstance(event.get("data"), str):
                    if not first_message_seen:
                        first_message_seen = True
                        yield ProgressUpdate(label="✍️ Writing response...")

                    acc.chunks.append(str(event["data"]))
                    yield StreamingText(text="".join(acc.chunks))

                elif event_type == "sources" and isinstance(event.get("data"), list):
                    raw_src = event.get("data")
                    assert isinstance(raw_src, list)
                    src_items: list[dict[str, object]] = []
                    for el in raw_src:
                        if isinstance(el, dict):
                            src_items.append({str(k): val for k, val in el.items()})
                    acc.add_sources(src_items)

                elif event_type == "tool_approval_request":
                    data = event.get("data", {})
                    if isinstance(data, dict):
                        action_requests = data.get("actionRequests", [])
                        extensions = data.get("extensions", {})
                        timeout_info = extensions.get("timeout", {}) if isinstance(extensions, dict) else {}
                        timeout_secs = timeout_info.get("seconds", 300) if isinstance(timeout_info, dict) else 300
                        timeout_behavior = timeout_info.get("behavior", "deny") if isinstance(timeout_info, dict) else "deny"

                        if isinstance(action_requests, list) and action_requests:
                            tool_names = [str(req.get("action", "unknown")) for req in action_requests if isinstance(req, dict)]
                            reasons = [
                                str(req.get("description", ""))
                                for req in action_requests
                                if isinstance(req, dict) and req.get("description")
                            ]
                            tools_str = ", ".join(tool_names) if tool_names else "unknown"
                            reason_str = "; ".join(reasons) if reasons else ""
                        else:
                            tools_str = str(data.get("tool_name", "unknown"))
                            reason_str = str(data.get("reason", ""))

                        timeout_action = "auto-approve" if timeout_behavior == "allow" else "auto-deny"
                        label = f"{tools_str} needs approval: {reason_str}\n⏱ Timeout: {timeout_secs}s ({timeout_action})"

                        is_batch = isinstance(action_requests, list) and len(action_requests) > 1
                        quick_replies: tuple[QuickReply, ...] = (
                            QuickReply(label="✅ Approve", text="/approve", required=True),
                            QuickReply(label="❌ Deny", text="/deny", required=True),
                        )
                        if is_batch:
                            quick_replies = (
                                QuickReply(
                                    label="✅ Approve All",
                                    text="/approve",
                                    required=True,
                                ),
                                QuickReply(label="❌ Deny All", text="/deny", required=True),
                                QuickReply(
                                    label="📋 Batch",
                                    text=f"/batch {','.join('a' for _ in action_requests)}",
                                    required=True,
                                ),
                            )
                        yield ProgressUpdate(label=label, quick_replies=quick_replies)
                        approval_timeout_info = {
                            "seconds": timeout_secs,
                            "behavior": timeout_behavior,
                        }

                elif event_type == "tool_image_output":
                    img_data = event.get("data", {})
                    if isinstance(img_data, dict):
                        if img_data.get("base64"):
                            acc.last_image_base64 = str(img_data["base64"])
                            acc.last_image_url = None
                        elif img_data.get("url"):
                            acc.last_image_url = str(img_data["url"])
                            acc.last_image_base64 = None
                        acc.last_image_mime = str(img_data.get("mime_type", "image/jpeg"))
                        acc.last_image_tool = str(event.get("tool_name", ""))

                elif event_type == "artifacts":
                    _collect_channel_artifacts(event, acc)

                elif event_type == "error":
                    error_msg = str(event.get("error", "Unknown error"))
                    error_type = str(event.get("error_type", ""))
                    acc.error_message = f"{error_type}: {error_msg}" if error_type else error_msg

                elif event_type == "token_usage":
                    data = event.get("data")
                    if isinstance(data, dict):
                        cost = data.get("cost_usd")
                        if isinstance(cost, (int, float)):
                            acc.cost_usd += float(cost)
                        model = data.get("model_name")
                        if isinstance(model, str) and model:
                            acc.model_name = model
                        usage = data.get("usage")
                        if isinstance(usage, dict):
                            total = usage.get("total_tokens")
                            if isinstance(total, int) and total > 0:
                                acc.total_tokens += total

                elif event_type == "message_end":
                    end_cost = event.get("cost_usd")
                    if isinstance(end_cost, (int, float)) and end_cost > 0 and acc.cost_usd == 0:
                        acc.cost_usd = float(end_cost)
                    end_model = event.get("model")
                    if isinstance(end_model, str) and end_model and not acc.model_name:
                        acc.model_name = end_model

            content = strip_internal_markers("".join(acc.chunks))

            if not content.strip():
                if acc.error_message:
                    logger.warning(
                        "ChannelAgentExecutor: agent error for %s: %s",
                        msg.sender_id,
                        acc.error_message,
                    )
                    content = f"[Error] {acc.error_message}"
                else:
                    logger.warning("ChannelAgentExecutor: empty LLM response for %s", msg.sender_id)
                    content = "[No response generated]"

            await persist_assistant_message(
                chat_id,
                content,
                timezone=msg.sent_timezone,
                extra_data={
                    "costUsd": acc.cost_usd,
                    "channelSenderId": msg.sender_id,
                } if acc.cost_usd > 0 else None,
            )

            if channel_budget_key and acc.cost_usd > 0:
                from app.services.budget.channel_budget import record_channel_cost

                record_channel_cost(channel_budget_key, acc.cost_usd)

            if not chat_history:
                auto_title = bool(memory_settings.get("enableAutoTitleGeneration", True))
                asyncio.create_task(
                    generate_channel_title(
                        chat_id,
                        msg.content,
                        lite_model_cfg if auto_title else None,
                    )
                )

            metadata: dict[str, object] | None = None
            if acc.sources:

                def _sort_key(s: dict[str, object]) -> int:
                    v = s.get("index")
                    return int(v) if isinstance(v, (int, float)) else 0

                metadata = {"sources": sorted(acc.sources, key=_sort_key)}

            if session_was_auto_reset:
                if metadata is None:
                    metadata = {}
                metadata["session_auto_reset"] = {
                    "reason": session_policy.mode.value,
                    "idle_minutes": session_policy.idle_minutes,
                    "daily_reset_hour": session_policy.daily_reset_hour,
                }

            if acc.cost_usd > 0 and memory_settings.get("enableCostEstimation"):
                if metadata is None:
                    metadata = {}
                metadata["cost_metadata"] = {
                    "cost_usd": acc.cost_usd,
                    "model_name": acc.model_name,
                    "total_tokens": acc.total_tokens,
                }

            reasoning = "".join(acc.reasoning_chunks) or None
            tool_steps = tuple(acc.tool_steps)

            quick_replies = suggest_quick_replies(is_first_message=not chat_history)

            media_list: list[MediaAttachment] = []
            tmp_paths: list[str] = []
            if acc.last_image_base64:
                ext = "jpg" if "jpeg" in acc.last_image_mime else "png"
                try:
                    img_bytes = b64.b64decode(acc.last_image_base64)
                    tmp = tempfile.NamedTemporaryFile(
                        suffix=f".{ext}",
                        prefix="screenshot_",
                        delete=False,
                    )
                    tmp.write(img_bytes)
                    tmp.close()
                    tmp_paths.append(tmp.name)
                    media_list.append(
                        MediaAttachment(
                            media_type=MediaType.IMAGE,
                            path=tmp.name,
                            filename=f"screenshot.{ext}",
                            mime_type=acc.last_image_mime,
                        ),
                    )
                except Exception:
                    logger.warning("Failed to save screenshot image for channel reply")
            elif acc.last_image_url:
                ext = "jpg" if "jpeg" in acc.last_image_mime else "png"
                media_list.append(
                    MediaAttachment(
                        media_type=MediaType.IMAGE,
                        url=acc.last_image_url,
                        filename=f"screenshot.{ext}",
                        mime_type=acc.last_image_mime,
                    ),
                )

            media_list.extend(acc.file_attachments)

            artifact_components = await _build_artifact_deep_links(
                acc, media_list, resolve_message_locale(msg),
            )

            media = tuple(media_list)

            try:
                yield msg.get_or_create_correlation_context().create_reply(
                    content=content,
                    metadata=metadata,
                    media=media,
                    reasoning=reasoning,
                    tool_steps=tool_steps,
                    components=artifact_components,
                    quick_replies=quick_replies,
                )
            finally:
                for p in tmp_paths:
                    try:
                        os.unlink(p)
                    except OSError:
                        pass
        except ConfigIncompleteError as exc:
            logger.warning(
                "ChannelAgentExecutor: config incomplete for %s: %s",
                msg.sender_id,
                exc.technical_details,
            )
            locale = resolve_message_locale(msg)
            lang_key = "zh" if is_chinese(locale) else "en"
            friendly_msg = exc.user_friendly_message.get(lang_key) or exc.user_friendly_message.get("en", str(exc))

            error_metadata = {
                "error_type": exc.error_code,
                "resolution_steps": exc.resolution_steps,
                "config_url": "/settings/model-service",
            }

            steps_text = "\n".join(f"• {step}" for step in exc.resolution_steps[:3])
            yield msg.get_or_create_correlation_context().create_reply(
                content=f"{friendly_msg}{get_text(msg, 'config_next_steps', steps=steps_text)}",
                metadata=error_metadata,
            )
        except MyrmLLMError as exc:
            logger.error("ChannelAgentExecutor: LLM error for %s: %s", msg.sender_id, exc)

            locale = resolve_message_locale(msg)
            lang_key = "zh" if is_chinese(locale) else "en"

            # 2. Extract diagnostic_result from Harness layer (already translated)
            diagnostic_result = exc.diagnostic_result or {}
            user_message = diagnostic_result.get("user_message", str(exc))
            resolution_steps = diagnostic_result.get("resolution_steps", [])

            # Format friendly message for headless channels
            friendly_msg = f"❌ {user_message}"

            if exc.context and "cooldown_remaining_ms" in exc.context:
                retry_after_seconds = int(exc.context["cooldown_remaining_ms"]) / 1000
                friendly_msg += get_text(msg, "cooldown_retry", seconds=retry_after_seconds)

            if resolution_steps:
                steps_text = "\n".join(f"• {step}" for step in resolution_steps[:3])
                friendly_msg += get_text(msg, "config_next_steps", steps=steps_text)

            # 3. Generate recovery_actions with business URLs
            from app.core.errors.llm_errors import generate_recovery_actions

            recovery_actions = generate_recovery_actions(exc.error_code, lang_key)

            # 4. Rich Interactive Error Recovery for Headless Channels
            components = []
            if msg.channel_capabilities and msg.channel_capabilities.buttons and recovery_actions:
                from app.channels.types.messages import (
                    ActionButton,
                )

                action_buttons = []
                for action in recovery_actions:
                    action_buttons.append(
                        ActionButton(
                            label=action["label"],
                            action_id=action["id"],
                            value=action["id"],
                        )
                    )

                if action_buttons:
                    components.append(tuple(action_buttons))

            # 5. Build error metadata for Web UI (structured error recovery)
            error_metadata = {
                "error_type": exc.error_code,
                "recovery_actions": recovery_actions,
            }

            yield msg.get_or_create_correlation_context().create_reply(
                content=friendly_msg,
                components=tuple(components) if components else (),
                metadata=error_metadata,
            )
        except Exception as exc:
            logger.error(
                "ChannelAgentExecutor: agent failed for %s: %s",
                msg.sender_id,
                exc,
                exc_info=True,
            )
            yield msg.get_or_create_correlation_context().create_reply(
                content=f"[Error] Agent execution failed: {exc}",
            )
        finally:
            if token_ctx is not None:
                from myrm_agent_harness.agent.security import user_credentials_ctx

                user_credentials_ctx.reset(token_ctx)
            if approval_timeout_info and chat_id:
                schedule_channel_approval_timeout(
                    channel=msg.channel,
                    peer=msg.chat_id or msg.sender_id,
                    chat_id=chat_id,
                    timeout_info=approval_timeout_info,
                    params=params,
                )
            if agent:
                await agent.close()
