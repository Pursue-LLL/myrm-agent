/**
 * [INPUT]
 * - chatId?: string
 * - useSwarmExecutionStore: Zustand store
 *
 * [OUTPUT]
 * - SwarmModeToggle: Input bar quick-action toggle button for Swarm multi-agent parallel execution
 *
 * [POS]
 * Input action button for Swarm Mode (Item 42 P0).
 * Strictly under 120 lines. Zero `any`.
 */

'use client';

import React from 'react';
import { Users, Sparkles } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import useChatStore from '@/store/useChatStore';
import { useSwarmExecutionStore } from '@/components/features/swarm/useSwarmExecutionStore';
import { cn } from '@/lib/utils/classnameUtils';

interface SwarmModeToggleProps {
  chatId?: string;
  className?: string;
}

export const SwarmModeToggle: React.FC<SwarmModeToggleProps> = ({ chatId, className }) => {
  const t = useTranslations('swarmExecution');
  const storeChatId = useChatStore((s) => s.chatId);
  const effectiveChatId = chatId || storeChatId || '';

  const { isSwarmEnabled, concurrencyQuota, toggleSwarm } = useSwarmExecutionStore();

  const handleToggle = () => {
    void toggleSwarm(effectiveChatId);
  };

  return (
    <TooltipProvider delayDuration={200}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            aria-label={t('swarmModeAriaLabel')}
            aria-pressed={isSwarmEnabled}
            onClick={handleToggle}
            className={cn(
              'relative flex shrink-0 items-center gap-1.5 h-7 px-2.5 rounded-full text-xs font-semibold whitespace-nowrap transition-all duration-300 cursor-pointer select-none overflow-hidden',
              isSwarmEnabled
                ? 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/40 shadow-sm shadow-amber-500/20 hover:bg-amber-500/20'
                : 'bg-black/[0.03] dark:bg-white/[0.04] text-slate-600 dark:text-slate-400 border border-transparent hover:text-slate-900 dark:hover:text-slate-100 hover:bg-black/[0.06] dark:hover:bg-white/[0.08]',
              className,
            )}
          >
            {isSwarmEnabled && (
              <div className="absolute inset-0 bg-gradient-to-r from-transparent via-amber-200/30 dark:via-amber-400/20 to-transparent -translate-x-full animate-shimmer" />
            )}
            <Users
              className={cn(
                'h-3.5 w-3.5 shrink-0 transition-transform duration-300',
                isSwarmEnabled ? 'text-amber-600 dark:text-amber-400 scale-110' : 'text-current',
              )}
            />
            <span className="tracking-wide">{t('swarmModeLabel')}</span>
            {isSwarmEnabled && (
              <span className="flex items-center gap-0.5 rounded-full bg-amber-500/20 px-1 py-0.2 text-[10px] font-bold text-amber-700 dark:text-amber-300">
                <Sparkles className="h-2.5 w-2.5" />
                <span>{concurrencyQuota}</span>
              </span>
            )}
          </button>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-64 p-3">
          <p className="font-semibold text-sm mb-1">{t('swarmModeTooltipTitle')}</p>
          <p className="text-xs text-muted-foreground leading-relaxed">
            {t('swarmModeTooltipDesc', { quota: concurrencyQuota })}
          </p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};

export default SwarmModeToggle;
