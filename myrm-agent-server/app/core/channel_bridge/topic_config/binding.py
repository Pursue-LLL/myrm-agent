"""[INPUT]
- .common (POS: shared constants and helpers)

[OUTPUT]
- BindingMixin

[POS]
Topic manager mixin: topic resolve/bind/unbind and metadata sync.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.channels.types import DraftTimeoutAction, IdentityScopeMode, ReplyMode, TopicContext
from app.channels.types.thread_sharing import ThreadSharingMode

from .common import (
    _CHANNEL_LEVEL_KEY,
    _TOPIC_WORKSPACE_MUTUAL_EXCLUSIVE_MSG,
    _UNSET,
    clean_identity_id,
    logger,
)


class BindingMixin:
    async def resolve_topic(
        self,
        channel: str,
        chat_id: str,
        thread_id: str | None,
    ) -> TopicContext | None:
        config = await self._load_config(channel)
        if not config:
            return None

        group_topics = config.get(chat_id)
        if not isinstance(group_topics, dict):
            return None

        storage_key = thread_id if thread_id is not None else _CHANNEL_LEVEL_KEY
        topic_cfg = group_topics.get(storage_key)
        if not isinstance(topic_cfg, dict):
            return None

        if self._is_expired(topic_cfg):
            self._delete_binding_keys(config, chat_id, storage_key)
            await self._save_config(channel, config)
            logger.info(
                "SqlTopicManager: expired binding %s/%s/%s auto-removed",
                channel,
                chat_id,
                storage_key,
            )
            return None

        raw_agent_id = topic_cfg.get("agentId")
        if isinstance(raw_agent_id, str) and raw_agent_id:
            if not await self._is_channel_bindable_agent(raw_agent_id):
                self._delete_binding_keys(config, chat_id, storage_key)
                await self._save_config(channel, config)
                logger.info(
                    "SqlTopicManager: unbindable agent %s binding %s/%s/%s auto-removed",
                    raw_agent_id,
                    channel,
                    chat_id,
                    storage_key,
                )
                return None

        await self._touch_active(channel, chat_id, storage_key, config)

        raw_reply_mode = str(topic_cfg.get("replyMode", "auto"))
        reply_mode = ReplyMode(raw_reply_mode) if raw_reply_mode in ReplyMode.__members__.values() else ReplyMode.AUTO
        raw_timeout_action = str(topic_cfg.get("draftTimeoutAction", "auto_reject"))
        timeout_action = (
            DraftTimeoutAction(raw_timeout_action)
            if raw_timeout_action in DraftTimeoutAction.__members__.values()
            else DraftTimeoutAction.AUTO_REJECT
        )
        raw_identity_scope = str(topic_cfg.get("identityScope", "inherit"))
        identity_scope = (
            IdentityScopeMode(raw_identity_scope)
            if raw_identity_scope in IdentityScopeMode.__members__.values()
            else IdentityScopeMode.INHERIT
        )

        return TopicContext(
            topic_id=thread_id or chat_id,
            agent_id=str(topic_cfg["agentId"]) if topic_cfg.get("agentId") else None,
            project_id=str(topic_cfg["projectId"]) if topic_cfg.get("projectId") else None,
            authorized_path=(str(topic_cfg["authorizedPath"]) if topic_cfg.get("authorizedPath") else None),
            enabled=bool(topic_cfg.get("enabled", True)),
            bound_at=str(topic_cfg["boundAt"]) if topic_cfg.get("boundAt") else None,
            thread_sharing_mode=str(topic_cfg.get("threadSharingMode", "isolated")),
            reply_mode=reply_mode,
            draft_timeout_minutes=int(topic_cfg.get("draftTimeoutMinutes", 5)),
            draft_timeout_action=timeout_action,
            personality_style=str(topic_cfg["personalityStyle"]) if topic_cfg.get("personalityStyle") else None,
            identity_scope=identity_scope,
            identity_id=str(topic_cfg["identityId"]) if topic_cfg.get("identityId") else None,
            identity_name=str(topic_cfg["identityName"]) if topic_cfg.get("identityName") else None,
            identity_revoked=bool(topic_cfg.get("identityRevoked", False)),
            completion_receipts=bool(topic_cfg.get("completionReceipts", True)),
            stall_nudge=bool(topic_cfg.get("stallNudge", False)),
        )

    async def bind_topic(
        self,
        channel: str,
        chat_id: str,
        thread_id: str | None,
        *,
        agent_id: str | None | object = _UNSET,
        display_name: str | None = None,
        avatar_url: str | None = None,
        thread_sharing_mode: ThreadSharingMode | object = _UNSET,
        reply_mode: ReplyMode | object = _UNSET,
        draft_timeout_minutes: int | object = _UNSET,
        draft_timeout_action: DraftTimeoutAction | object = _UNSET,
        project_id: str | None | object = _UNSET,
        authorized_path: str | None | object = _UNSET,
        personality_style: str | None | object = _UNSET,
        identity_scope: IdentityScopeMode | object = _UNSET,
        identity_id: str | None | object = _UNSET,
        identity_name: str | None | object = _UNSET,
        identity_revoked: bool | object = _UNSET,
        completion_receipts: bool | object = _UNSET,
        stall_nudge: bool | object = _UNSET,
    ) -> TopicContext:
        resolved_agent_id: str | None = None
        if agent_id is not _UNSET:
            resolved_agent_id = None if agent_id is None else str(agent_id)
            if resolved_agent_id:
                resolved_agent_id = await self._resolve_agent_id(resolved_agent_id)
                await self._assert_channel_bindable_agent(resolved_agent_id)

        if project_id is not _UNSET and authorized_path is not _UNSET:
            if project_id and authorized_path:
                raise ValueError(_TOPIC_WORKSPACE_MUTUAL_EXCLUSIVE_MSG)

        storage_key = thread_id if thread_id is not None else _CHANNEL_LEVEL_KEY
        config = await self._load_config(channel)
        group_topics = config.get(chat_id)
        existing: dict[str, object] = {}
        if isinstance(group_topics, dict):
            existing_raw = group_topics.get(storage_key)
            if isinstance(existing_raw, dict):
                existing = dict(existing_raw)

        now_iso = datetime.now(timezone.utc).isoformat()
        topic_entry: dict[str, object] = dict(existing)
        topic_entry["enabled"] = True
        topic_entry["boundAt"] = existing.get("boundAt") or now_iso
        topic_entry["lastActiveAt"] = now_iso
        topic_entry["idleTimeoutH"] = self._default_idle_timeout_h
        if self._default_max_age_h is not None:
            topic_entry["maxAgeH"] = self._default_max_age_h

        if thread_sharing_mode is not _UNSET:
            mode_value = (
                thread_sharing_mode.value if isinstance(thread_sharing_mode, ThreadSharingMode) else str(thread_sharing_mode)
            )
            topic_entry["threadSharingMode"] = mode_value
        if reply_mode is not _UNSET:
            topic_entry["replyMode"] = reply_mode.value
        if draft_timeout_minutes is not _UNSET:
            topic_entry["draftTimeoutMinutes"] = draft_timeout_minutes
        if draft_timeout_action is not _UNSET:
            topic_entry["draftTimeoutAction"] = draft_timeout_action.value

        if resolved_agent_id is not None:
            topic_entry["agentId"] = resolved_agent_id
        elif agent_id is not _UNSET and agent_id is None:
            topic_entry.pop("agentId", None)

        if display_name is not None:
            topic_entry["displayName"] = display_name
        if avatar_url is not None:
            topic_entry["avatarUrl"] = avatar_url

        resolved_project_id: str | None = None
        resolved_authorized_path: str | None = None
        if project_id is not _UNSET:
            if project_id:
                from app.core.channel_bridge.topic_workspace_bind import assert_project_workspace

                await assert_project_workspace(str(project_id))
                topic_entry["projectId"] = str(project_id)
                topic_entry.pop("authorizedPath", None)
                resolved_project_id = str(project_id)
            else:
                topic_entry.pop("projectId", None)
        if authorized_path is not _UNSET:
            if authorized_path:
                from app.core.channel_bridge.topic_workspace_bind import validate_authorized_path

                validated_path = validate_authorized_path(str(authorized_path))
                topic_entry["authorizedPath"] = validated_path
                topic_entry.pop("projectId", None)
                resolved_authorized_path = validated_path
            else:
                topic_entry.pop("authorizedPath", None)

        if project_id is _UNSET and authorized_path is _UNSET:
            resolved_project_id = str(topic_entry["projectId"]) if topic_entry.get("projectId") else None
            resolved_authorized_path = str(topic_entry["authorizedPath"]) if topic_entry.get("authorizedPath") else None
        elif project_id is _UNSET:
            resolved_project_id = str(topic_entry["projectId"]) if topic_entry.get("projectId") else None
        elif authorized_path is _UNSET:
            resolved_authorized_path = str(topic_entry["authorizedPath"]) if topic_entry.get("authorizedPath") else None

        if personality_style is not _UNSET:
            if personality_style:
                topic_entry["personalityStyle"] = str(personality_style)
            else:
                topic_entry.pop("personalityStyle", None)

        if identity_scope is not _UNSET:
            scope_value = identity_scope.value if isinstance(identity_scope, IdentityScopeMode) else str(identity_scope)
            topic_entry["identityScope"] = scope_value
        if identity_id is not _UNSET:
            if identity_id:
                topic_entry["identityId"] = clean_identity_id(str(identity_id))
            else:
                topic_entry.pop("identityId", None)
        if identity_name is not _UNSET:
            if identity_name:
                topic_entry["identityName"] = str(identity_name)
            else:
                topic_entry.pop("identityName", None)
        if identity_revoked is not _UNSET:
            topic_entry["identityRevoked"] = bool(identity_revoked)
        if completion_receipts is not _UNSET:
            topic_entry["completionReceipts"] = bool(completion_receipts)
        if stall_nudge is not _UNSET:
            topic_entry["stallNudge"] = bool(stall_nudge)

        await self._upsert_topic(channel, chat_id, storage_key, topic_entry)

        raw_reply_mode = str(topic_entry.get("replyMode", ReplyMode.AUTO.value))
        effective_reply_mode = ReplyMode(raw_reply_mode) if raw_reply_mode in ReplyMode.__members__.values() else ReplyMode.AUTO
        raw_timeout_action = str(topic_entry.get("draftTimeoutAction", DraftTimeoutAction.AUTO_REJECT.value))
        effective_timeout_action = (
            DraftTimeoutAction(raw_timeout_action)
            if raw_timeout_action in DraftTimeoutAction.__members__.values()
            else DraftTimeoutAction.AUTO_REJECT
        )
        raw_identity_scope = str(topic_entry.get("identityScope", IdentityScopeMode.INHERIT.value))
        effective_identity_scope = (
            IdentityScopeMode(raw_identity_scope)
            if raw_identity_scope in IdentityScopeMode.__members__.values()
            else IdentityScopeMode.INHERIT
        )

        return TopicContext(
            topic_id=thread_id or chat_id,
            agent_id=(str(topic_entry["agentId"]) if topic_entry.get("agentId") else None),
            project_id=resolved_project_id,
            authorized_path=resolved_authorized_path,
            enabled=True,
            bound_at=str(topic_entry.get("boundAt", now_iso)),
            thread_sharing_mode=str(topic_entry.get("threadSharingMode", "isolated")),
            reply_mode=effective_reply_mode,
            draft_timeout_minutes=int(topic_entry.get("draftTimeoutMinutes", 5)),
            draft_timeout_action=effective_timeout_action,
            personality_style=str(topic_entry["personalityStyle"]) if topic_entry.get("personalityStyle") else None,
            identity_scope=effective_identity_scope,
            identity_id=str(topic_entry["identityId"]) if topic_entry.get("identityId") else None,
            identity_name=str(topic_entry["identityName"]) if topic_entry.get("identityName") else None,
            identity_revoked=bool(topic_entry.get("identityRevoked", False)),
            completion_receipts=bool(topic_entry.get("completionReceipts", True)),
            stall_nudge=bool(topic_entry.get("stallNudge", False)),
        )

    async def unbind_topic(
        self,
        channel: str,
        chat_id: str,
        thread_id: str | None,
    ) -> bool:
        config = await self._load_config(channel)
        group_topics = config.get(chat_id)
        storage_key = thread_id if thread_id is not None else _CHANNEL_LEVEL_KEY
        if not isinstance(group_topics, dict) or storage_key not in group_topics:
            return False

        del group_topics[storage_key]
        if not group_topics:
            del config[chat_id]

        await self._save_config(channel, config)

        from app.channels.routing.follow_up import drop_tracked_thread

        drop_tracked_thread(channel, chat_id, thread_id)
        return True

    async def sync_topic_metadata(
        self,
        channel: str,
        chat_id: str,
        thread_id: str | None,
        *,
        display_name: str | None = None,
        avatar_url: str | None = None,
    ) -> None:
        if display_name is None and avatar_url is None:
            return

        config = await self._load_config(channel)
        group_raw = config.get(chat_id)
        if not isinstance(group_raw, dict):
            group_topics: dict[str, object] = {}
            config[chat_id] = group_topics
        else:
            group_topics = group_raw

        storage_key = thread_id if thread_id is not None else _CHANNEL_LEVEL_KEY
        topic_raw = group_topics.get(storage_key)
        if not isinstance(topic_raw, dict):
            topic_cfg: dict[str, object] = {}
            group_topics[storage_key] = topic_cfg
        else:
            topic_cfg = topic_raw

        changed = False
        if display_name is not None and topic_cfg.get("displayName") != display_name:
            topic_cfg["displayName"] = display_name
            changed = True
        if avatar_url is not None and topic_cfg.get("avatarUrl") != avatar_url:
            topic_cfg["avatarUrl"] = avatar_url
            changed = True

        if changed:
            await self._save_config(channel, config)
