/**
 * Provider Quota Analytics Modal Component
 * 全景 Token 经济学时序大盘、模型占比饼图化进度条与细粒度账单弹窗
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. a11y 模态框无障碍标准与聚焦捕获。
 */

import React, { useEffect } from 'react';
import {
  BarChart3,
  PieChart,
  Calendar,
  DollarSign,
  Flame,
  Download,
  X,
  Clock,
  Bot,
  Zap,
} from 'lucide-react';
import { useProviderQuotaStore } from './useProviderQuotaStore';
import {
  formatCurrency,
  formatTokenCount,
  estimateRemainingDays,
} from './quotaTelemetryParser';

export const ProviderQuotaAnalyticsModal: React.FC = () => {
  const {
    providers,
    activeProviderId,
    isAnalyticsModalOpen,
    modelDistributions,
    agentUsages,
    dailyTrends,
    setAnalyticsModalOpen,
  } = useProviderQuotaStore();

  const currentProvider = providers[activeProviderId];

  // Esc 键关闭监听
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') {
        setAnalyticsModalOpen(false);
      }
    };

    if (isAnalyticsModalOpen) {
      window.addEventListener('keydown', handleKeyDown);
    }

    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isAnalyticsModalOpen, setAnalyticsModalOpen]);

  if (!isAnalyticsModalOpen || !currentProvider) {
    return null;
  }

  const remainingDays = estimateRemainingDays(
    currentProvider.balanceUsd,
    currentProvider.dailyBurnRateUsd
  );

  const handleExportCsv = (): void => {
    const csvContent =
      'Date,TokensConsumed,CostUSD\n' +
      dailyTrends
        .map((t) => `${t.date},${t.tokensConsumed},${t.costUsd}`)
        .join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `quota_usage_${currentProvider.id}.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  return (
    <dialog
      open
      data-testid="provider-quota-analytics-modal-backdrop"
      aria-modal="true"
      aria-label="全景 Token 经济学与算力配额遥测"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 overflow-y-auto bg-transparent border-none m-0 max-w-none max-h-none w-full h-full"
    >
      {/* 遮罩背景点击层 */}
      <div
        aria-hidden="true"
        data-testid="modal-backdrop-overlay"
        className="fixed inset-0 bg-black/70 backdrop-blur-sm"
        onClick={() => {
          setAnalyticsModalOpen(false);
        }}
      />

      <div
        data-testid="provider-quota-analytics-modal-content"
        className="relative z-10 w-full max-w-3xl rounded-2xl border border-neutral-800 bg-neutral-900 text-neutral-100 shadow-2xl p-6 space-y-6 overflow-hidden"
      >
        {/* 顶部标题栏与关闭 */}
        <div className="flex items-center justify-between border-b border-neutral-800 pb-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/20 text-indigo-400">
              <BarChart3 className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-white">
                全景 Token 经济学与算力配额遥测
              </h2>
              <p className="text-xs text-neutral-400 font-mono">
                当前活跃提供商：{currentProvider.name} (
                {currentProvider.modelIdentifier})
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              data-testid="export-csv-btn"
              onClick={handleExportCsv}
              className="flex items-center gap-1.5 rounded-lg border border-neutral-700 bg-neutral-800 px-3 py-1.5 text-xs text-neutral-200 hover:bg-neutral-700 hover:text-white transition-colors"
            >
              <Download className="h-3.5 w-3.5" />
              <span>导出账单 CSV</span>
            </button>

            <button
              type="button"
              data-testid="close-analytics-modal-btn"
              onClick={() => {
                setAnalyticsModalOpen(false);
              }}
              className="rounded-lg p-1 text-neutral-400 hover:bg-neutral-800 hover:text-white transition-colors"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* 四维核心遥测指标卡片 */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div className="rounded-xl border border-neutral-800 bg-neutral-950/60 p-3.5">
            <div className="flex items-center gap-1 text-[11px] text-neutral-400 font-mono mb-1">
              <DollarSign className="h-3.5 w-3.5 text-emerald-400" />
              <span>账户可用余额</span>
            </div>
            <div
              className="text-lg font-bold font-mono text-emerald-400"
              data-testid="analytics-balance-usd"
            >
              {formatCurrency(currentProvider.balanceUsd)}
            </div>
            <div className="text-[10px] text-neutral-500">
              初始充值 {formatCurrency(currentProvider.initialDepositUsd)}
            </div>
          </div>

          <div className="rounded-xl border border-neutral-800 bg-neutral-950/60 p-3.5">
            <div className="flex items-center gap-1 text-[11px] text-neutral-400 font-mono mb-1">
              <Zap className="h-3.5 w-3.5 text-indigo-400" />
              <span>剩余配额占比</span>
            </div>
            <div
              className="text-lg font-bold font-mono text-indigo-400"
              data-testid="analytics-percentage"
            >
              {currentProvider.remainingPercentage}%
            </div>
            <div className="text-[10px] text-neutral-500">
              余 {formatTokenCount(currentProvider.remainingTokens)} /{' '}
              {formatTokenCount(currentProvider.totalTokensLimit)}
            </div>
          </div>

          <div className="rounded-xl border border-neutral-800 bg-neutral-950/60 p-3.5">
            <div className="flex items-center gap-1 text-[11px] text-neutral-400 font-mono mb-1">
              <Flame className="h-3.5 w-3.5 text-amber-400" />
              <span>日均燃尽速率</span>
            </div>
            <div
              className="text-lg font-bold font-mono text-amber-400"
              data-testid="analytics-burn-rate"
            >
              {formatCurrency(currentProvider.dailyBurnRateUsd)}/天
            </div>
            <div className="text-[10px] text-neutral-500">近 7 日加权计算</div>
          </div>

          <div className="rounded-xl border border-neutral-800 bg-neutral-950/60 p-3.5">
            <div className="flex items-center gap-1 text-[11px] text-neutral-400 font-mono mb-1">
              <Clock className="h-3.5 w-3.5 text-cyan-400" />
              <span>预估可用天数</span>
            </div>
            <div
              className="text-lg font-bold font-mono text-cyan-400"
              data-testid="analytics-remaining-days"
            >
              {remainingDays} 天
            </div>
            <div className="text-[10px] text-neutral-500">基于当前消耗速率</div>
          </div>
        </div>

        {/* 模型消耗分布百分比进度条与智能体消耗 */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* 左侧：模型用量占比 */}
          <div className="rounded-xl border border-neutral-800 bg-neutral-950/50 p-4 space-y-3">
            <div className="flex items-center justify-between text-xs font-semibold text-neutral-300">
              <span className="flex items-center gap-1.5">
                <PieChart className="h-4 w-4 text-indigo-400" />
                模型 Token 消耗占比 (Percentages)
              </span>
              <span className="font-mono text-[11px] text-neutral-500">
                按使用量
              </span>
            </div>

            <div className="space-y-2.5">
              {modelDistributions.map((model) => (
                <div key={model.modelName} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-medium text-neutral-200">
                      {model.modelName}
                    </span>
                    <span className="font-mono text-neutral-400">
                      {formatTokenCount(model.tokenCount)} ({model.percentage}%)
                    </span>
                  </div>
                  <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-800">
                    <div
                      className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-cyan-400 transition-all duration-300"
                      style={{ width: `${model.percentage}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* 右侧：按智能体角色分类开销 */}
          <div className="rounded-xl border border-neutral-800 bg-neutral-950/50 p-4 space-y-3">
            <div className="flex items-center justify-between text-xs font-semibold text-neutral-300">
              <span className="flex items-center gap-1.5">
                <Bot className="h-4 w-4 text-purple-400" />
                智能体角色消耗明细
              </span>
              <span className="font-mono text-[11px] text-neutral-500">
                任务数 / 费用
              </span>
            </div>

            <div className="space-y-2">
              {agentUsages.map((agent) => (
                <div
                  key={agent.agentRole}
                  className="flex items-center justify-between rounded-lg bg-neutral-900/80 px-2.5 py-1.5 text-xs border border-neutral-800/80"
                >
                  <div className="truncate">
                    <div className="font-medium text-neutral-200 truncate">
                      {agent.agentRole}
                    </div>
                    <div className="text-[10px] text-neutral-500 font-mono">
                      {agent.taskCount} 项任务 ·{' '}
                      {formatTokenCount(agent.tokenCount)} Tokens
                    </div>
                  </div>
                  <div className="font-mono font-semibold text-emerald-400 shrink-0">
                    {formatCurrency(agent.costUsd)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 底部：7 日消耗走势预览 */}
        <div className="rounded-xl border border-neutral-800 bg-neutral-950/50 p-4 space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-neutral-300">
            <Calendar className="h-4 w-4 text-emerald-400" />
            <span>近 7 日算力消耗走势</span>
          </div>

          <div className="grid grid-cols-7 gap-2 pt-2">
            {dailyTrends.map((trend) => (
              <div
                key={trend.date}
                className="flex flex-col items-center justify-end rounded-lg bg-neutral-900/60 p-2 text-center border border-neutral-800/60"
              >
                <div className="font-mono text-[11px] font-bold text-neutral-200 mb-1">
                  {formatCurrency(trend.costUsd)}
                </div>
                <div
                  className="w-full rounded-t bg-indigo-500/40 hover:bg-indigo-500 transition-colors"
                  style={{
                    height: `${Math.min(
                      60,
                      Math.max(12, (trend.costUsd / 6.0) * 50)
                    )}px`,
                  }}
                />
                <div className="mt-1 font-mono text-[10px] text-neutral-500">
                  {trend.date}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </dialog>
  );
};
