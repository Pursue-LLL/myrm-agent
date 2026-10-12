/**
 * Epistemic Veracity Badge Component.
 *
 * [INPUT] EpistemicBadgeProps (tier, confidenceScore, compact)
 * [OUTPUT] JSX.Element - Visual badge representing epistemic trust grade
 * [POS] Item 30 component. Strictly under 120 lines. Zero `any`.
 */

import React from 'react';
import { ShieldCheck, Eye, Sparkles } from 'lucide-react';
import type { EpistemicBadgeProps } from './memoryInspectorTypes';

export const EpistemicBadge: React.FC<EpistemicBadgeProps> = ({
  tier,
  confidenceScore,
  compact = false,
  className = '',
}) => {
  const tierConfig = {
    assertion: {
      label: '确定断言',
      color: 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:bg-emerald-950/40 dark:border-emerald-800 dark:text-emerald-400',
      icon: <ShieldCheck className="w-3.5 h-3.5 text-emerald-500 shrink-0" />,
      defaultConfidence: 1.0,
    },
    observation: {
      label: '环境观察',
      color: 'bg-sky-500/10 border-sky-500/30 text-sky-600 dark:bg-sky-950/40 dark:border-sky-800 dark:text-sky-400',
      icon: <Eye className="w-3.5 h-3.5 text-sky-500 shrink-0" />,
      defaultConfidence: 0.85,
    },
    belief: {
      label: '自主信念',
      color: 'bg-amber-500/10 border-amber-500/30 text-amber-600 dark:bg-amber-950/40 dark:border-amber-800 dark:text-amber-400',
      icon: <Sparkles className="w-3.5 h-3.5 text-amber-500 shrink-0" />,
      defaultConfidence: 0.6,
    },
  }[tier];

  const score = confidenceScore !== undefined ? confidenceScore : tierConfig.defaultConfidence;
  const scorePercent = Math.round(score * 100);

  if (compact) {
    return (
      <span
        title={`${tierConfig.label} (置信度 ${scorePercent}%)`}
        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-medium border ${tierConfig.color} ${className}`}
      >
        {tierConfig.icon}
        <span>{tierConfig.label}</span>
      </span>
    );
  }

  return (
    <div
      role="status"
      aria-label={`${tierConfig.label} 置信度 ${scorePercent}%`}
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${tierConfig.color} shadow-xs ${className}`}
    >
      {tierConfig.icon}
      <span>{tierConfig.label}</span>
      <span className="text-[10px] font-mono opacity-80 pl-0.5 border-l border-current/20">
        {scorePercent}%
      </span>
    </div>
  );
};
