'use client';

/**
 * FabricationPlaceholderBadge Component.
 * Inline highlight badge for unverified placeholder numbers/data.
 * Implements WorkBuddy controlled fabrication paradigm with zero emojis.
 */

import React from 'react';
import { AlertCircle, CheckCircle2 } from 'lucide-react';
import { PlaceholderItem } from './factCheckTypes';

interface FabricationPlaceholderBadgeProps {
  item: PlaceholderItem;
  onClick?: (item: PlaceholderItem) => void;
  className?: string;
}

export const FabricationPlaceholderBadge: React.FC<FabricationPlaceholderBadgeProps> = ({
  item,
  onClick,
  className = '',
}) => {
  const isPending = item.status === 'pending';

  return (
    <button
      type="button"
      onClick={() => {
        if (onClick) {
          onClick(item);
        }
      }}
      title={
        isPending
          ? '待实测占位数据：发布前建议替换为真实跑测结果'
          : `已替换为真实数据: ${item.replacedValue}`
      }
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-mono transition-all cursor-pointer ${
        isPending
          ? 'bg-amber-500/15 border border-amber-500/40 text-amber-300 hover:bg-amber-500/25'
          : 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/25'
      } ${className}`}
    >
      {isPending ? (
        <AlertCircle className="w-3 h-3 text-amber-400 shrink-0" />
      ) : (
        <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
      )}
      <span>
        {isPending
          ? `[待替换: ${item.placeholderKey}]`
          : (item.replacedValue || item.placeholderKey)}
      </span>
    </button>
  );
};
