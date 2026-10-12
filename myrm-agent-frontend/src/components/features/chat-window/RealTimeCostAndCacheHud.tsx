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

function formatCost(usd: number): string {
  if (usd <= 0) return '$0.0000';
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(3)}`;
}

export const RealTimeCostAndCacheHud: React.FC = memo(() => {
  const messages = useChatStore((state) => state.messages);
  const selectedModels = useChatStore((state) => state.selectedModels);

  // 当前主模型名
  const currentModelName = useMemo(() => {
    return selectedModels?.base || 'default';
  }, [selectedModels?.base]);

  // 从当前对话历史中聚合统计 Token 用量与 Prompt Cache 经济学指标
  const sessionEconomics = useMemo(() => {
    let totalTokens = 0;
    let totalCachedTokens = 0;
    let totalPromptTokens = 0;
    let totalNetSavingsUsd = 0;
    let latestCacheHitRate = 0;
    let latestHasEffectiveCache = false;

    // 倒序遍历查找最近一轮的用量快照与全量累计
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i];
      const usage = msg.usage;
      if (!usage) continue;

      if (typeof usage.total_tokens === 'number') {
        totalTokens += usage.total_tokens;
      }
      if (typeof usage.prompt_tokens === 'number') {
        totalPromptTokens += usage.prompt_tokens;
      }
      if (typeof usage.cached_tokens === 'number') {
        totalCachedTokens += usage.cached_tokens;
      }
      if (typeof usage.net_savings_usd === 'number') {
        totalNetSavingsUsd += usage.net_savings_usd;
      }

      // 提取最新一轮的命中率指示
      if (latestCacheHitRate === 0 && typeof usage.cache_hit_rate === 'number') {
        latestCacheHitRate = usage.cache_hit_rate;
      }
      if (!latestHasEffectiveCache && usage.has_effective_cache === true) {
        latestHasEffectiveCache = true;
      }
    }

    // 全局命中率：若最近一轮无独立率，则使用累计 prompt tokens 计算
    const overallHitRate =
      totalPromptTokens > 0 ? (totalCachedTokens / totalPromptTokens) * 100 : latestCacheHitRate;

    // 测量衰减纠偏门限：只有当 cached_tokens >= 1024 且 net_savings >= 0.0001 时才高亮
    const isCacheActive =
      latestHasEffectiveCache || (totalCachedTokens >= 1024 && totalNetSavingsUsd >= 0.0001);

    return {
      totalTokens,
      totalCachedTokens,
      totalPromptTokens,
      totalNetSavingsUsd,
      hitRate: overallHitRate,
      isCacheActive,
    };
  }, [messages]);

  // 当会话没有任何 Token 消耗时，显示极简就绪状态胶囊
  const hasUsage = sessionEconomics.totalTokens > 0;

  return (
    <ModelPricingPopover currentModel={currentModelName}>
      <button
        type="button"
        title="点击查看模型四维单价矩阵与 Prompt Cache 经济学效益"
        className={cn(
          'group flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-mono transition-all select-none',
          'border bg-background/80 hover:bg-muted/80 backdrop-blur-sm shadow-2xs cursor-pointer',
          sessionEconomics.isCacheActive
            ? 'border-emerald-500/30 text-emerald-600 dark:text-emerald-400'
            : 'border-border/60 text-muted-foreground hover:text-foreground'
        )}
      >
        <Activity className="w-3 h-3 text-muted-foreground group-hover:text-primary transition-colors flex-shrink-0" />

        {hasUsage ? (
          <>
            {/* 上下文/总 Token 水位 */}
            <span className="font-medium">
              {formatTokens(sessionEconomics.totalTokens)} tok
            </span>

            {/* Prompt Cache 命中率高亮或常规显示 */}
            {sessionEconomics.isCacheActive ? (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.2 rounded-full bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-semibold text-[10px] animate-pulse">
                <Zap className="w-2.5 h-2.5 fill-current" />
                <span>{sessionEconomics.hitRate.toFixed(0)}% Cache</span>
                {sessionEconomics.totalNetSavingsUsd > 0 && (
                  <span className="ml-0.5 opacity-90">
                    (省 {formatCost(sessionEconomics.totalNetSavingsUsd)})
                  </span>
                )}
              </span>
            ) : sessionEconomics.totalCachedTokens > 0 ? (
              <span className="text-[10px] text-muted-foreground/80">
                {sessionEconomics.hitRate.toFixed(0)}% Cache
              </span>
            ) : null}
          </>
        ) : (
          <span className="text-[10px] text-muted-foreground group-hover:text-foreground">
            算力透视 HUD
          </span>
        )}
      </button>
    </ModelPricingPopover>
  );
});

RealTimeCostAndCacheHud.displayName = 'RealTimeCostAndCacheHud';
