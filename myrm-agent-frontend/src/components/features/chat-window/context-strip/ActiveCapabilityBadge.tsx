'use client';

/**
 * [INPUT]
 * - Lucide icons & standard class helpers
 * - useTranslations('chat.contextStrip')
 *
 * [OUTPUT]
 * - ActiveCapabilityBadge: 呈现当前轮次活跃能力计数（基础工具/技能/MCP），当挂载较多工具时触发 Amber Nudge 预警。
 *
 * [POS]
 * 聊天输入区上下文胶囊条右侧常驻的负载指示器。
 */

import * as React from 'react';
import { Zap, AlertTriangle } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';

export interface ActiveCapabilityBadgeProps {
  skillCount: number;
  mcpCount: number;
  isOverloaded?: boolean;
  onClick?: () => void;
  className?: string;
}

export function ActiveCapabilityBadge({
  skillCount,
  mcpCount,
  isOverloaded = false,
  onClick,
  className,
}: ActiveCapabilityBadgeProps) {
  const t = useTranslations('chat.contextStrip');

  const total = skillCount + mcpCount;
  if (total === 0) {
    return null;
  }

  const badgeContent = (
    <button
      type="button"
      data-testid="active-capability-badge"
      onClick={onClick}
      className={cn(
        'inline-flex h-6.5 items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium transition-all select-none',
        isOverloaded
          ? 'border border-amber-500/40 bg-amber-500/15 text-amber-800 dark:text-amber-300 hover:bg-amber-500/25 animate-pulse'
          : 'border border-border/60 bg-muted/50 text-muted-foreground hover:bg-muted/80 hover:text-foreground',
        onClick && 'cursor-pointer',
        className,
      )}
      aria-label={isOverloaded ? t('overloadAria') : t('badgeAria', { count: total })}
    >
      {isOverloaded ? (
        <AlertTriangle className="h-3 w-3 text-amber-600 dark:text-amber-400 shrink-0" />
      ) : (
        <Zap className="h-3 w-3 text-primary/70 shrink-0" />
      )}
      <span className="leading-none">
        {total} {t('capabilities')}
      </span>
    </button>
  );

  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>{badgeContent}</TooltipTrigger>
        <TooltipContent side="top" align="end" className="text-xs max-w-xs p-2 space-y-1">
          <p className="font-semibold">{t('activeCapabilitiesTitle')}</p>
          <div className="text-muted-foreground text-[11px] space-y-0.5">
            {skillCount > 0 ? <p>{t('skillCountDesc', { count: skillCount })}</p> : null}
            {mcpCount > 0 ? <p>{t('mcpCountDesc', { count: mcpCount })}</p> : null}
          </div>
          {isOverloaded ? (
            <p className="text-amber-600 dark:text-amber-400 font-medium pt-1 text-[11px] border-t border-border/40">
              {t('overloadWarning')}
            </p>
          ) : null}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
