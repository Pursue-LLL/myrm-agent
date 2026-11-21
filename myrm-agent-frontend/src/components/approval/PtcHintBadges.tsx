'use client';

/**
 * [INPUT]
 * - lucide-react icons
 *
 * [OUTPUT]
 * - PtcHintBadges: MCP 工具提供方声明的 destructive / open-world 徽章
 *
 * [POS]
 * SingleApprovalCard 与 PolymorphicApprovalCard 共用的声明徽章组。只提示更小心，不出现「只读」：
 * 提供方自称只读不是事实，卡片在决策点不得拿它劝人放心。
 */

import { Globe, Terminal } from 'lucide-react';

import { cn } from '@/lib/utils/classnameUtils';

export interface PtcAnnotations {
  destructiveHint?: boolean;
  openWorldHint?: boolean;
}

interface PtcHintBadgesProps {
  annotations: PtcAnnotations;
  t: (key: string) => string;
  className?: string;
  badgeClassName?: string;
}

/** Badges for what a tool's provider declares about it: destructive and open-world, each labelled as a declaration. */
export default function PtcHintBadges({ annotations, t, className, badgeClassName }: PtcHintBadgesProps) {
  if (!annotations.destructiveHint && !annotations.openWorldHint) {
    return null;
  }

  const baseBadge = badgeClassName ?? 'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border';

  return (
    <div className={cn('flex items-center gap-1.5', className)}>
      {annotations.destructiveHint ? (
        <span
          className={cn(
            baseBadge,
            'bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-400 border-red-200 dark:border-red-800',
          )}
          title={t('ptc.destructiveTitle')}
        >
          <Terminal className="w-3 h-3 mr-1" />
          {t('ptc.destructiveLabel')}
        </span>
      ) : null}
      {annotations.openWorldHint ? (
        <span
          className={cn(
            baseBadge,
            'bg-amber-50 dark:bg-amber-950/30 text-amber-700 dark:text-amber-400 border-amber-200 dark:border-amber-800',
          )}
          title={t('ptc.openWorldTitle')}
        >
          <Globe className="w-3 h-3 mr-1" />
          {t('ptc.openWorldLabel')}
        </span>
      ) : null}
    </div>
  );
}
