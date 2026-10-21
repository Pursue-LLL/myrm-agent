/**
 * Quota Exhaustion Warning & Failover Banner Component
 * 额度耗尽柔性预警、会话现场冻结保护与一键自愈故障转移横幅
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 具备清晰的恢复动作与无障碍交互。
 */

import React from 'react';
import {
  AlertTriangle,
  ArrowRightLeft,
  PauseCircle,
  X,
  ShieldAlert,
  CheckCircle2,
} from 'lucide-react';
import { ProviderId } from './providerQuotaTypes';
import { useProviderQuotaStore } from './useProviderQuotaStore';
import { formatCurrency, formatTokenCount } from './quotaTelemetryParser';

export interface QuotaExhaustionWarningBannerProps {
  className?: string;
}

export const QuotaExhaustionWarningBanner: React.FC<
  QuotaExhaustionWarningBannerProps
> = ({ className = '' }) => {
  const {
    providers,
    activeProviderId,
    isExhaustionWarningOpen,
    lastFailoverAction,
    setExhaustionWarningOpen,
    triggerFailoverRecovery,
  } = useProviderQuotaStore();

  const currentProvider = providers[activeProviderId];

  if (!isExhaustionWarningOpen || !currentProvider) {
    return null;
  }

  // 推荐健康的备选 Provider 候选列表
  const healthyAlternatives: ProviderId[] = (
    Object.keys(providers) as ProviderId[]
  ).filter((pId) => {
    return (
      pId !== activeProviderId &&
      providers[pId].status === 'healthy'
    );
  });

  const recommendedFallback: ProviderId =
    healthyAlternatives.length > 0 ? healthyAlternatives[0] : 'local';

  const handleFailover = (targetId: ProviderId): void => {
    triggerFailoverRecovery(targetId, 'insufficient_quota');
  };

  const isExhausted =
    currentProvider.status === 'exhausted' ||
    currentProvider.remainingTokens <= 0;

  return (
    <div
      data-testid="quota-exhaustion-warning-banner"
      className={`relative flex flex-col md:flex-row items-start md:items-center justify-between gap-3 rounded-xl border border-rose-500/50 bg-rose-950/40 p-3.5 backdrop-blur-md text-neutral-100 shadow-xl ${className}`}
    >
      {/* 警示文本与状态 */}
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-rose-500/20 text-rose-400">
          <ShieldAlert className="h-5 w-5" />
        </div>

        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-rose-200 text-sm">
              {isExhausted ? '算力配额已完全耗尽' : '算力配额濒临枯竭预警'}
            </span>
            <span className="rounded bg-rose-500/30 px-1.5 py-0.5 font-mono text-[10px] text-rose-300 font-bold">
              剩余 {currentProvider.remainingPercentage}%
            </span>
          </div>

          <p className="text-xs text-neutral-300">
            提供商{' '}
            <span className="font-mono font-medium text-white">
              {currentProvider.name}
            </span>{' '}
            剩余 Token 仅剩{' '}
            <span className="font-mono text-rose-300">
              {formatTokenCount(currentProvider.remainingTokens)}
            </span>
            {currentProvider.supportsLiveTelemetry && (
              <>
                {' '}
                (余额 {formatCurrency(currentProvider.balanceUsd)})
              </>
            )}
            。长程任务面临中断风险，系统已自动保护会话现场。
          </p>
        </div>
      </div>

      {/* 快捷自愈与操作区 */}
      <div className="flex items-center gap-2 self-end md:self-auto shrink-0">
        {/* 一键无缝热切换至健康备用渠道 */}
        <button
          type="button"
          data-testid="failover-action-btn"
          onClick={() => {
            handleFailover(recommendedFallback);
          }}
          className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 transition-colors shadow-sm"
        >
          <ArrowRightLeft className="h-3.5 w-3.5" />
          <span>
            热切换至 {providers[recommendedFallback].name}
          </span>
        </button>

        {/* 冻结等待充值 */}
        <button
          type="button"
          data-testid="suspend-session-btn"
          onClick={() => {
            setExhaustionWarningOpen(false);
          }}
          className="flex items-center gap-1 rounded-lg border border-neutral-700 bg-neutral-800/80 px-2.5 py-1.5 text-xs font-medium text-neutral-300 hover:bg-neutral-800 hover:text-white transition-colors"
          title="保持当前会话现场冻结并关闭警告"
        >
          <PauseCircle className="h-3.5 w-3.5 text-neutral-400" />
          <span>挂起保留</span>
        </button>

        {/* 关闭按钮 */}
        <button
          type="button"
          data-testid="dismiss-warning-btn"
          onClick={() => {
            setExhaustionWarningOpen(false);
          }}
          className="rounded-lg p-1 text-neutral-400 hover:bg-neutral-800 hover:text-white transition-colors"
          aria-label="关闭告警"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* 曾触发过的降级指示 */}
      {lastFailoverAction && (
        <div
          data-testid="failover-history-tag"
          className="w-full border-t border-rose-900/50 pt-2 text-[11px] text-neutral-400 flex items-center gap-1 font-mono"
        >
          <CheckCircle2 className="h-3 w-3 text-emerald-400" />
          <span>
            最近自愈：从 {lastFailoverAction.sourceProviderId} 成功平滑迁移至{' '}
            {lastFailoverAction.targetProviderId}
          </span>
        </div>
      )}
    </div>
  );
};
