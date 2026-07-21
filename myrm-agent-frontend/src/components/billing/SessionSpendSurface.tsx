/**
 * [INPUT]
 * - useChatStore (messages with costUsd/wuConsumed)
 * - useEntitlements (balance_wu for ETA calc)
 * - useBillingCatalog (topup_wu_per_usd for USD→WU fallback)
 * - @/lib/deploy-mode::isSandbox / isLocalMode
 *
 * [OUTPUT]
 * - SessionSpendSurface: 对话输入区旁的 WU/$ 消耗 pill
 *
 * [POS]
 * Sandbox: 显示本轮 WU 消耗 + 本会话累计 + burn-rate ETA
 * Local/Tauri: 显示本会话 $ 累计
 */
'use client';

import { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import useChatStore from '@/store/useChatStore';
import { isSandbox, isLocalMode } from '@/lib/deploy-mode';
import { useEntitlements } from '@/hooks/useEntitlements';
import { useBillingCatalog } from '@/hooks/useBillingCatalog';
import { cn } from '@/lib/utils/classnameUtils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';

const WU_PER_USD_FALLBACK = 1000;
const MIN_TURNS_FOR_ETA = 3;
const ESTIMATED_TURNS_PER_DAY = 30;

interface SessionSpendSurfaceProps {
  className?: string;
}

export default function SessionSpendSurface({ className }: SessionSpendSurfaceProps) {
  const sandbox = isSandbox();
  const local = isLocalMode();
  const t = useTranslations('billing.spendSurface');
  const messages = useChatStore((s) => s.messages);
  const { entitlements } = useEntitlements();
  const { catalog } = useBillingCatalog();

  const wuPerUsd = catalog?.topup_wu_per_usd ?? WU_PER_USD_FALLBACK;

  const { lastTurnWu, sessionWu, lastTurnCost, sessionCost, assistantTurns } = useMemo(() => {
    let totalWu = 0;
    let totalCost = 0;
    let latestWu = 0;
    let latestCost = 0;
    let turns = 0;

    for (const msg of messages) {
      if (msg.role !== 'assistant') continue;
      const wu = msg.wuConsumed ?? (msg.costUsd ? Math.max(1, Math.round(msg.costUsd * wuPerUsd)) : 0);
      const cost = msg.costUsd ?? 0;
      if (wu > 0 || cost > 0) {
        totalWu += wu;
        totalCost += cost;
        latestWu = wu;
        latestCost = cost;
        turns += 1;
      }
    }
    return { lastTurnWu: latestWu, sessionWu: totalWu, lastTurnCost: latestCost, sessionCost: totalCost, assistantTurns: turns };
  }, [messages, wuPerUsd]);

  if (!sandbox && !local) return null;
  if (sessionWu === 0 && sessionCost === 0) return null;

  if (sandbox) {
    const balanceWu = entitlements?.balance_wu;
    let etaDays: number | null = null;
    if (balanceWu && assistantTurns >= MIN_TURNS_FOR_ETA && sessionWu > 0) {
      const avgWuPerTurn = sessionWu / assistantTurns;
      const dailyBurn = avgWuPerTurn * ESTIMATED_TURNS_PER_DAY;
      etaDays = dailyBurn > 0 ? Math.round(balanceWu / dailyBurn) : null;
    }

    const pillContent = (
      <span
        className={cn(
          'inline-flex items-center gap-1.5 rounded-full border border-border/50 bg-muted/30 px-2 py-0.5 text-[11px] text-muted-foreground tabular-nums',
          className,
        )}
      >
        {lastTurnWu > 0 && <span className="text-orange-600 dark:text-orange-400 font-medium">{t('turnWu', { wu: lastTurnWu })}</span>}
        <span>{t('sessionWu', { wu: sessionWu.toLocaleString() })}</span>
        {etaDays !== null && etaDays < 999 && (
          <span className="text-muted-foreground/70">{t('burnEta', { days: etaDays })}</span>
        )}
      </span>
    );

    if (!etaDays || !balanceWu) return pillContent;

    return (
      <TooltipProvider delayDuration={200}>
        <Tooltip>
          <TooltipTrigger asChild>{pillContent}</TooltipTrigger>
          <TooltipContent side="top" className="text-xs">
            <div className="flex flex-col gap-0.5">
              <span>{t('tooltipBalance', { wu: balanceWu.toLocaleString() })}</span>
              <span>{t('tooltipAvgTurn', { wu: Math.round(sessionWu / assistantTurns) })}</span>
            </div>
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>
    );
  }

  // Local/Tauri: session cost in USD
  if (sessionCost <= 0) return null;

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border border-border/50 bg-muted/30 px-2 py-0.5 text-[11px] text-muted-foreground tabular-nums',
        className,
      )}
    >
      {lastTurnCost > 0 && (
        <span className="text-orange-600 dark:text-orange-400 font-medium">
          {t('turnCost', { cost: lastTurnCost.toFixed(4) })}
        </span>
      )}
      <span>{t('sessionCost', { cost: sessionCost.toFixed(4) })}</span>
    </span>
  );
}
