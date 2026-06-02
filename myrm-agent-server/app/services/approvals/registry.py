"""
[INPUT]
- app.database.models.approval::ApprovalRecord (POS: 审批持久化模型)
- app.services.event.app_event_bus::AppEvent (POS: 服务器级 SSE 总线)

[OUTPUT]
- ApprovalRegistry: 统一的拦截审批注册与唤醒中枢

[POS]
统一审批流调度器。负责将各种拦截节点落库并推送 SSE 事件，接收 resolve 指令。
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import and_, select

from app.database.connection import get_session
from app.database.models.approval import ApprovalRecord
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)


class ApprovalRegistry:
    """Registry for managing execution interruptions and manual approvals."""

    @classmethod
    async def cleanup_expired_approvals(cls) -> int:
        """Find pending approvals that have expired and reject them automatically.

        Returns:
            The number of approvals that were auto-rejected.
        """
        async with get_session() as db:
            stmt = select(ApprovalRecord).where(
                and_(
                    ApprovalRecord.status == "PENDING",
                    ApprovalRecord.expires_at.is_not(None),
                    ApprovalRecord.expires_at <= datetime.now(timezone.utc),
                )
            )
            result = await db.execute(stmt)
            expired_records = result.scalars().all()

            if not expired_records:
                return 0

            for record in expired_records:
                record.status = "TIMEOUT"
                record.resolved_at = datetime.now(timezone.utc)
                record.reason = (record.reason or "") + "\n\n[Auto-Rejected: TTL Expired]"

                # Emit event to awaken the suspended state machine with "deny" decision
                if record.thread_id:
                    try:
                        bus = get_event_bus()
                        bus.publish(
                            AppEvent(
                                event_type=AppEventType.STATUS,
                                data={
                                    "action": "resume_agent",
                                    "thread_id": record.thread_id,
                                    "chat_id": record.chat_id,
                                    "agent_id": record.agent_id,
                                    "decision": "deny",
                                    "edited_payload": None,
                                },
                            )
                        )
                        logger.info("Auto-rejected expired approval: %s (thread_id=%s)", record.id, record.thread_id)
                    except Exception as e:
                        logger.error("Failed to publish resume event for expired approval %s: %s", record.id, e)

            await db.commit()
            return len(expired_records)

    @classmethod
    async def create_approval(
        cls,
        agent_id: str,
        action_type: str,
        payload: dict[str, object],
        reason: str | None = None,
        severity: str = "warning",
        chat_id: str | None = None,
        thread_id: str | None = None,
        status: str = "PENDING",
        expires_at: datetime | None = None,
    ) -> ApprovalRecord:
        """Create a new approval record and emit an SSE event."""
        record_id = uuid4().hex

        async with get_session() as db:
            record = ApprovalRecord(
                id=record_id,
                agent_id=agent_id,
                chat_id=chat_id,
                thread_id=thread_id,
                action_type=action_type,
                reason=reason,
                severity=severity,
                payload=payload,
                status=status,
                expires_at=expires_at,
            )
            db.add(record)
            await db.commit()
            await db.refresh(record)

        # Broadcast SSE
        try:
            bus = get_event_bus()
            event_type = AppEventType.APPROVAL_REQUIRED if status == "PENDING" else AppEventType.SKILL_GROWTH_UPDATED
            # Only broadcast if it's one of the types we added to AppEventType
            if event_type in [e.value for e in AppEventType]:
                bus.publish(
                    AppEvent(
                        event_type=event_type,
                        data={
                            "approval_id": record.id,
                            "action_type": action_type,
                            "status": status,
                            "severity": severity,
                        },
                    )
                )
            logger.info("Approval record created and published: id=%s type=%s", record.id, action_type)
        except Exception as e:
            logger.error("Failed to publish approval event: %s", e)

        # Broadcast to Channel (Native Approval Blocks) if it's a channel chat
        if chat_id and status == "PENDING":
            try:
                from app.database.models.chat import Chat

                async with get_session() as db:
                    chat = (await db.execute(select(Chat).where(Chat.id == chat_id))).scalar_one_or_none()

                if chat and chat.source and chat.source != "web" and chat.channel_session_key:
                    from app.channels.types.components import ActionButton, ButtonStyle
                    from app.channels.types.messages import MessagePriority, OutboundMessage
                    from app.channels.types.session import SessionKey
                    from app.core.channel_bridge import get_channel_gateway

                    # Parse session key to find recipient ID
                    # We strip the epoch suffix if present (e.g. :e=...)
                    raw_key = chat.channel_session_key.split(":e=")[0]
                    sk = SessionKey.parse(raw_key)

                    if sk and sk.peer_id:
                        # Construct native block UI
                        timeout_str = f" (Expires: {expires_at.strftime('%H:%M:%S UTC')})" if expires_at else ""
                        msg_text = f"⚠️ **Approval Required**\nAction: `{action_type}`\nReason: {reason or 'Requires your review'}{timeout_str}"

                        components = (
                            (
                                ActionButton(
                                    label="✅ Approve",
                                    action_id=f"approval:approve:{record.id}",
                                    style=ButtonStyle.PRIMARY,
                                    value="approve",
                                ),
                                ActionButton(
                                    label="❌ Deny",
                                    action_id=f"approval:deny:{record.id}",
                                    style=ButtonStyle.DANGER,
                                    value="deny",
                                ),
                            ),
                        )

                        outbound_msg = OutboundMessage(
                            channel=sk.channel,
                            recipient_id=sk.peer_id,
                            user_id="sandbox",
                            content=msg_text,
                            components=components,
                            priority=MessagePriority.SYSTEM,
                        )

                        gw = get_channel_gateway()
                        # Publish via message bus instead of directly blocking
                        await gw.publish(outbound_msg)
                        logger.info("Pushed Native Approval Block to channel '%s' for recipient '%s'", sk.channel, sk.peer_id)
            except Exception as e:
                logger.error("Failed to push Native Approval Block to channel: %s", e)

        return record

    @classmethod
    async def resolve_approval(
        cls, approval_id: str, decision: str, edited_payload: dict[str, object] | None = None
    ) -> ApprovalRecord | None:
        """Resolve an approval and return the record for further processing.

        Args:
            decision: 'approve' or 'deny'
        """
        async with get_session() as db:
            stmt = select(ApprovalRecord).where(ApprovalRecord.id == approval_id)
            result = await db.execute(stmt)
            record = result.scalar_one_or_none()

            if not record:
                return None

            record.status = "APPROVED" if decision == "approve" else "REJECTED"
            record.resolved_at = datetime.now(timezone.utc)

            if edited_payload:
                # Merge the edited fields into the original payload
                new_payload = dict(record.payload)
                new_payload.update(edited_payload)
                record.payload = new_payload

            await db.commit()
            await db.refresh(record)
            return record

    @classmethod
    async def list_pending(cls, limit: int = 50, offset: int = 0) -> list[ApprovalRecord]:
        async with get_session() as db:
            stmt = (
                select(ApprovalRecord)
                .where(ApprovalRecord.status == "PENDING")
                .order_by(ApprovalRecord.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
            result = await db.execute(stmt)
            return list(result.scalars().all())
