"""Batch Audit Log Repository

CRUD operations for batch optimization audit logs.
"""

import logging
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.skill_optimization.batch_audit_log import BatchAuditLog

logger = logging.getLogger(__name__)


class AuditLogRepository:
    """批量优化审计日志Repository"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_log(
        self,
        batch_id: str,
        operation: str,
        status: str,
        details: dict[str, object] | None = None,
        user_id: str | None = None,
        error_message: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> BatchAuditLog:
        """创建审计日志

        Args:
            batch_id: Batch task ID
            operation: Operation type (create/start/complete/cancel/rollback)
            status: Operation status (success/failure)
            details: Operation details
            user_id: User who performed the operation
            error_message: Error message if operation failed
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            BatchAuditLog: Created audit log record
        """
        log = BatchAuditLog(
            log_id=str(uuid4()),
            batch_id=batch_id,
            user_id=user_id,
            operation=operation,
            status=status,
            details=details or {},
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(log)
        await self.session.commit()
        await self.session.refresh(log)
        logger.info(f"Created audit log {log.log_id} for batch {batch_id}: {operation} - {status}")
        return log

    async def get_batch_logs(self, batch_id: str) -> list[BatchAuditLog]:
        """获取批量任务的所有审计日志

        Args:
            batch_id: Batch task ID

        Returns:
            list[BatchAuditLog]: All audit logs for the batch
        """
        result = await self.session.execute(
            select(BatchAuditLog).where(BatchAuditLog.batch_id == batch_id).order_by(desc(BatchAuditLog.created_at))
        )
        return list(result.scalars().all())

    async def get_user_logs(self, user_id: str, limit: int = 50) -> list[BatchAuditLog]:
        """获取用户的审计日志

        Args:
            user_id: User ID
            limit: Maximum number of records

        Returns:
            list[BatchAuditLog]: User's audit logs
        """
        result = await self.session.execute(select(BatchAuditLog).order_by(desc(BatchAuditLog.created_at)).limit(limit))
        return list(result.scalars().all())

    async def get_recent_logs(self, limit: int = 50) -> list[BatchAuditLog]:
        """获取最近的审计日志

        Args:
            limit: Maximum number of records

        Returns:
            list[BatchAuditLog]: Recent audit logs
        """
        result = await self.session.execute(select(BatchAuditLog).order_by(desc(BatchAuditLog.created_at)).limit(limit))
        return list(result.scalars().all())

    async def get_failed_operations(self, limit: int = 50) -> list[BatchAuditLog]:
        """获取失败的操作日志

        Args:
            limit: Maximum number of records

        Returns:
            list[BatchAuditLog]: Failed operation logs
        """
        result = await self.session.execute(
            select(BatchAuditLog).where(BatchAuditLog.status == "failure").order_by(desc(BatchAuditLog.created_at)).limit(limit)
        )
        return list(result.scalars().all())
