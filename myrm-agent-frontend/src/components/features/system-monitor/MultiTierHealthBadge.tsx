'use client';

/**
 * [INPUT]
 * - ./types::MultiTierHealthReportData, ProbeResultItem, HealthStatus (POS: 分层健康契约)
 * - lucide-react::Server, Radio, CheckCircle2, AlertTriangle, XCircle, Activity (POS: 视觉指示图标)
 *
 * [OUTPUT]
 * - MultiTierHealthBadge: 组件层与入口网关层分层健康巡检展示卡
 *
 * [POS]
 * src/components/features/system-monitor/MultiTierHealthBadge.tsx — 分层能力健康大盘视窗。
 */

import React from 'react';
import {
  Server,
  Radio,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Activity,
} from 'lucide-react';
import type { MultiTierHealthReportData, ProbeResultItem, HealthStatus } from './types';

const STATUS_CONFIG: Record<
  HealthStatus,
  { label: string; color: string; icon: React.ReactNode }
> = {
  healthy: {
    label: '全层健康 (HEALTHY)',
    color: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
    icon: <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />,
  },
  degraded: {
    label: '部分降级 (DEGRADED)',
    color: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
    icon: <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />,
  },
  unhealthy: {
    label: '核心异常 (UNHEALTHY)',
    color: 'bg-destructive/15 text-destructive border-destructive/30',
    icon: <XCircle className="w-4 h-4 text-destructive shrink-0" />,
  },
};

interface MultiTierHealthBadgeProps {
  report: MultiTierHealthReportData;
  className?: string;
}

export const MultiTierHealthBadge: React.FC<MultiTierHealthBadgeProps> = ({
  report,
  className = '',
}) => {
  if (!report) {
    return null;
  }

  const overall = STATUS_CONFIG[report.overall_status] || STATUS_CONFIG.unhealthy;
  const componentProbes = report.probes.filter((p) => p.tier === 'component');
  const ingressProbes = report.probes.filter((p) => p.tier === 'ingress');

  const renderProbeItem = (probe: ProbeResultItem) => {
    const statusMeta = STATUS_CONFIG[probe.status] || STATUS_CONFIG.unhealthy;
    return (
      <div
        key={probe.name}
        className="flex items-center justify-between p-2 rounded-lg bg-muted/20 border border-border/30 text-xs"
      >
        <div className="flex items-center gap-2 overflow-hidden">
          {statusMeta.icon}
          <span className="font-semibold text-foreground truncate">{probe.name}</span>
          {probe.is_core && (
            <span className="text-[10px] px-1 py-0.2 rounded bg-muted/50 text-muted-foreground font-mono">
              核心
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 shrink-0 text-muted-foreground font-mono text-[11px]">
          <span>{probe.message}</span>
          <span>{probe.latency_ms.toFixed(1)} ms</span>
        </div>
      </div>
    );
  };

  return (
    <div
      data-testid="multi-tier-health-badge"
      className={`rounded-xl border border-border/60 bg-background/50 p-4 space-y-4 ${className}`}
    >
      {/* 头部大盘裁决状态 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-border/40 pb-3">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-primary" />
          <h3 className="text-sm font-semibold text-foreground">
            系统能力分层健康巡检 (Multi-Tier Health)
          </h3>
        </div>
        <div
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium ${overall.color}`}
        >
          {overall.icon}
          <span>{overall.label}</span>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">{report.summary}</p>

      {/* 分层详情 */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Tier 1: 组件层 */}
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            <Server className="w-3.5 h-3.5 text-primary" />
            <span>组件支撑层 (Component Tier)</span>
          </div>
          <div className="space-y-1.5">{componentProbes.map(renderProbeItem)}</div>
        </div>

        {/* Tier 2: 入口网关层 */}
        <div className="space-y-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            <Radio className="w-3.5 h-3.5 text-cyan-500" />
            <span>入口网关层 (Ingress Tier)</span>
          </div>
          <div className="space-y-1.5">{ingressProbes.map(renderProbeItem)}</div>
        </div>
      </div>
    </div>
  );
};
