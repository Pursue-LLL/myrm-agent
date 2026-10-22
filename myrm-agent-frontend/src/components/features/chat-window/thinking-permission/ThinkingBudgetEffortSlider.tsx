'use client';

/**
 * [INPUT]
 * - thinkingPermissionTypes::ThinkingEffortLevel, THINKING_BUDGET_TIERS (POS: Budget tiers contract.)
 * - useThinkingBudgetStore::useThinkingBudgetStore (POS: Reactive thinking budget store.)
 * - lucide-react::BrainCircuit, SlidersHorizontal, Info (POS: Vector icons.)
 *
 * [OUTPUT]
 * - ThinkingBudgetEffortSlider: 5-tier fluid slider for model reasoning budget and effort control.
 *
 * [POS]
 * Embedded input toolbar widget allowing knowledge workers to tune reasoning depth
 * (Off / 2k / 8k / 16k / 32k) to strike the perfect balance between latency, cost, and depth.
 */

import React, { useEffect, useId, useMemo, useState } from 'react';
import { BrainCircuit, Info } from 'lucide-react';
import {
  type ThinkingEffortLevel,
  THINKING_BUDGET_TIERS,
} from './thinkingPermissionTypes';
import { useThinkingBudgetStore } from './useThinkingBudgetStore';
import useChatStore from '@/store/useChatStore';
import useProviderStore from '@/store/useProviderStore';
import { resolveActiveModelSelection } from '@/lib/model-binding';
import { detectReasoningSupport } from '@/lib/reasoning-model-detection';

export interface ThinkingBudgetEffortSliderProps {
  modelName?: string;
  supportsReasoning?: boolean;
  className?: string;
  disabled?: boolean;
}

const TIER_INDEX_MAP: Record<ThinkingEffortLevel, number> = {
  off: 0,
  low: 1,
  medium: 2,
  high: 3,
  max: 4,
};

const INDEX_TO_TIER: readonly ThinkingEffortLevel[] = ['off', 'low', 'medium', 'high', 'max'];

export default function ThinkingBudgetEffortSlider({
  modelName,
  supportsReasoning,
  className = '',
  disabled = false,
}: ThinkingBudgetEffortSliderProps) {
  const sliderId = useId();
  const actionMode = useChatStore((state) => state.actionMode);
  const agentConfig = useChatStore((state) => state.agentConfig);
  const defaultModelConfig = useProviderStore((state) => state.defaultModelConfig);
  const providers = useProviderStore((state) => state.providers);

  const resolvedModelName = useMemo(() => {
    if (modelName) {
      return modelName;
    }
    const selection = resolveActiveModelSelection(actionMode, agentConfig, defaultModelConfig, providers);
    return selection?.model ?? '';
  }, [modelName, actionMode, agentConfig, defaultModelConfig, providers]);

  const resolvedSupportsReasoning = useMemo(
    () => detectReasoningSupport(resolvedModelName, supportsReasoning),
    [supportsReasoning, resolvedModelName],
  );

  const currentLevel = useThinkingBudgetStore((state) => state.level);
  const setLevel = useThinkingBudgetStore((state) => state.setLevel);
  const hydrateForModel = useThinkingBudgetStore((state) => state.hydrateForModel);

  const [hoveredLevel, setHoveredLevel] = useState<ThinkingEffortLevel | null>(null);

  useEffect(() => {
    if (resolvedModelName) {
      hydrateForModel(resolvedModelName);
    }
  }, [resolvedModelName, hydrateForModel]);

  const activeIndex = TIER_INDEX_MAP[currentLevel] ?? 0;
  const activeTierConfig = useMemo(() => {
    const active = THINKING_BUDGET_TIERS.find((t) => t.level === currentLevel);
    return active ?? THINKING_BUDGET_TIERS[0];
  }, [currentLevel]);

  const displayTier = useMemo(() => {
    if (hoveredLevel) {
      return THINKING_BUDGET_TIERS.find((t) => t.level === hoveredLevel) ?? activeTierConfig;
    }
    return activeTierConfig;
  }, [hoveredLevel, activeTierConfig]);

  const isActuallyDisabled = disabled || !resolvedSupportsReasoning;

  const handleSliderChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    if (isActuallyDisabled) {
      return;
    }
    const idx = Number.parseInt(event.target.value, 10);
    const targetTier = INDEX_TO_TIER[idx] ?? 'off';
    setLevel(targetTier, resolvedModelName);
  };

  const handleStepClick = (tier: ThinkingEffortLevel) => {
    if (isActuallyDisabled) {
      return;
    }
    setLevel(tier, resolvedModelName);
  };

  return (
    <div
      data-testid="thinking-budget-effort-slider"
      className={`relative inline-flex items-center gap-2 px-2 py-1 rounded-md border border-border/40 bg-background/80 shadow-xs backdrop-blur-xs select-none transition-all ${
        isActuallyDisabled ? 'opacity-50 cursor-not-allowed' : ''
      } ${className}`}
    >
      <div className="flex items-center gap-1.5 shrink-0">
        <BrainCircuit
          className={`w-3.5 h-3.5 transition-colors ${
            !isActuallyDisabled && currentLevel !== 'off'
              ? activeTierConfig.activeColorClass
              : 'text-muted-foreground'
          }`}
          aria-hidden="true"
        />
        <span className="text-xs font-medium text-foreground">思考深度</span>
      </div>

      {isActuallyDisabled ? (
        <div className="flex items-center gap-1 text-[11px] text-muted-foreground" title="当前模型不支持思考预算调节">
          <span className="italic">不支持</span>
          <Info className="w-3 h-3 opacity-70" />
        </div>
      ) : (
        <div className="flex items-center gap-2">
          {/* Native range slider for smooth touch & keyboard a11y */}
          <div className="relative flex items-center w-24">
            <label htmlFor={sliderId} className="sr-only">
              思考深度滑块（0k 到 32k）
            </label>
            <input
              id={sliderId}
              type="range"
              min={0}
              max={4}
              step={1}
              value={activeIndex}
              onChange={handleSliderChange}
              disabled={isActuallyDisabled}
              aria-label="调节思考推理预算"
              data-testid="thinking-range-input"
              className="w-full h-1.5 bg-muted rounded-lg appearance-none cursor-pointer accent-primary focus:outline-hidden focus:ring-1 focus:ring-ring"
            />
          </div>

          {/* Quick step pills */}
          <div className="flex items-center gap-0.5">
            {THINKING_BUDGET_TIERS.map((tier) => {
              const isSelected = tier.level === currentLevel;
              return (
                <button
                  key={tier.level}
                  type="button"
                  data-testid={`thinking-step-${tier.level}`}
                  onClick={() => {
                    handleStepClick(tier.level);
                  }}
                  onMouseEnter={() => {
                    setHoveredLevel(tier.level);
                  }}
                  onMouseLeave={() => {
                    setHoveredLevel(null);
                  }}
                  aria-pressed={isSelected}
                  className={`px-1.5 py-0.5 text-[10px] font-mono rounded transition-all ${
                    isSelected
                      ? 'bg-primary text-primary-foreground font-semibold shadow-2xs'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  }`}
                  title={`${tier.tokenLabel} · ${tier.latencyDescription}`}
                >
                  {tier.tokenLabel}
                </button>
              );
            })}
          </div>

          {/* Current badge indicator */}
          <span
            data-testid="thinking-tier-badge"
            className="text-[11px] font-medium text-muted-foreground min-w-[28px] text-right"
            title={displayTier.latencyDescription}
          >
            {displayTier.tokenLabel}
          </span>
        </div>
      )}
    </div>
  );
}
