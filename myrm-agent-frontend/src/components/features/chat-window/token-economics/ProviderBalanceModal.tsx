/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Consistent vector icons)
 * - @/components/features/chat-window/token-economics/tokenEconomicsTypes
 * - @/components/features/chat-window/token-economics/tokenEconomicsEngine
 * - @/components/features/chat-window/token-economics/useTokenEconomicsStore
 *
 * [OUTPUT]
 * - ProviderBalanceModal (POS: Self-inspection modal for upstream provider account balances)
 *
 * [POS]
 * Primary modal for Item 193 (P1).
 * Displays live balance probes, watermark levels, and quota consumption across mainstream LLM providers.
 */

import React, { useEffect, useCallback } from 'react';
import Link from 'next/link';
import {
  X,
  RefreshCw,
  Wallet,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  ExternalLink,
} from 'lucide-react';
import type {
  BalanceWatermarkLevel,
  ProviderBalanceInfo,
} from './tokenEconomicsTypes';
import { formatCurrencyAmount } from './tokenEconomicsEngine';
import { useTokenEconomicsStore } from './useTokenEconomicsStore';

export interface ProviderBalanceModalProps {
  readonly onClose?: () => void;
  readonly className?: string;
}

function getWatermarkBadge(level: BalanceWatermarkLevel) {
  switch (level) {
    case 'healthy': {
      return {
        label: '额度充盈',
        icon: <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />,
        badgeClass: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
        progressClass: '[&::-webkit-progress-value]:bg-emerald-500 [&::-moz-progress-bar]:bg-emerald-500',
      };
    }
    case 'warning': {
      return {
        label: '水位偏低',
        icon: <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />,
        badgeClass: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
        progressClass: '[&::-webkit-progress-value]:bg-amber-500 [&::-moz-progress-bar]:bg-amber-500',
      };
    }
    case 'critical': {
      return {
        label: '额度告急',
        icon: <AlertCircle className="w-3.5 h-3.5 text-rose-500" />,
        badgeClass: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20',
        progressClass: '[&::-webkit-progress-value]:bg-rose-500 [&::-moz-progress-bar]:bg-rose-500',
      };
    }
  }
}

export const ProviderBalanceModal: React.FC<ProviderBalanceModalProps> = ({
  onClose,
  className = '',
}) => {
  const isBalanceModalOpen = useTokenEconomicsStore((state) => state.isBalanceModalOpen);
  const providerBalances = useTokenEconomicsStore((state) => state.providerBalances);
  const isLoadingBalances = useTokenEconomicsStore((state) => state.isLoadingBalances);
  const toggleBalanceModal = useTokenEconomicsStore((state) => state.toggleBalanceModal);
  const refreshProviderBalances = useTokenEconomicsStore((state) => state.refreshProviderBalances);

  const handleClose = useCallback(() => {
    toggleBalanceModal(false);
    if (onClose) {
      onClose();
    }
  }, [toggleBalanceModal, onClose]);

  // 支持键盘 Escape 关闭
  useEffect(() => {
    if (!isBalanceModalOpen) {
      return;
    }

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        handleClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isBalanceModalOpen, handleClose]);

  if (!isBalanceModalOpen) {
    return null;
  }

  const balancesList = Object.values(providerBalances);

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="provider-balance-modal-title"
      data-testid="provider-balance-modal"
      onCancel={handleClose}
      className={`fixed inset-0 z-50 m-0 flex h-full w-full max-h-none max-w-none items-center justify-center bg-transparent p-4 border-none ${className}`}
    >
      {/* 语义化全屏背景遮罩按钮 */}
      <button
        type="button"
        aria-label="关闭背景遮罩"
        data-testid="provider-balance-backdrop"
        onClick={handleClose}
        className="fixed inset-0 -z-10 h-full w-full bg-black/60 backdrop-blur-sm cursor-default border-none p-0 m-0"
      />

      <div className="relative w-full max-w-2xl max-h-[85vh] flex flex-col rounded-xl border border-border bg-card shadow-2xl overflow-hidden">
        {/* 对话框头部 */}
        <div className="flex items-center justify-between border-b border-border/80 px-5 py-3.5 bg-muted/30">
          <div className="flex items-center gap-2">
            <Wallet className="w-4 h-4 text-primary" />
            <h3 id="provider-balance-modal-title" className="text-sm font-semibold text-foreground">
              Provider 账户余额即时自省
            </h3>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                void refreshProviderBalances();
              }}
              disabled={isLoadingBalances}
              title="重新探测刷新余额"
              aria-label="重新探测刷新余额"
              className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoadingBalances ? 'animate-spin text-primary' : ''}`} />
              <span>{isLoadingBalances ? '探测中...' : '刷新'}</span>
            </button>

            <button
              type="button"
              onClick={handleClose}
              title="关闭对话框"
              aria-label="关闭对话框"
              className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* 说明副标题 */}
        <div className="px-5 py-2.5 bg-muted/10 border-b border-border/40 text-xs text-muted-foreground">
          通过安全 RPC 代理探针读取当前已绑定 API Key 的可用配额与余额水位，消除长任务调用黑盒焦虑。
        </div>

        {/* 账户余额卡片列表 */}
        <div className="flex-1 overflow-y-auto p-5 grid grid-cols-1 sm:grid-cols-2 gap-3">
          {balancesList.map((info: ProviderBalanceInfo) => {
            const badge = getWatermarkBadge(info.watermarkLevel);
            const totalQuota = info.totalQuota ?? info.availableBalance;
            const progressValue = totalQuota > 0 ? Math.min(100, Math.round((info.availableBalance / totalQuota) * 100)) : 100;

            return (
              <div
                key={info.provider}
                data-testid={`balance-card-${info.provider}`}
                className="rounded-lg border border-border/70 bg-card/60 p-4 shadow-sm hover:shadow-md transition-all flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-semibold text-foreground text-sm">
                      {info.providerName}
                    </span>
                    <div
                      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${badge.badgeClass}`}
                    >
                      {badge.icon}
                      <span>{badge.label}</span>
                    </div>
                  </div>

                  <div className="mt-3 flex items-baseline gap-1">
                    <span className="text-xl font-bold font-mono text-foreground tracking-tight">
                      {formatCurrencyAmount(info.availableBalance, info.currency)}
                    </span>
                    {info.totalQuota ? (
                      <span className="text-xs text-muted-foreground">
                        / {formatCurrencyAmount(info.totalQuota, info.currency)}
                      </span>
                    ) : null}
                  </div>

                  {/* 语义化水位进度条 */}
                  <div className="mt-2.5">
                    <div className="flex justify-between text-[10px] text-muted-foreground mb-1">
                      <span>可用余量比例</span>
                      <span>{progressValue}%</span>
                    </div>
                    <progress
                      value={progressValue}
                      max={100}
                      aria-label={`${info.providerName} 可用余量`}
                      className={`h-1.5 w-full overflow-hidden rounded-full bg-secondary ${badge.progressClass}`}
                    />
                  </div>
                </div>

                <div className="mt-4 pt-2.5 border-t border-border/40 flex items-center justify-between text-[11px] text-muted-foreground">
                  <span>
                    {info.expiresAt ? `有效期至 ${info.expiresAt}` : '长期有效'}
                  </span>
                  <span className="text-[10px]">
                    探针状态: {info.status === 'active' ? '正常' : '异常'}
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* 底部按钮栏 */}
        <div className="flex items-center justify-between border-t border-border px-5 py-3 bg-muted/20">
          <Link
            href="/settings/models"
            className="inline-flex items-center gap-1 text-xs text-primary hover:underline font-medium"
          >
            <span>管理模型 Provider 与 API Key</span>
            <ExternalLink className="w-3 h-3" />
          </Link>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-lg bg-secondary px-4 py-1.5 text-xs font-medium text-secondary-foreground hover:bg-secondary/80 transition-colors"
          >
            完成查看
          </button>
        </div>
      </div>
    </dialog>
  );
};
