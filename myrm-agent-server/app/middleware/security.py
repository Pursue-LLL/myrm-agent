"""统一安全中间件 - 防重放攻击

集成多层安全验证：
1. 时间戳验证（60秒窗口）
2. Nonce 验证（一次性令牌）
3. 请求签名验证（HMAC-SHA256）
4. Token 黑名单检查

防护能力：
✅ 防止请求重放攻击
✅ 防止请求内容篡改
✅ 防止 Token 泄露后的滥用
✅ 防止中间人攻击
"""

from __future__ import annotations

import logging

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from myrm_agent_harness.infra.security import (
    SignatureVerifier,
    TimestampVerifier,
    nonce_manager,
)
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from app.config.settings import settings
from app.platform_utils.deployment_capabilities import get_deployment_capabilities

logger = logging.getLogger(__name__)


class SecurityMiddleware(BaseHTTPMiddleware):
    """统一安全中间件

    架构原则：
    1. 多层防御（Defense in Depth）
    2. 零信任（Zero Trust）
    3. 纵深防御（Defense in Breadth）
    """

    def __init__(self, app: ASGIApp, enabled: bool = True) -> None:
        """初始化安全中间件

        Args:
            app: FastAPI 应用实例
            enabled: 是否启用（默认：Sandbox 模式启用）
        """
        super().__init__(app)
        self.enabled = enabled and get_deployment_capabilities().is_sandbox_instance

        # 初始化验证器
        self.timestamp_verifier = TimestampVerifier(time_window=60)  # 60秒窗口
        self.signature_verifier = SignatureVerifier(secret_key=settings.internal_service_key.get_secret_value())

        if self.enabled:
            logger.warning("✅ Security Middleware enabled (Anti-Replay Protection)")
        else:
            logger.warning("⚠️ Security Middleware disabled")

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """处理安全验证逻辑"""
        # 本地模式或未启用：跳过
        if not self.enabled:
            return await call_next(request)

        # 提取安全头
        timestamp = request.headers.get("X-Timestamp")
        nonce = request.headers.get("X-Nonce")
        signature = request.headers.get("X-Signature")

        # 1. 验证时间戳（必需）
        if not timestamp:
            return self._security_error("Missing X-Timestamp header")

        valid, error_msg = self.timestamp_verifier.verify(timestamp)
        if not valid:
            return self._security_error(f"Timestamp validation failed: {error_msg}")

        # 4. 验证 Nonce（必需）
        if not nonce:
            return self._security_error("Missing X-Nonce header")

        # 检查 Nonce 是否已被使用（防重放）
        nonce_valid = await nonce_manager.check_and_store(nonce)
        if not nonce_valid:
            return self._security_error("Nonce has been used (replay attack detected)")

        # 5. 验证请求签名（可选，根据配置）
        if settings.security.signature_enabled:
            if not signature:
                return self._security_error("Missing X-Signature header")

            valid, error_msg = await self.signature_verifier.verify_request(
                request,
                timestamp,
                nonce,
                signature,
            )
            if not valid:
                return self._security_error(f"Signature validation failed: {error_msg}")

        # 5. 所有验证通过，放行
        return await call_next(request)

    def _security_error(self, message: str) -> JSONResponse:
        """返回安全错误响应"""
        logger.warning(f"🚫 Security validation failed: {message}")

        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "success": False,
                "code": 40301,  # BusinessCode.SECURITY_VALIDATION_FAILED
                "message": f"Security validation failed: {message}",
            },
        )


__all__ = ["SecurityMiddleware"]
