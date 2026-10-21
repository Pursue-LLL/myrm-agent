"""强类型失败分级裁决、同会话就地三明治压缩自适应重试全套自动化测试套件。

全面覆盖：
1. 确定性优先级规则（401 包含 'out of funds' 强制判定为 AUTH 而非 QUOTA）
2. 额度耗尽 (QUOTA) 与配置缺失 (MISSING_CONFIG) 即刻熔断 (RETRY_NONE)
3. 瞬态限流 (RATE_LIMIT) 与 5xx 服务端错误进入同会话退避重试 (RETRY_RESUME)
4. 上下文超限 (CONTEXT_OVERFLOW) 触发同会话就地压缩协议 (RETRY_COMPRESS_THEN_RESUME)
5. 终极铁律测试：就地压缩绝对保持同一会话 ID（A retried bot turn NEVER mints a fresh session）
6. 弹性重试治理器 (ResilientRetryGovernor) 指数退避抖动与预算耗尽安全熔断
"""

from __future__ import annotations

from myrm_agent_harness.agent.resilience.failure_reasons import (
    RetryDisposition,
    TypedFailureClassifier,
    TypedFailureReason,
)
from myrm_agent_harness.agent.resilience.in_session_compactor import (
    InSessionTrajectoryCompactor,
)
from myrm_agent_harness.agent.resilience.retry_governor import (
    ResilientRetryGovernor,
)


def test_typed_failure_classifier_auth_precedence_over_quota() -> None:
    """测试确定性优先级：Anthropic 401 包含'out of funds'时，强制判定为 AUTH 而非 QUOTA。"""
    # 典型高危歧义错误体
    ambiguous_err = (
        "Error code: 401 - {'error': {'type': 'authentication_error', "
        "'message': 'invalid, blocked or out of funds'}}"
    )
    assessment = TypedFailureClassifier.classify(ambiguous_err, http_status=401)

    assert assessment.reason == TypedFailureReason.PROVIDER_AUTH_OR_ACCESS
    assert assessment.disposition == RetryDisposition.RETRY_NONE
    assert assessment.can_retry is False
    assert assessment.http_status == 401
    assert "身份鉴权失败" in assessment.user_message


def test_typed_failure_classifier_quota_billing() -> None:
    """测试账户欠费与额度耗尽被精准判定为 QUOTA 并立即熔断。"""
    quota_err = "Error code: 402 - {'message': 'insufficient_quota: you exceeded your current quota'}"
    assessment = TypedFailureClassifier.classify(quota_err, http_status=402)

    assert assessment.reason == TypedFailureReason.PROVIDER_QUOTA_LIMIT
    assert assessment.disposition == RetryDisposition.RETRY_NONE
    assert assessment.can_retry is False
    assert "账户额度已耗尽" in assessment.user_message


def test_typed_failure_classifier_rate_limit_transient() -> None:
    """测试 429 速率限制被识别为瞬态错误并建议 RETRY_RESUME。"""
    rate_err = "429 Too Many Requests: TPM limit exceeded for current tier"
    assessment = TypedFailureClassifier.classify(rate_err, http_status=429)

    assert assessment.reason == TypedFailureReason.PROVIDER_RATE_LIMIT
    assert assessment.disposition == RetryDisposition.RETRY_RESUME
    assert assessment.can_retry is True
    assert "速率限制" in assessment.user_message


def test_typed_failure_classifier_context_overflow_disposition() -> None:
    """测试上下文超限被精准分类并触发 RETRY_COMPRESS_THEN_RESUME。"""
    context_err = (
        "InvalidRequestError: This model's maximum context length is 128000 tokens. "
        "However, your messages resulted in 131000 tokens."
    )
    assessment = TypedFailureClassifier.classify(context_err, http_status=400)

    assert assessment.reason == TypedFailureReason.CONTEXT_OVERFLOW
    assert assessment.disposition == RetryDisposition.RETRY_COMPRESS_THEN_RESUME
    assert assessment.can_retry is True
    assert "就地压缩" in assessment.user_message


def test_in_session_trajectory_compactor_sandwich_structure() -> None:
    """测试同会话就地三明治压缩：保持 session_id 绝对不变，保留头尾关键帧，浓缩中程。"""
    session_id = "sess_prod_12345"

    # 构造长轨迹：头部 2 条 + 中程 10 条 + 尾部 4 条
    messages: list[dict[str, str]] = [
        {"role": "system", "content": "You are a senior architect."},
        {"role": "user", "content": "Please implement Item 8 according to guidelines."},
    ]
    for i in range(1, 11):
        messages.append({"role": "assistant", "content": f"Running tool step {i} with detailed execution plan and parameters."})
        messages.append({"role": "tool", "content": f"Tool output for step {i}: [detailed diagnostic trace log...] " + ("DATA_CHUNK_" * 50)})

    messages.append({"role": "assistant", "content": "Inspecting intermediate findings."})
    messages.append({"role": "user", "content": "Please continue with the next fix."})
    messages.append({"role": "assistant", "content": "Executing final validation."})
    messages.append({"role": "tool", "content": "Tests completed with 0 errors."})

    result = InSessionTrajectoryCompactor.compact(
        session_id=session_id,
        messages=messages,
        keep_head_count=2,
        keep_tail_count=4,
    )

    # 1. 终极铁律核验：session_id 必须严格一致！
    assert result.session_id == session_id

    # 2. 压缩结构核验：头 2 条 + 1 条检查点 + 尾 4 条 = 7 条
    assert result.compacted_message_count == 7
    assert result.pruned_message_count == 20
    assert result.compression_ratio < 1.0

    # 3. 头部首条与尾部末条内容完全吻合
    compacted = result.compacted_messages
    assert compacted[0]["role"] == "system"
    assert "senior architect" in compacted[0]["content"]
    assert compacted[1]["role"] == "user"
    assert "Please implement Item 8" in compacted[1]["content"]

    # 中部注入检查点摘要
    assert compacted[2]["role"] == "system"
    assert "[Context Checkpoint: In-Session Compacted Trajectory]" in compacted[2]["content"]

    # 尾部鲜活观测完整保留
    assert compacted[-1]["role"] == "tool"
    assert "Tests completed with 0 errors." in compacted[-1]["content"]


def test_in_session_trajectory_compactor_short_trajectory_idempotent() -> None:
    """测试短轨迹（未超门限）原地幂等返回，不破坏任何结构。"""
    session_id = "sess_short"
    messages: list[dict[str, str]] = [
        {"role": "system", "content": "Prompt"},
        {"role": "user", "content": "Hello"},
    ]
    result = InSessionTrajectoryCompactor.compact(session_id, messages)

    assert result.session_id == session_id
    assert result.compacted_messages == messages
    assert result.pruned_message_count == 0
    assert result.compression_ratio == 1.0


def test_resilient_retry_governor_immediate_circuit_break() -> None:
    """测试治理器对鉴权错误的即刻熔断（should_retry=False, 0s 等待）。"""
    governor = ResilientRetryGovernor(max_retries=3)
    auth_err = "401 Unauthorized: invalid_api_key provided"

    directive = governor.evaluate(auth_err, attempt=1)

    assert directive.should_retry is False
    assert directive.disposition == RetryDisposition.RETRY_NONE
    assert directive.reason == TypedFailureReason.PROVIDER_AUTH_OR_ACCESS
    assert directive.backoff_seconds == 0.0
    assert "身份鉴权失败" in directive.user_guidance


def test_resilient_retry_governor_context_overflow_compaction_pipeline() -> None:
    """测试治理器处理上下文超限：生成新上下文并保持 session_id 严格一致。"""
    governor = ResilientRetryGovernor(max_retries=3)
    context_err = "400 context_length_exceeded: maximum tokens reached"

    raw_context: dict[str, object] = {
        "session_id": "session_marathon_999",
        "messages": [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Initial user goal"},
            {"role": "assistant", "content": "Intermediate work step 1"},
            {"role": "tool", "content": "Intermediate tool data 1"},
            {"role": "assistant", "content": "Intermediate work step 2"},
            {"role": "tool", "content": "Intermediate tool data 2"},
            {"role": "assistant", "content": "Recent thinking"},
            {"role": "tool", "content": "Recent observation"},
            {"role": "user", "content": "Next turn prompt"},
            {"role": "assistant", "content": "Final step"},
        ],
    }

    directive = governor.evaluate(context_err, attempt=1, context=raw_context)

    assert directive.should_retry is True
    assert directive.disposition == RetryDisposition.RETRY_COMPRESS_THEN_RESUME
    assert directive.compacted_context is not None

    # 验证新上下文严格保留原 session_id
    assert directive.compacted_context["session_id"] == "session_marathon_999"
    assert directive.compacted_context["_in_session_compacted"] is True
    compacted_msgs = directive.compacted_context["messages"]
    raw_msgs = raw_context["messages"]
    assert isinstance(compacted_msgs, list)
    assert isinstance(raw_msgs, list)
    assert len(compacted_msgs) < len(raw_msgs)  # 成功瘦身


def test_resilient_retry_governor_exponential_backoff_and_exhaustion() -> None:
    """测试瞬态错误指数退避递增与超过预算时的安全终止。"""
    governor = ResilientRetryGovernor(
        max_retries=3,
        base_backoff_seconds=1.0,
        enable_jitter=False,
    )
    transient_err = "503 Service Unavailable: overloaded"

    # 尝试 1 -> 应当重试，退避 1.0s
    d1 = governor.evaluate(transient_err, attempt=1)
    assert d1.should_retry is True
    assert d1.backoff_seconds == 1.0

    # 尝试 2 -> 应当重试，退避 2.0s
    d2 = governor.evaluate(transient_err, attempt=2)
    assert d2.should_retry is True
    assert d2.backoff_seconds == 2.0

    # 尝试 3 -> 已达到最大尝试次数，停止重试
    d3 = governor.evaluate(transient_err, attempt=3)
    assert d3.should_retry is False
    assert "重试上限" in d3.user_guidance
