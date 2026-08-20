'use client';

/**
 * [INPUT]
 * - lucide-react icons
 *
 * [OUTPUT]
 * - PtcHintBadges: MCP PTC read-only / destructive / open-world 注解 badge
 *
 * [POS]
 * SingleApprovalCard 与 ToolCallApproval 共用的 PTC 注解 badge 组。
 */

import { Check, Globe, Terminal } from 'lucide-react';

import { cn } from '@/lib/utils/classnameUtils';

export interface PtcAnnotations {
  readOnlyHint?: boolean;
  destructiveHint?: boolean;
  openWorldHint?: boolean;
}

interface PtcHintBadgesProps {
  annotations: PtcAnnotations;
  t: (key: string) => string;
  className?: string;
  badgeClassName?: string;
}

/** MCP/PTC tool hint badges (read-only / destructive / open-world). */
export default function PtcHintBadges({ annotations, t, className, badgeClassName }: PtcHintBadgesProps) {
  if (!annotations.readOnlyHint && !annotations.destructiveHint && !annotations.openWorldHint) {
    return null;
  }

  const baseBadge = badgeClassName ?? 'inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium border';

  return (
    <div className={cn('flex items-center gap-1.5', className)}>
      {annotations.readOnlyHint ? (
        <span
          className={cn(
            baseBadge,
            'bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-400 border-green-200 dark:border-green-800',
          )}
          title={t('ptc.readOnlyTitle')}
        >
          <Check className="w-3 h-3 mr-1" />
          {t('ptc.readOnlyLabel')}
        </span>
      ) : null}
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
