'use client';

/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天消息与模型状态订阅)
 * - @/components/features/chat-window/ModelPricingPopover::ModelPricingPopover (POS: 四维单价透视弹窗)
 *
 * [OUTPUT]
 * - RealTimeCostAndCacheHud: 常驻算力与 Prompt Cache 经济学透视胶囊 HUD
 *
 * [POS]
 * 表现层/聊天窗：置于输入框底栏的常驻算力胶囊，提供上下文 Token 水位、预估费用、
 * Prompt Cache 命中率指示与高亮节省微徽章，点击展开模型四维单价矩阵。
 */

import React, { memo, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import useChatStore from '@/store/useChatStore';
import { ModelPricingPopover } from './ModelPricingPopover';
import { Zap, Activity } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

function formatTokens(tokens: number): string {
  if (tokens >= 1_000_000) {
    return `${(tokens / 1_000_000).toFixed(1)}M`;
  }
  if (tokens >= 1_000) {
    return `${(tokens / 1_000).toFixed(1)}K`;
  }
  return `${tokens}`;
}

// 只在有节省金额（> 0）时才展示，故无需处理非正数
function formatCost(usd: number): string {
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(3)}`;
}

// 旧会话或外部代理回传的用量可能缺字段，缺失按 0 累计
const amount = (value: number | undefined): number => (typeof value === 'number' ? value : 0);

export const RealTimeCostAndCacheHud: React.FC = memo(() => {
  const t = useTranslations('chat.costHud');
  const messages = useChatStore((state) => state.messages);
  const baseModel = useChatStore((state) => state.selectedModels.base);

  const currentModelName = baseModel || 'default';

  // 从当前对话历史中聚合统计 Token 用量与 Prompt Cache 经济学指标
  const sessionEconomics = useMemo(() => {
    let totalTokens = 0;
    let totalCachedTokens = 0;
    let totalPromptTokens = 0;
    let totalNetSavingsUsd = 0;
    let hasEffectiveCache = false;

    for (const { usage } of messages) {
      if (!usage) {
        continue;
      }
      totalTokens += amount(usage.total_tokens);
      totalPromptTokens += amount(usage.prompt_tokens);
      totalCachedTokens += amount(usage.cached_tokens);
      totalNetSavingsUsd += amount(usage.net_savings_usd);
      hasEffectiveCache ||= usage.has_effective_cache === true;
    }

    // 命中率由累计 token 得出：服务端逐轮的 cache_hit_rate 是 0–1 比例，不能与百分比混用
    const hitRate = totalPromptTokens > 0 ? (totalCachedTokens / totalPromptTokens) * 100 : 0;

    // 测量衰减纠偏门限：服务端判定有效，或累计 cached_tokens >= 1024 且 net_savings >= 0.0001 时才高亮
    const isCacheActive = hasEffectiveCache || (totalCachedTokens >= 1024 && totalNetSavingsUsd >= 0.0001);

    return { totalTokens, totalCachedTokens, totalNetSavingsUsd, hitRate, isCacheActive };
  }, [messages]);

  // 当会话没有任何 Token 消耗时，显示极简就绪状态胶囊
  const hasUsage = sessionEconomics.totalTokens > 0;

  return (
    <ModelPricingPopover currentModel={currentModelName}>
      <button
        type="button"
        title={t('popoverTitle')}
        className={cn(
          'group flex min-h-6 items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-mono transition-all select-none',
          'border bg-background/80 hover:bg-muted/80 backdrop-blur-sm shadow-2xs cursor-pointer',
          sessionEconomics.isCacheActive
            ? 'border-emerald-500/30 text-emerald-600 dark:text-emerald-400'
            : 'border-border/60 text-muted-foreground hover:text-foreground',
        )}
      >
        <Activity className="w-3 h-3 text-muted-foreground group-hover:text-primary transition-colors flex-shrink-0" />

        {hasUsage ? (
          <>
            {/* 上下文/总 Token 水位 */}
            <span className="font-medium">{formatTokens(sessionEconomics.totalTokens)} tok</span>

            {/* Prompt Cache 命中率高亮或常规显示 */}
            {sessionEconomics.isCacheActive ? (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-semibold text-[10px] animate-pulse">
                <Zap className="w-2.5 h-2.5 fill-current" />
                <span>{sessionEconomics.hitRate.toFixed(0)}% Cache</span>
                {sessionEconomics.totalNetSavingsUsd > 0 && (
                  <span className="ml-0.5 opacity-90">
                    {t('savedAmount', { amount: formatCost(sessionEconomics.totalNetSavingsUsd) })}
                  </span>
                )}
              </span>
            ) : sessionEconomics.totalCachedTokens > 0 ? (
              <span className="text-[10px] text-muted-foreground/80">{sessionEconomics.hitRate.toFixed(0)}% Cache</span>
            ) : null}
          </>
        ) : (
          <span className="text-[11px] text-muted-foreground group-hover:text-foreground">{t('idleLabel')}</span>
        )}
      </button>
    </ModelPricingPopover>
  );
});

RealTimeCostAndCacheHud.displayName = 'RealTimeCostAndCacheHud';
