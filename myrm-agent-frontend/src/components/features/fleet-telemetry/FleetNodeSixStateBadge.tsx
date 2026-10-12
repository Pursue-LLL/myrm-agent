'use client';

/**
 * [INPUT]
 * - @/services/fleetTelemetry::FleetNodeState, FleetDiagnoseParams, FleetDiagnosisResponse (POS: 机队遥测类型与服务)
 * - ./FleetDiagnosisDialog::FleetDiagnosisDialog (POS: 排障自省诊断弹窗)
 *
 * [OUTPUT]
 * - FleetNodeSixStateBadge: 分布式节点六态精细化健康徽章组件
 *
 * [POS]
 * 表现层/机队可观测性：以六态细粒度区分展示节点健康，杜绝将模型欠费等误报为通用网络断开，支持一键打开诊断弹窗。
 */

import React, { useState } from 'react';
import { type FleetNodeState, type FleetDiagnoseParams, type FleetDiagnosisResponse } from '@/services/fleetTelemetry';
import { FleetDiagnosisDialog } from './FleetDiagnosisDialog';
import { cn } from '@/lib/utils/classnameUtils';
import { AlertCircle, AlertTriangle, CheckCircle2, PowerOff, Settings2, Wrench } from 'lucide-react';

interface FleetNodeSixStateBadgeProps {
  state: FleetNodeState;
  nodeParams: FleetDiagnoseParams;
  initialReport?: FleetDiagnosisResponse | null;
  className?: string;
  showLabel?: boolean;
}

interface StateVisualConfig {
  label: string;
  dotColor: string;
  badgeBg: string;
  textColor: string;
  icon: React.FC<{ className?: string }>;
}

const STATE_CONFIG: Record<FleetNodeState, StateVisualConfig> = {
  online: {
    label: '在线运行',
    dotColor: 'bg-emerald-500',
    badgeBg: 'bg-emerald-500/10 border-emerald-500/20',
    textColor: 'text-emerald-600 dark:text-emerald-400',
    icon: CheckCircle2,
  },
  offline: {
    label: '物理离线',
    dotColor: 'bg-zinc-400',
    badgeBg: 'bg-zinc-500/10 border-zinc-500/20',
    textColor: 'text-zinc-500',
    icon: PowerOff,
  },
  misconfigured: {
    label: '凭据失效',
    dotColor: 'bg-orange-500',
    badgeBg: 'bg-orange-500/10 border-orange-500/20',
    textColor: 'text-orange-600 dark:text-orange-400',
    icon: Settings2,
  },
  provider_unavailable: {
    label: '⚠️ 模型欠费/超限',
    dotColor: 'bg-amber-500 animate-pulse',
    badgeBg: 'bg-amber-500/15 border-amber-500/30',
    textColor: 'text-amber-700 dark:text-amber-300 font-semibold',
    icon: AlertTriangle,
  },
  gateway_stopped: {
    label: '守护进程停止',
    dotColor: 'bg-rose-500',
    badgeBg: 'bg-rose-500/10 border-rose-500/20',
    textColor: 'text-rose-600 dark:text-rose-400',
    icon: AlertCircle,
  },
  runner_broken: {
    label: '沙箱容器异常',
    dotColor: 'bg-purple-500',
    badgeBg: 'bg-purple-500/10 border-purple-500/20',
    textColor: 'text-purple-600 dark:text-purple-400',
    icon: Wrench,
  },
};

export const FleetNodeSixStateBadge: React.FC<FleetNodeSixStateBadgeProps> = ({
  state,
  nodeParams,
  initialReport,
  className,
  showLabel = true,
}) => {
  const [dialogOpen, setDialogOpen] = useState<boolean>(false);
  const config = STATE_CONFIG[state] ?? STATE_CONFIG.offline;
  const Icon = config.icon;

  return (
    <>
      <button
        type="button"
        onClick={() => setDialogOpen(true)}
        title={`节点状态：${config.label}（点击进行五级自省排障）`}
        className={cn(
          'inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs border font-medium transition-all select-none cursor-pointer',
          'hover:shadow-2xs active:scale-98',
          config.badgeBg,
          config.textColor,
          className
        )}
      >
        <span className={cn('w-2 h-2 rounded-full flex-shrink-0', config.dotColor)} />
        <Icon className="w-3.5 h-3.5 flex-shrink-0" />
        {showLabel && <span>{config.label}</span>}
      </button>

      <FleetDiagnosisDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        nodeParams={nodeParams}
        initialReport={initialReport}
      />
    </>
  );
};
