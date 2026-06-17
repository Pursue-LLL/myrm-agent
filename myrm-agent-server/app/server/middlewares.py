from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.core.infra.cors_validator import CORS_ORIGINS_DEFAULT, parse_and_validate_cors_origins
from app.middleware.auth import AuthMiddleware
from app.middleware.cache import CacheControlMiddleware
from app.middleware.host_allowlist import HostAllowlistMiddleware
from app.middleware.ingress import PublicIngressMiddleware
from app.middleware.max_body_size import MaxBodySizeMiddleware
from app.middleware.session_idle import SessionIdleMiddleware
from app.middleware.text_sanitizer_middleware import TextSanitizerMiddleware
from app.middleware.webhook_security import RawBodyLimitMiddleware
from app.middleware.ws_auth import WsAuthMiddleware


def register_middlewares(app: FastAPI) -> None:
    """Register global middlewares."""
    # 中间件注册顺序（LIFO）：CORS → MaxBodySize → RawBodyLimit → Cache → Auth → TextSanitizer
    # 实际执行顺序：TextSanitizer → Auth → Cache → RawBodyLimit → MaxBodySize → CORS
    app.add_middleware(TextSanitizerMiddleware)
    app.add_middleware(HostAllowlistMiddleware)
    app.add_middleware(SessionIdleMiddleware)
    app.add_middleware(AuthMiddleware)
    app.add_middleware(WsAuthMiddleware)
    app.add_middleware(CacheControlMiddleware)
    app.add_middleware(RawBodyLimitMiddleware, max_size=1024 * 1024)
    app.add_middleware(MaxBodySizeMiddleware, max_size=15 * 1024 * 1024)  # 全局 15MB 熔断器

    # CORS 最后注册，最先执行（处理 OPTIONS 预检）
    cors_origins = parse_and_validate_cors_origins(settings.cors_origins or CORS_ORIGINS_DEFAULT)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        max_age=600,
    )

    # Public Ingress Middleware 最后注册，处于洋葱模型的最外层。
    # 它在请求进入框架路由或 CORS 处理之前，修正反向代理丢失的 Host/Scheme
    app.add_middleware(PublicIngressMiddleware)
