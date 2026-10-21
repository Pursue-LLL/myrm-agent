'use client';

/**
 * [INPUT]
 * - @/components/features/chat-window/pacing-selector/modelPacingTypes
 * - @/components/features/chat-window/pacing-selector/modelPacingEngine
 * - @/components/features/chat-window/pacing-selector/useModelPacingStore
 * - lucide-react (POS: Vector icons, zero native emojis)
 *
 * [OUTPUT]
 * - ModelPacingDetailPopover (POS: Tri-tier model execution pacing selector card popover)
 *
 * [POS]
 * Implementation for Item 191 detailed selector popover.
 * Allows users to switch between Fast (<5s) / Balanced (10-25s) / Smart (30-90s).
 */

import React, { memo, useMemo, useCallback } from 'react';
import { Zap, Scale, Brain, Check, X, Sparkles } from 'lucide-react';
import type { ModelPacingTier } from './modelPacingTypes';
import { resolvePacingSpec } from './modelPacingEngine';
import { useModelPacingStore } from './useModelPacingStore';

interface ModelPacingDetailPopoverProps {
  readonly className?: string;
  readonly chatId?: string | null;
  readonly onTierSelected?: (tier: ModelPacingTier) => void;
}

const ALL_TIERS: readonly ModelPacingTier[] = ['fast', 'balanced', 'smart'];

export const ModelPacingDetailPopover = memo(function ModelPacingDetailPopover({
  className = '',
  chatId = null,
  onTierSelected,
}: ModelPacingDetailPopoverProps) {
  const isPopoverOpen = useModelPacingStore((s) => s.isPopoverOpen);
  const activeTier = useModelPacingStore((s) => s.activeTier);
  const setPacingTier = useModelPacingStore((s) => s.setPacingTier);
  const togglePopover = useModelPacingStore((s) => s.togglePopover);

  const tierSpecs = useMemo(() => {
    return ALL_TIERS.map((tier) => resolvePacingSpec(tier));
  }, []);

  const handleSelectTier = useCallback(
    (tier: ModelPacingTier) => {
      setPacingTier(tier, chatId);
      if (onTierSelected) {
        onTierSelected(tier);
      }
    },
    [setPacingTier, chatId, onTierSelected],
  );

  const handleClose = useCallback(() => {
    togglePopover(false);
  }, [togglePopover]);

  if (!isPopoverOpen) {
    return null;
  }

  const renderTierIcon = (tier: ModelPacingTier) => {
    switch (tier) {
      case 'fast': {
        return <Zap className="w-4 h-4 text-sky-400" aria-hidden="true" />;
      }
      case 'balanced': {
        return <Scale className="w-4 h-4 text-emerald-400" aria-hidden="true" />;
      }
      case 'smart': {
        return <Brain className="w-4 h-4 text-purple-400" aria-hidden="true" />;
      }
    }
  };

  return (
    <section
      aria-label="模型执行节奏选择"
      className={`w-full max-w-md rounded-2xl border border-neutral-700/80 bg-neutral-900/95 p-4 shadow-2xl backdrop-blur-md text-neutral-100 z-50 animate-in fade-in zoom-in-95 duration-150 ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-neutral-800">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/20">
            <Sparkles className="w-4 h-4" aria-hidden="true" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-neutral-100">执行节奏档位切换</h3>
            <p className="text-[11px] text-neutral-400">
              按任务紧迫度自主调节，无需手动配置繁复的模型名称
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={handleClose}
          className="p-1 rounded text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800 transition-colors"
          aria-label="关闭节奏选择器"
        >
          <X className="w-4 h-4" aria-hidden="true" />
        </button>
      </div>

      {/* Tier Options Grid */}
      <div className="mt-3.5 space-y-2.5">
        {tierSpecs.map((spec) => {
          const isSelected = activeTier === spec.tier;

          const borderBgClass = isSelected
            ? spec.badgeColor === 'sky'
              ? 'border-sky-500/60 bg-sky-500/10 ring-1 ring-sky-500/40'
              : spec.badgeColor === 'emerald'
              ? 'border-emerald-500/60 bg-emerald-500/10 ring-1 ring-emerald-500/40'
              : 'border-purple-500/60 bg-purple-500/10 ring-1 ring-purple-500/40'
            : 'border-neutral-800 bg-neutral-950/60 hover:bg-neutral-800/60 hover:border-neutral-700';

          return (
            <button
              key={spec.tier}
              type="button"
              onClick={() => handleSelectTier(spec.tier)}
              className={`w-full p-3 rounded-xl border text-left transition-all relative group cursor-pointer ${borderBgClass}`}
              aria-pressed={isSelected}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="p-1.5 rounded-lg bg-neutral-900 border border-neutral-800">
                    {renderTierIcon(spec.tier)}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-xs text-neutral-100">
                        {spec.displayName}
                      </span>
                      <span className="px-1.5 py-0.2 rounded text-[10px] font-mono bg-neutral-800 text-neutral-300">
                        {spec.typicalLatencySec}
                      </span>
                    </div>
                    <div className="text-[11px] text-neutral-400 mt-0.5">{spec.subtitle}</div>
                  </div>
                </div>

                {isSelected ? (
                  <div className="flex items-center justify-center w-5 h-5 rounded-full bg-sky-500 text-neutral-950">
                    <Check className="w-3.5 h-3.5 stroke-[2.5]" aria-hidden="true" />
                  </div>
                ) : null}
              </div>

              <p className="mt-2 text-[11px] text-neutral-400/90 leading-relaxed">
                {spec.description}
              </p>

              {/* Recommended use cases */}
              <div className="mt-2 flex flex-wrap gap-1">
                {spec.recommendedUseCases.map((useCase) => (
                  <span
                    key={useCase}
                    className="px-1.5 py-0.5 rounded text-[10px] bg-neutral-900 text-neutral-400 border border-neutral-800/80"
                  >
                    {useCase}
                  </span>
                ))}
              </div>
            </button>
          );
        })}
      </div>

      {/* Footer hint */}
      <div className="mt-3.5 pt-2.5 border-t border-neutral-800 text-[10px] text-neutral-500 text-center">
        系统将根据所选档位自动匹配最优模型与思考 Token 预算
      </div>
    </section>
  );
});
