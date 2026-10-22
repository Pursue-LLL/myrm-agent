"""Model Overrides Registry & Context Pricing Engine.

[INPUT]
- services.models.overrides.model_overrides_types::ModelOverrideItem, PreloadedModelSku, Currency, etc.
- pathlib.Path, json, logging

[OUTPUT]
- ModelOverridesRegistry: Singleton service managing persistent model overrides, preloaded SKUs, and BYOK cost calculation
- model_overrides_registry: Global instance

[POS]
Core business logic implementing Hermes Agent v0.21.0 model_overrides parity.
Enables instant customization of context bounds, max output tokens, and BYOK token economics.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Final

from app.services.models.overrides.model_overrides_types import (
    CostEstimationRequest,
    CostEstimationResponse,
    Currency,
    ModelOverrideItem,
    PreloadedModelSku,
)

logger = logging.getLogger(__name__)

# Preloaded catalog representing modern 2026 models for one-click cloning
PRELOADED_2026_SKUS: Final[tuple[PreloadedModelSku, ...]] = (
    PreloadedModelSku(
        model_id="glm-5.3-flash",
        display_name="GLM-5.3 Flash",
        provider="Zhipu AI",
        default_context_window=131_072,
        default_max_output_tokens=8_192,
        suggested_input_cost_per_mtoken=0.10,
        suggested_output_cost_per_mtoken=0.10,
        currency=Currency.CNY,
        recommended_use_case="Ultra-fast tool orchestration and high-concurrency coding assistance",
    ),
    PreloadedModelSku(
        model_id="qwen-3.8-max",
        display_name="Qwen 3.8 Max",
        provider="Alibaba Cloud",
        default_context_window=131_072,
        default_max_output_tokens=16_384,
        suggested_input_cost_per_mtoken=0.40,
        suggested_output_cost_per_mtoken=1.20,
        currency=Currency.CNY,
        recommended_use_case="Complex reasoning, long document synthesis, and rigorous architecture auditing",
    ),
    PreloadedModelSku(
        model_id="qwen-3.8-flash",
        display_name="Qwen 3.8 Flash",
        provider="Alibaba Cloud",
        default_context_window=1_000_000,
        default_max_output_tokens=8_192,
        suggested_input_cost_per_mtoken=0.05,
        suggested_output_cost_per_mtoken=0.15,
        currency=Currency.CNY,
        recommended_use_case="Million-token context window with sub-second time-to-first-token",
    ),
    PreloadedModelSku(
        model_id="gemini-3.7-flash",
        display_name="Gemini 3.7 Flash",
        provider="Google DeepMind",
        default_context_window=1_048_576,
        default_max_output_tokens=8_192,
        suggested_input_cost_per_mtoken=0.075,
        suggested_output_cost_per_mtoken=0.30,
        currency=Currency.USD,
        recommended_use_case="Native multimodal 1M context analysis with continuous reasoning",
    ),
    PreloadedModelSku(
        model_id="minimax-m3",
        display_name="MiniMax M3",
        provider="MiniMax",
        default_context_window=262_144,
        default_max_output_tokens=8_192,
        suggested_input_cost_per_mtoken=0.15,
        suggested_output_cost_per_mtoken=0.60,
        currency=Currency.CNY,
        recommended_use_case="Long context narrative comprehension and conversational depth",
    ),
    PreloadedModelSku(
        model_id="deepseek-v3",
        display_name="DeepSeek V3",
        provider="DeepSeek",
        default_context_window=131_072,
        default_max_output_tokens=8_192,
        suggested_input_cost_per_mtoken=0.14,
        suggested_output_cost_per_mtoken=0.28,
        currency=Currency.USD,
        recommended_use_case="State-of-the-art open weights coding and engineering workflows",
    ),
)


class ModelOverridesRegistry:
    """Registry coordinating persistent model configuration overrides and BYOK pricing."""

    def __init__(self, persistence_file: Path | str | None = None) -> None:
        self._persistence_file: Path = (
            Path(persistence_file) if persistence_file else Path.cwd() / ".myrm" / "model_overrides.json"
        )
        self._overrides: dict[str, ModelOverrideItem] = {}
        self._load_from_disk()

    def list_overrides(self) -> list[ModelOverrideItem]:
        """Return all registered model override entries."""
        return list(self._overrides.values())

    def get_override(self, model_id: str) -> ModelOverrideItem | None:
        """Fetch override configuration for a specific model."""
        return self._overrides.get(model_id)

    def upsert_override(self, override: ModelOverrideItem) -> ModelOverrideItem:
        """Create or update a model override configuration."""
        self._overrides[override.model_id] = override
        self._save_to_disk()
        return override

    def delete_override(self, model_id: str) -> bool:
        """Delete an existing override configuration."""
        if model_id in self._overrides:
            del self._overrides[model_id]
            self._save_to_disk()
            return True
        return False

    def get_preloaded_skus(self) -> list[PreloadedModelSku]:
        """Return collection of modern 2026 pre-calibrated baseline models."""
        return list(PRELOADED_2026_SKUS)

    def resolve_effective_context_window(self, model_id: str, default_window: int = 128_000) -> int:
        """Calculate effective context window taking user override into account."""
        item = self._overrides.get(model_id)
        if item and item.enabled and item.custom_context_window:
            return item.custom_context_window

        # Check preloaded baseline fallback
        for sku in PRELOADED_2026_SKUS:
            if sku.model_id == model_id:
                return sku.default_context_window

        return default_window

    def resolve_effective_pricing(self, model_id: str) -> tuple[float, float, Currency, bool]:
        """Resolve effective input/output pricing and currency.

        Returns:
            Tuple of (input_cost_per_mtoken, output_cost_per_mtoken, currency, is_overridden)
        """
        item = self._overrides.get(model_id)
        if item and item.enabled:
            input_cost = item.input_cost_per_mtoken if item.input_cost_per_mtoken is not None else 0.50
            output_cost = item.output_cost_per_mtoken if item.output_cost_per_mtoken is not None else 1.50
            return (input_cost, output_cost, item.currency, True)

        for sku in PRELOADED_2026_SKUS:
            if sku.model_id == model_id:
                return (
                    sku.suggested_input_cost_per_mtoken,
                    sku.suggested_output_cost_per_mtoken,
                    sku.currency,
                    False,
                )

        return (0.50, 1.50, Currency.USD, False)

    def estimate_cost(self, request: CostEstimationRequest) -> CostEstimationResponse:
        """Calculate accurate BYOK token cost using effective pricing matrices."""
        input_price, output_price, currency, is_overridden = self.resolve_effective_pricing(request.model_id)

        input_cost = round((request.input_tokens / 1_000_000) * input_price, 6)
        output_cost = round((request.output_tokens / 1_000_000) * output_price, 6)
        total_cost = round(input_cost + output_cost, 6)

        return CostEstimationResponse(
            model_id=request.model_id,
            input_tokens=request.input_tokens,
            output_tokens=request.output_tokens,
            input_cost=input_cost,
            output_cost=output_cost,
            total_cost=total_cost,
            currency=currency,
            is_overridden=is_overridden,
        )

    def _load_from_disk(self) -> None:
        """Load stored overrides from JSON file."""
        if not self._persistence_file.exists():
            return
        try:
            content = self._persistence_file.read_text(encoding="utf-8")
            data: dict[str, dict[str, str | int | float | bool | None]] = json.loads(content)
            for model_id, item_dict in data.items():
                self._overrides[model_id] = ModelOverrideItem(**item_dict)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to load model overrides from disk: %s", exc)

    def _save_to_disk(self) -> None:
        """Persist current overrides to JSON file."""
        try:
            self._persistence_file.parent.mkdir(parents=True, exist_ok=True)
            serialized: dict[str, dict[str, str | int | float | bool | None]] = {
                k: v.model_dump() for k, v in self._overrides.items()
            }
            self._persistence_file.write_text(
                json.dumps(serialized, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to save model overrides to disk: %s", exc)


# Global singleton instance
model_overrides_registry: Final[ModelOverridesRegistry] = ModelOverridesRegistry()
