'use client';

/**
 * [INPUT]
 * - @/hooks/agent/useAgentReadiness::useAgentReadiness (POS: SWR readiness polling)
 *
 * [OUTPUT]
 * - ReadinessBadge: Compact dot + tooltip in the message-input toolbar.
 *   Hidden when ready; amber dot for warnings, red dot for blocked.
 *
 * [POS]
 * Proactive readiness indicator next to AgentIndicator. Tooltip shows
 * per-dimension issues with deep-link buttons to Settings.
 */

import { memo, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { useRouter } from 'next/navigation';
import { AlertTriangle, XCircle } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { useAgentReadiness } from '@/hooks/agent/useAgentReadiness';
import type { ReadinessLevel, AgentReadinessItem } from '@/services/agent';

const DOT_STYLES: Record<Exclude<ReadinessLevel, 'ready'>, string> = {
  warning: 'bg-amber-500',
  blocked: 'bg-red-500 animate-pulse',
};

const ICON_MAP: Record<Exclude<ReadinessLevel, 'ready'>, typeof AlertTriangle> = {
  warning: AlertTriangle,
  blocked: XCircle,
};

const ReadinessBadge = memo(() => {
  const t = useTranslations('agent.readiness');
  const router = useRouter();
  const { report, overallLevel, hasIssues, isLoading } = useAgentReadiness();

  const handleDeepLink = useCallback(
    (path: string) => {
      router.push(path);
    },
    [router],
  );

  if (!hasIssues || isLoading || !report) {return null;}

  const level = overallLevel as Exclude<ReadinessLevel, 'ready'>;
  const Icon = ICON_MAP[level];

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={`inline-flex h-2 w-2 shrink-0 rounded-full cursor-pointer ${DOT_STYLES[level]}`}
            aria-label={t(level)}
          />
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-[320px] p-3 space-y-2" sideOffset={8}>
          <div className="flex items-center gap-1.5 text-xs font-medium">
            <Icon size={14} className={level === 'blocked' ? 'text-red-500' : 'text-amber-500'} />
            <span>{t(level)}</span>
          </div>
          <div className="space-y-1.5">
            {report.items
              .filter((item: AgentReadinessItem) => item.level !== 'ready')
              .map((item: AgentReadinessItem) => (
                <button
                  key={item.dimension}
                  type="button"
                  className="flex items-start gap-2 w-full text-left text-xs text-muted-foreground hover:text-foreground transition-colors rounded p-1 -m-1 hover:bg-muted/50"
                  onClick={() => handleDeepLink(item.settings_path)}
                >
                  <span className="shrink-0 mt-0.5">
                    <span
                      className={`inline-block h-1.5 w-1.5 rounded-full ${
                        item.level === 'blocked' ? 'bg-red-500' : 'bg-amber-500'
                      }`}
                    />
                  </span>
                  <span>
                    <span className="font-medium text-foreground">{item.dimension}</span>
                    {' — '}
                    {item.next_action}
                  </span>
                </button>
              ))}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
});

ReadinessBadge.displayName = 'ReadinessBadge';

export default ReadinessBadge;
