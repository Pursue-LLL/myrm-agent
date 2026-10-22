/**
 * UpgradePreFlightProbeCard - 多源网络前置体检大盘与智能镜像选择卡片
 *
 * [INPUT]
 * - probes: NetworkMirrorProbeResult[] 多源网络镜像体检数据
 * - selectedMirrorId: string 当前选中的镜像源标识
 * - onSelectMirror: (id: string) => void 切换选中镜像回调
 * - onRefreshProbes: () => void 重新探测网络延迟回调
 * - isProbing?: boolean 正在测速中
 *
 * [OUTPUT]
 * - UpgradePreFlightProbeCard: React.FC
 *
 * [POS]
 * 系统更新控制台前置网络体检面板。彻底根治 GitHub 官方源由于端口超时导致升级死寂、
 * 迫使用户中途 Ctrl+C 强退损坏环境的恶性体验痛点。
 */

import React from 'react';
import {
  AlertCircle,
  Check,
  CheckCircle2,
  Globe,
  RotateCw,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type {
  MirrorHealthStatus,
  NetworkMirrorProbeResult,
} from './upgradeCockpitTypes';

export interface UpgradePreFlightProbeCardProps {
  probes: NetworkMirrorProbeResult[];
  selectedMirrorId: string;
  onSelectMirror: (id: string) => void;
  onRefreshProbes: () => void;
  isProbing?: boolean;
}

function renderHealthBadge(status: MirrorHealthStatus) {
  switch (status) {
    case 'optimal':
      return (
        <span className="flex items-center gap-1 rounded bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
          <CheckCircle2 className="h-3 w-3" />
          <span>极速稳定</span>
        </span>
      );
    case 'healthy':
      return (
        <span className="flex items-center gap-1 rounded bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-medium text-blue-600 dark:text-blue-400">
          <Check className="h-3 w-3" />
          <span>连通正常</span>
        </span>
      );
    case 'degraded':
      return (
        <span className="flex items-center gap-1 rounded bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">
          <AlertCircle className="h-3 w-3" />
          <span>延迟较高</span>
        </span>
      );
    case 'blocked':
      return (
        <span className="flex items-center gap-1 rounded bg-rose-500/10 px-1.5 py-0.5 text-[10px] font-medium text-rose-600 dark:text-rose-400">
          <AlertCircle className="h-3 w-3" />
          <span>端口超时</span>
        </span>
      );
  }
}

export const UpgradePreFlightProbeCard: React.FC<UpgradePreFlightProbeCardProps> = ({
  probes,
  selectedMirrorId,
  onSelectMirror,
  onRefreshProbes,
  isProbing = false,
}) => {
  return (
    <div
      data-testid="upgrade-preflight-probe-card"
      className="rounded-xl border border-border/60 bg-card/60 p-4 shadow-sm"
    >
      {/* 头部标题与重测按钮 */}
      <div className="flex items-center justify-between pb-3 border-b border-border/40">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Globe className="h-4 w-4" />
          </div>
          <div>
            <h4 className="text-sm font-semibold text-foreground">
              前置网络诊断探针
            </h4>
            <p className="text-[11px] text-muted-foreground">
              多源跨境通道实时体检与一键切换，杜绝下载中断
            </p>
          </div>
        </div>

        <button
          type="button"
          data-testid="refresh-probes-btn"
          disabled={isProbing}
          onClick={() => {
            onRefreshProbes();
          }}
          className="flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
        >
          <RotateCw className={cn('h-3 w-3', isProbing && 'animate-spin')} />
          <span>{isProbing ? '正在体检...' : '重新测速'}</span>
        </button>
      </div>

      {/* 探针列表 */}
      <div className="mt-3 grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {probes.map((probe) => {
          const isSelected = selectedMirrorId === probe.id;
          return (
            <button
              type="button"
              key={probe.id}
              data-testid={`mirror-probe-item-${probe.id}`}
              onClick={() => {
                onSelectMirror(probe.id);
              }}
              className={cn(
                'group relative flex cursor-pointer flex-col justify-between rounded-lg border p-3 text-left transition-all',
                isSelected
                  ? 'border-primary/80 bg-primary/5 shadow-sm'
                  : 'border-border/50 bg-background/50 hover:border-primary/40 hover:bg-accent/20',
              )}
            >
              <div className="flex w-full items-start justify-between gap-2">
                <div className="space-y-0.5">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-semibold text-foreground">
                      {probe.name}
                    </span>
                    {probe.isRecommended && (
                      <span className="flex items-center gap-0.5 rounded bg-amber-500/10 px-1 py-0.2 text-[9px] font-medium text-amber-600 dark:text-amber-400">
                        <Zap className="h-2.5 w-2.5" />
                        <span>推荐</span>
                      </span>
                    )}
                  </div>
                  <p className="text-[10px] font-mono text-muted-foreground truncate max-w-[200px]">
                    {probe.endpointUrl}
                  </p>
                </div>
                {renderHealthBadge(probe.status)}
              </div>

              <div className="mt-2.5 flex w-full items-center justify-between text-[11px] border-t border-border/30 pt-2">
                <span className="text-muted-foreground">
                  往返延迟: <strong className="font-mono text-foreground">{probe.latencyMs}ms</strong>
                </span>
                <span className="text-[10px] text-muted-foreground">
                  {probe.statusDescription}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
};
