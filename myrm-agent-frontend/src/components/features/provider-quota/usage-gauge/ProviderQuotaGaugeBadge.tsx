/**
 * Provider Quota Gauge Badge Component
 * 顶部导航与状态栏常驻多渠道模型配额、余额与健康度仪表徽章
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. a11y 无障碍标准与键盘导航。
 */

import React, { useState, useRef, useEffect } from 'react';
import {
  Gauge,
  ChevronDown,
  Check,
  Zap,
  BarChart3,
  AlertTriangle,
  Cpu,
} from 'lucide-react';
import { ProviderId, ProviderQuotaSnapshot } from './providerQuotaTypes';
import { useProviderQuotaStore } from './useProviderQuotaStore';
import { formatCurrency, formatTokenCount } from './quotaTelemetryParser';

export interface ProviderQuotaGaugeBadgeProps {
  className?: string;
}

export const ProviderQuotaGaugeBadge: React.FC<
  ProviderQuotaGaugeBadgeProps
> = ({ className = '' }) => {
  const [isDropdownOpen, setIsDropdownOpen] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const {
    providers,
    activeProviderId,
    setActiveProvider,
    setAnalyticsModalOpen,
  } = useProviderQuotaStore();

  const activeProvider: ProviderQuotaSnapshot = providers[activeProviderId];

  // 点击外部收起下拉框
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent): void => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsDropdownOpen(false);
      }
    };

    if (isDropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isDropdownOpen]);

  const getStatusColor = (
    status: ProviderQuotaSnapshot['status']
  ): {
    badgeBorder: string;
    badgeBg: string;
    text: string;
    indicator: string;
    progress: string;
  } => {
    if (status === 'exhausted' || status === 'critical') {
      return {
        badgeBorder: 'border-rose-500/50',
        badgeBg: 'bg-rose-950/30',
        text: 'text-rose-400',
        indicator: 'bg-rose-500 animate-pulse',
        progress: 'bg-rose-500',
      };
    }
    if (status === 'warning') {
      return {
        badgeBorder: 'border-amber-500/50',
        badgeBg: 'bg-amber-950/30',
        text: 'text-amber-400',
        indicator: 'bg-amber-400',
        progress: 'bg-amber-400',
      };
    }
    return {
      badgeBorder: 'border-emerald-500/30',
      badgeBg: 'bg-emerald-950/20',
      text: 'text-emerald-400',
      indicator: 'bg-emerald-400',
      progress: 'bg-emerald-500',
    };
  };

  const colors = getStatusColor(activeProvider.status);

  return (
    <div
      ref={dropdownRef}
      className={`relative inline-flex items-center text-xs ${className}`}
      data-testid="provider-quota-gauge-root"
    >
      {/* 状态徽章主触发区 */}
      <div
        className={`flex items-center gap-2 rounded-full border px-2.5 py-1 backdrop-blur-md transition-all duration-200 select-none shadow-sm ${colors.badgeBorder} ${colors.badgeBg}`}
      >
        {/* 状态指示呼吸灯 */}
        <span
          className={`h-2 w-2 rounded-full ${colors.indicator}`}
          data-testid="quota-status-indicator"
        />

        {/* 提供商切换按钮 */}
        <button
          type="button"
          onClick={() => {
            setIsDropdownOpen((prev) => !prev);
          }}
          data-testid="provider-dropdown-toggle"
          className="flex items-center gap-1 font-medium text-neutral-200 hover:text-white transition-colors"
          title="点击切换模型提供商"
        >
          <Zap className="h-3.5 w-3.5 text-indigo-400" />
          <span className="font-mono text-[11px] truncate max-w-[120px]">
            {activeProvider.name}
          </span>
          <ChevronDown className="h-3 w-3 text-neutral-400" />
        </button>

        <span className="text-neutral-700">|</span>

        {/* 剩余进度条与百分比 */}
        <button
          type="button"
          onClick={() => {
            setAnalyticsModalOpen(true);
          }}
          data-testid="open-analytics-btn"
          className="flex items-center gap-1.5 hover:opacity-85 transition-opacity"
          title="点击打开全景用量分析与账单明细"
        >
          <div className="h-1.5 w-12 overflow-hidden rounded-full bg-neutral-800">
            <div
              className={`h-full transition-all duration-300 ${colors.progress}`}
              style={{ width: `${activeProvider.remainingPercentage}%` }}
              data-testid="quota-progress-fill"
            />
          </div>

          <span
            className={`font-mono text-[11px] font-semibold ${colors.text}`}
            data-testid="quota-percentage-text"
          >
            {activeProvider.remainingPercentage}%
          </span>

          {activeProvider.supportsLiveTelemetry && (
            <span
              className="font-mono text-[11px] text-neutral-400"
              data-testid="quota-balance-usd"
            >
              {formatCurrency(activeProvider.balanceUsd)}
            </span>
          )}

          <BarChart3 className="h-3 w-3 text-neutral-400 hover:text-neutral-200" />
        </button>
      </div>

      {/* 渠道下拉快捷选择卡片 */}
      {isDropdownOpen && (
        <div
          data-testid="provider-dropdown-menu"
          className="absolute right-0 top-full mt-2 z-50 w-72 rounded-xl border border-neutral-800 bg-neutral-900/95 p-2 shadow-2xl backdrop-blur-lg"
        >
          <div className="flex items-center justify-between px-2 py-1.5 text-[11px] text-neutral-400 font-mono border-b border-neutral-800/80 mb-1">
            <span className="flex items-center gap-1">
              <Gauge className="h-3.5 w-3.5 text-indigo-400" />
              可用提供商额度透视
            </span>
            <button
              type="button"
              onClick={() => {
                setIsDropdownOpen(false);
                setAnalyticsModalOpen(true);
              }}
              className="text-indigo-400 hover:underline"
            >
              时序大盘
            </button>
          </div>

          <div className="space-y-1">
            {(Object.keys(providers) as ProviderId[]).map((pId) => {
              const p = providers[pId];
              const isSelected = pId === activeProviderId;
              const pColors = getStatusColor(p.status);

              return (
                <button
                  type="button"
                  key={pId}
                  data-testid={`provider-option-${pId}`}
                  onClick={() => {
                    setActiveProvider(pId);
                    setIsDropdownOpen(false);
                  }}
                  className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors ${
                    isSelected
                      ? 'bg-neutral-800 text-white'
                      : 'text-neutral-300 hover:bg-neutral-800/60'
                  }`}
                >
                  <div className="flex items-center gap-2 truncate">
                    {p.id === 'local' ? (
                      <Cpu className="h-3.5 w-3.5 text-neutral-400 shrink-0" />
                    ) : (
                      <span
                        className={`h-2 w-2 rounded-full shrink-0 ${pColors.indicator}`}
                      />
                    )}
                    <div className="truncate">
                      <div className="font-medium truncate">{p.name}</div>
                      <div className="font-mono text-[10px] text-neutral-500 truncate">
                        {p.modelIdentifier}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 font-mono text-[11px] shrink-0">
                    <span className={pColors.text}>
                      {p.remainingPercentage}%
                    </span>
                    {isSelected && (
                      <Check className="h-3.5 w-3.5 text-indigo-400" />
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          {activeProvider.status === 'critical' && (
            <div className="mt-2 flex items-center gap-1.5 rounded-lg bg-rose-950/40 border border-rose-800/60 p-2 text-[11px] text-rose-300">
              <AlertTriangle className="h-3.5 w-3.5 text-rose-400 shrink-0" />
              <span>当前额度濒临耗尽，建议切换至备用渠道。</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
