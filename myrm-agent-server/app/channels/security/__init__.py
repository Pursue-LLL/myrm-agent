"""Webhook security protocols and middleware.

[INPUT]
(No external dependencies, pure protocol definitions)

[OUTPUT]
Protocol：
- SignatureVerifier: SignatureValidateProtocol
- IdempotencyStore: 幂 etc.性StorageProtocol
- MetricsCollector: SecurityMetrics收集Protocol（ using ObjectParameter）
- FallbackStrategy: degradationStrategyProtocol
- FallbackMode: degradationMode枚举

Data类（Result）：
- VerificationResult: SignatureValidateResult（强Type）
- IdempotencyResult: 幂 etc.性CheckResult（强Type）

Data类（Metrics）：
- WebhookMetrics: SuccessRequestMetrics封装
- WebhookFailure: FailureRequest详情封装

Data类（Config）：
- SecurityLimits: Security限流Configure（7Parameter分组）
- IpPolicy: IPStrategyConfigure（黑Whitelist+TrustedProxy）
- SecurityProtocols: SecurityProtocolConfigure（4个ProtocolInstance分组）

Data类（Context）：
- FallbackEvent: degradation事件Record
- WebhookContext: Validate后 Request上下文

Exception：
- WebhookResponseError: standard化ErrorResponse（RFC 7807/6585/7231，trace_id + retry_after）
- SecurityViolationError: Security违规Exception

 in 间件：
- WebhookSecurityMiddleware: 统一Security in 间件（ using 3组ConfigureObject）

ToolFunction：
- extract_real_ip: ExtractrealClientIP
- is_ip_blocked: IPBlacklistCheck
- is_ip_allowed: IPWhitelistCheck
- validate_host: Host HeaderValidate

[POS]
Webhook security layer. Defines inbound security protocols (signature verification,
idempotency, metrics, degradation). Provides out-of-the-box security middleware.
Business layer injects platform-specific logic via protocols.PI。
"""

from .context import FallbackEvent, IdempotencyResult, VerificationResult, WebhookContext
from .errors import SecurityViolationError, WebhookResponseError
from .ip_utils import extract_real_ip, is_ip_allowed, is_ip_blocked, validate_host
from .protocols import (
    FallbackMode,
    FallbackStrategy,
    IdempotencyStore,
    IpPolicy,
    MetricsCollector,
    SecurityLimits,
    SecurityProtocols,
    SignatureVerifier,
    WebhookFailure,
    WebhookMetrics,
)
from .webhook_middleware import WebhookSecurityMiddleware

__all__ = [
    # Protocol
    "SignatureVerifier",
    "IdempotencyStore",
    "MetricsCollector",
    "FallbackStrategy",
    "FallbackMode",
    # ResultData类
    "VerificationResult",
    "IdempotencyResult",
    # MetricsData类
    "WebhookMetrics",
    "WebhookFailure",
    # ConfigData类
    "SecurityLimits",
    "IpPolicy",
    "SecurityProtocols",
    # ContextData类
    "FallbackEvent",
    "WebhookContext",
    # Exception
    "WebhookResponseError",
    "SecurityViolationError",
    #  in 间件
    "WebhookSecurityMiddleware",
    # ToolFunction
    "extract_real_ip",
    "is_ip_blocked",
    "is_ip_allowed",
    "validate_host",
]
