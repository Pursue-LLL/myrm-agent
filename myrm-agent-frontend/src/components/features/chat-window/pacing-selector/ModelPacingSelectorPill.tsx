'use client';

/**
 * [INPUT]
 * - @/components/features/chat-window/pacing-selector/modelPacingTypes
 * - @/components/features/chat-window/pacing-selector/modelPacingEngine
 * - @/components/features/chat-window/pacing-selector/useModelPacingStore
 * - lucide-react (POS: Vector icons, zero native emojis)
 *
 * [OUTPUT]
 * - ModelPacingSelectorPill (POS: Compact tri-tier execution pacing selector pill)
 *
 * [POS]
 * Implementation for Item 191 input bar pill.
 * Provides instant one-click inspection and tier switching between Fast / Balanced / Smart.
 */

import React, { memo, useMemo, useCallback } from 'react';
import { Zap, Scale, Brain, ChevronDown } from 'lucide-react';
import type { ModelPacingTier } from './modelPacingTypes';
import { resolvePacingSpec } from './modelPacingEngine';
import { useModelPacingStore } from './useModelPacingStore';

interface ModelPacingSelectorPillProps {
  readonly className?: string;
  readonly compact?: boolean;
}

export const ModelPacingSelectorPill = memo(function ModelPacingSelectorPill({
  className = '',
  compact = false,
}: ModelPacingSelectorPillProps) {
  const activeTier = useModelPacingStore((s) => s.activeTier);
  const isPopoverOpen = useModelPacingStore((s) => s.isPopoverOpen);
  const togglePopover = useModelPacingStore((s) => s.togglePopover);

  const spec = useMemo(() => resolvePacingSpec(activeTier), [activeTier]);

  const renderIcon = (tier: ModelPacingTier) => {
    switch (tier) {
      case 'fast': {
        return <Zap className="w-3.5 h-3.5 text-sky-400" aria-hidden="true" />;
      }
      case 'balanced': {
        return <Scale className="w-3.5 h-3.5 text-emerald-400" aria-hidden="true" />;
      }
      case 'smart': {
        return <Brain className="w-3.5 h-3.5 text-purple-400" aria-hidden="true" />;
      }
    }
  };

  const badgeColorClass = useMemo(() => {
    switch (spec.badgeColor) {
      case 'sky': {
        return 'bg-sky-500/10 text-sky-300 border-sky-500/30';
      }
      case 'emerald': {
        return 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30';
      }
      case 'purple': {
        return 'bg-purple-500/10 text-purple-300 border-purple-500/30';
      }
    }
  }, [spec.badgeColor]);

  const handleClick = useCallback(() => {
    togglePopover();
  }, [togglePopover]);

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-haspopup="dialog"
      aria-expanded={isPopoverOpen}
      aria-label={`执行节奏：${spec.displayName} (${spec.typicalLatencySec})`}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium transition-colors hover:opacity-90 focus:outline-none focus:ring-1 focus:ring-sky-500 select-none ${badgeColorClass} ${className}`}
    >
      {renderIcon(activeTier)}
      {!compact ? <span>{spec.displayName}</span> : null}
      <span className="text-[10px] opacity-70 hidden sm:inline">{spec.typicalLatencySec}</span>
      <ChevronDown
        className={`w-3 h-3 opacity-60 transition-transform ${isPopoverOpen ? 'rotate-180' : ''}`}
        aria-hidden="true"
      />
    </button>
  );
});
