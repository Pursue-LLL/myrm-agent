'use client';

import React from 'react';
import { useTranslations } from 'next-intl';

export type FactStatusType = 'published_truth' | 'in_progress_draft' | 'deprecated';

interface FactTrustBadgeProps {
  status?: FactStatusType | string;
  className?: string;
  showLabel?: boolean;
}

export const FactTrustBadge: React.FC<FactTrustBadgeProps> = ({
  status = 'published_truth',
  className = '',
  showLabel = true,
}) => {
  const t = useTranslations('knowledge');

  const normalizedStatus: FactStatusType =
    status === 'in_progress_draft' || status === 'draft'
      ? 'in_progress_draft'
      : status === 'deprecated' || status === 'blocked'
        ? 'deprecated'
        : 'published_truth';

  const badgeConfig = {
    published_truth: {
      dotColor: 'bg-emerald-500',
      bgColor: 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border-emerald-500/20',
      label: 'Published Truth',
      icon: '✓',
    },
    in_progress_draft: {
      dotColor: 'bg-amber-500',
      bgColor: 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/20',
      label: 'Draft',
      icon: '✎',
    },
    deprecated: {
      dotColor: 'bg-zinc-400',
      bgColor: 'bg-zinc-500/10 text-zinc-600 dark:text-zinc-400 border-zinc-500/20',
      label: 'Deprecated',
      icon: '✕',
    },
  }[normalizedStatus];

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${badgeConfig.bgColor} ${className}`}
      title={`Fact Trust: ${badgeConfig.label}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${badgeConfig.dotColor}`} />
      {showLabel && <span>{badgeConfig.label}</span>}
    </span>
  );
};

export default FactTrustBadge;
