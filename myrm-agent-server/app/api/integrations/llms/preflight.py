"""[OUTPUT]
preflight endpoints.

[POS]
Model switch preflight: context-window fit and compaction estimate.
"""

from __future__ import annotations

import asyncio

from fastapi.responses import JSONResponse
from myrm_agent_harness.toolkits.llms.catalog import model_facts
from pydantic import BaseModel, Field

from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse

from .common import router


class ModelSwitchPreflightItem(BaseModel):
    """模型切换压缩预检输入项"""

    model: str = Field(..., description="目标模型名（provider/model 格式）")
    max_input_tokens: int | None = Field(
        default=None,
        description="目标模型上下文窗口（前端能力探测结果）；缺省时后端尝试解析",
    )


class ModelSwitchPreflightRequest(BaseModel):
    """模型切换压缩预检请求"""

    estimated_tokens: int = Field(..., gt=0, description="当前会话估算 tokens")
    compress_start_ratio: float | None = Field(
        default=None,
        description="显式压缩起始比例（agent 引擎配置）；缺省按目标模型 tier 推断。"
        "越界值由 harness ContextConfig 内部 clamp 到 [0.20, 0.85]，与运行时口径一致",
    )
    prompt_mode: str | None = Field(
        default=None,
        description="agent prompt 模式（full/lean/naked/search）。仅 full 或未配置时按模型 tier 推断压缩比例，"
        "否则回退默认 0.5，与 factory._apply_small_model_tuning 的触发条件保持一致",
    )
    turn_count: int | None = Field(
        default=None,
        ge=0,
        description="当前会话 human 消息数（轮数）。提供时按运行时动态阈值判定压缩（长会话阈值收紧），"
        "与 compress_processor 的 calculate_dynamic_thresholds 口径一致；缺省回退静态阈值",
    )
    chat_id: str | None = Field(
        default=None,
        description="当前会话 ID。提供时预检消费压缩无效 streak（anti-thrash）："
        "streak>=2 且当前 tokens<目标窗口 90% 时判定不会压缩，与运行时 "
        "should_block_automatic_compression 语义一致，避免对已跳过的压缩误报预警",
    )
    models: list[ModelSwitchPreflightItem] = Field(..., description="目标模型列表")


class ModelSwitchPreflightResult(BaseModel):
    """模型切换压缩预检结果"""

    model: str = Field(..., description="目标模型名")
    found: bool = Field(default=False, description="是否成功解析目标窗口")
    new_window: int | None = Field(default=None, description="目标模型上下文窗口")
    compress_threshold: int | None = Field(default=None, description="切换后压缩触发阈值")
    will_compress: bool = Field(default=False, description="切换后下一条消息将触发压缩")


def _resolve_target_max_input_tokens(
    model: str,
    fallback: int | None,
) -> int | None:
    """Resolve the target model context window for preflight checks.

    Priority: explicit frontend capability value > model catalog.
    Returns None when the window is unknown (caller skips the warning).
    """
    if isinstance(fallback, int) and fallback > 0:
        return fallback
    window = (model_facts(model) or {}).get("max_input_tokens")
    return int(window) if isinstance(window, (int, float)) and window > 0 else None


@router.post("/model-switch-preflight", response_model=StandardSuccessResponse)
async def model_switch_preflight(request: ModelSwitchPreflightRequest) -> JSONResponse:
    """
    模型切换压缩预检

    计算切换到目标模型后是否会在下一条消息立即触发上下文压缩。
    复用 harness ContextConfig 的真实压缩阈值公式，避免前端硬编码导致口径漂移。
    compress_start_ratio 缺省且 agent 为 full prompt 模式时，按目标模型 tier
    （STRONG/MEDIUM/WEAK）推断，与 factory._apply_small_model_tuning 的压缩起点口径一致；
    非 full 模式（lean/naked/search）下 _apply_small_model_tuning 不生效，回退默认 0.5。
    传入 turn_count 时复用 harness ContextBudget 的动态阈值（长会话按紧张度收紧阈值），
    与 compress_processor 的阈值计算口径一致。已知边界：运行时 eco_mode（预算压力阈值
    ×0.80，compress 实际触发更早）与 hot cache bypass（5 分钟活跃跳过压缩）为瞬态运行时
    状态，前端无法预知，预检不模拟。方向：eco_mode 下预检用未打折阈值判定，边界场景可能
    漏报（运行时会压缩但预检判定不压缩）；hot cache 下预检可能略早（运行时会跳过压缩）。
    预检判定与文案已按「可能触发」措辞，不做确定性断言。
    传入 chat_id 时消费压缩无效 streak（anti-thrash）：streak>=2 且当前 tokens<目标窗口 90%
    时判定不会压缩，与运行时 should_block_automatic_compression 语义一致，避免对运行时已
    跳过的无效压缩误报预警；streak>=2 但 tokens>=90% 窗口（防 OOM 强制压缩）仍判定会压缩。

    Returns:
        每个目标模型的窗口、压缩阈值与 will_compress 判定
    """
    from myrm_agent_harness.agent.context_management.infra.context_budget import (
        DEFAULT_ESTIMATED_REMAINING_TURNS,
        ContextBudget,
    )
    from myrm_agent_harness.agent.context_management.infra.schemas import ContextConfig
    from myrm_agent_harness.agent.context_management.strategies.compression.compression_anti_thrash_guard import (
        ANTI_THRASHING_STREAK_LIMIT,
        SAFETY_NET_RATIO,
    )
    from myrm_agent_harness.agent.context_management.strategies.compression.compression_streak_store import (
        get_compression_streak_store,
    )
    from myrm_agent_harness.core.config.model_tier import ModelTier, infer_model_tier

    ineffective_streak = (
        await asyncio.to_thread(get_compression_streak_store().get_streak, request.chat_id) if request.chat_id else 0
    )
    results: list[dict[str, object]] = []
    for item in request.models:
        window = _resolve_target_max_input_tokens(item.model, item.max_input_tokens)
        if window is None:
            results.append(ModelSwitchPreflightResult(model=item.model).model_dump())
            continue

        ratio = request.compress_start_ratio
        if ratio is None and request.prompt_mode in (None, "full"):
            tier = infer_model_tier(item.model, max_context_tokens=window)
            if tier == ModelTier.WEAK:
                ratio = 0.30
            elif tier == ModelTier.MEDIUM:
                ratio = 0.50
            # STRONG -> ratio None -> 默认 0.5 压缩阈值

        cfg = ContextConfig(max_context_tokens=window, compress_start_ratio=ratio)
        threshold = cfg.compress_threshold
        if request.turn_count is not None:
            budget = ContextBudget(
                current_tokens=request.estimated_tokens,
                compress_threshold=cfg.compress_threshold,
                summarize_threshold=cfg.summarize_trigger_threshold,
                config=cfg,
            )
            threshold, _ = budget.calculate_dynamic_thresholds(
                turn_count=request.turn_count,
                estimated_remaining_turns=DEFAULT_ESTIMATED_REMAINING_TURNS,
            )

        anti_thrash_blocked = ineffective_streak >= ANTI_THRASHING_STREAK_LIMIT and request.estimated_tokens < int(
            window * SAFETY_NET_RATIO
        )
        will_compress = not anti_thrash_blocked and request.estimated_tokens >= threshold

        results.append(
            ModelSwitchPreflightResult(
                model=item.model,
                found=True,
                new_window=window,
                compress_threshold=threshold,
                will_compress=will_compress,
            ).model_dump()
        )

    return success_response(data={"results": results})
