/**
 * [INPUT]
 * - react (POS: UI 组件状态与交互钩子)
 * - lucide-react (POS: 矢量图标库，包含 Bot, Database, Box, HardDrive, RefreshCw, AlertTriangle, ShieldCheck, Stethoscope, CheckCircle2, XCircle, ArrowRight)
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind 样式合并纯函数)
 *
 * [OUTPUT]
 * - InfraQuotaCockpit: 每用户/组织多 Agent 基础设施配额驾驶舱与准入门禁组件
 * - InfraQuotaCockpitProps: 组件属性契约
 * - ResourceQuotaItem: 单项资源额度契约
 * - InfraQuotaData: 驾驶舱全量数据契约
 *
 * [POS]
 * 对话窗口与 Fleet 管理页基础设施配额治理驾驶舱（AgentPerUserMultiAgentInfraQuotaGovernancePack）。
 * 呈现活跃 Agent、临时 DB、并发沙箱与持久 Volume 四维资源水位、准入门禁核验与 Doctor 降本调优建议。
 */
import React, { useState } from 'react';
import {
  Bot,
  Database,
  Box,
  HardDrive,
  RefreshCw,
  AlertTriangle,
  ShieldCheck,
  Stethoscope,
  CheckCircle2,
  XCircle,
  Laptop,
  Cloud,
  ChevronRight,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export type ResourceType =
  | 'active_agents'
  | 'ephemeral_dbs'
  | 'concurrent_sandboxes'
  | 'volume_storage_gb';

export type QuotaStatus = 'normal' | 'warning' | 'critical' | 'exhausted';

export interface ResourceQuotaItem {
  resourceType: ResourceType;
  displayName: string;
  used: number;
  limit: number;
  unit: string;
  usagePct: number;
  status: QuotaStatus;
}

export interface InfraQuotaData {
  userId: string;
  isLocalMode: boolean;
  quotas: ResourceQuotaItem[];
  doctorRecommendations: string[];
}

export interface InfraQuotaCockpitProps {
  data: InfraQuotaData;
  isLoading?: boolean;
  onRefresh?: () => Promise<void> | void;
  onCheckQuota?: (
    resourceType: ResourceType,
    amount: number
  ) => Promise<{
    allowed: boolean;
    rejectionReason?: string;
    remediationSteps?: string[];
  }>;
  className?: string;
}

function getResourceIcon(type: ResourceType): React.ReactElement {
  switch (type) {
    case 'active_agents':
      return <Bot className="w-4 h-4 text-sky-500 shrink-0" />;
    case 'ephemeral_dbs':
      return <Database className="w-4 h-4 text-indigo-500 shrink-0" />;
    case 'concurrent_sandboxes':
      return <Box className="w-4 h-4 text-amber-500 shrink-0" />;
    case 'volume_storage_gb':
      return <HardDrive className="w-4 h-4 text-emerald-500 shrink-0" />;
  }
}

function getStatusBadgeClass(status: QuotaStatus): string {
  switch (status) {
    case 'exhausted':
      return 'bg-rose-500/10 text-rose-600 border-rose-500/30';
    case 'critical':
      return 'bg-amber-500/10 text-amber-600 border-amber-500/30';
    case 'warning':
      return 'bg-yellow-500/10 text-yellow-600 border-yellow-500/30';
    case 'normal':
    default:
      return 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30';
  }
}

function getProgressBarClass(status: QuotaStatus): string {
  switch (status) {
    case 'exhausted':
      return 'bg-rose-500';
    case 'critical':
      return 'bg-amber-500';
    case 'warning':
      return 'bg-yellow-500';
    case 'normal':
    default:
      return 'bg-emerald-500';
  }
}

export const InfraQuotaCockpit: React.FC<InfraQuotaCockpitProps> = ({
  data,
  isLoading = false,
  onRefresh,
  onCheckQuota,
  className,
}) => {
  const [selectedResource, setSelectedResource] = useState<ResourceType>('active_agents');
  const [checkAmount, setCheckAmount] = useState<number>(1);
  const [isChecking, setIsChecking] = useState<boolean>(false);
  const [checkResult, setCheckResult] = useState<{
    allowed: boolean;
    rejectionReason?: string;
    remediationSteps?: string[];
  } | null>(null);

  const handleSimulateCheck = async (): Promise<void> => {
    if (!onCheckQuota || checkAmount <= 0) {
      return;
    }
    try {
      setIsChecking(true);
      const res = await onCheckQuota(selectedResource, checkAmount);
      setCheckResult(res);
    } finally {
      setIsChecking(false);
    }
  };

  return (
    <div
      data-testid="infra-quota-cockpit"
      className={cn(
        'w-full max-w-2xl rounded-xl border border-border/80 bg-card/95 text-card-foreground shadow-sm overflow-hidden text-xs transition-all',
        className
      )}
    >
      {/* 头部：标题与部署模式 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/50 bg-muted/20">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <ShieldCheck className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-sm text-foreground">
                多 Agent 基础设施配额治理驾驶舱
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground border border-border/40 flex items-center gap-1">
                {data.isLocalMode ? (
                  <>
                    <Laptop className="w-3 h-3 text-emerald-500" /> 单机物理沙箱模式
                  </>
                ) : (
                  <>
                    <Cloud className="w-3 h-3 text-sky-500" /> 云托管组织配额模式
                  </>
                )}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              治理对象: <span className="font-mono">{data.userId}</span> · 四大核心计算与存储资源水位
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {onRefresh && (
            <button
              type="button"
              data-testid="refresh-quota-btn"
              onClick={onRefresh}
              disabled={isLoading}
              className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            >
              <RefreshCw className={cn('w-3.5 h-3.5', isLoading && 'animate-spin')} />
            </button>
          )}
        </div>
      </div>

      {/* 四大维度配额卡片网格 */}
      <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-3" data-testid="quota-cards-grid">
        {data.quotas.map((item) => (
          <div
            key={item.resourceType}
            className="p-3 rounded-lg border border-border/60 bg-background/80 space-y-2 hover:border-border transition-colors"
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5 font-medium text-foreground">
                {getResourceIcon(item.resourceType)}
                <span>{item.displayName}</span>
              </div>
              <span
                className={cn(
                  'px-1.5 py-0.5 rounded text-[9px] font-mono uppercase border font-semibold',
                  getStatusBadgeClass(item.status)
                )}
              >
                {item.status}
              </span>
            </div>

            {/* 数值与单位 */}
            <div className="flex items-baseline justify-between text-[11px]">
              <span className="text-muted-foreground">已占用 / 额度:</span>
              <span className="font-mono font-semibold text-foreground">
                {item.used.toLocaleString()} / {item.limit.toLocaleString()}{' '}
                <span className="text-[10px] text-muted-foreground font-normal">{item.unit}</span>
              </span>
            </div>

            {/* 进度条 */}
            <div className="space-y-1">
              <div className="w-full h-1.5 rounded-full bg-muted overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all duration-300',
                    getProgressBarClass(item.status)
                  )}
                  style={{ width: `${Math.min(100, item.usagePct)}%` }}
                />
              </div>
              <div className="text-right text-[10px] font-mono text-muted-foreground">
                {item.usagePct}%
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Doctor 智能降本排障建议 */}
      <div className="px-4 pb-3">
        <div
          data-testid="doctor-recommendations-panel"
          className="p-3 rounded-lg bg-muted/30 border border-border/50 space-y-1.5"
        >
          <div className="font-semibold text-foreground flex items-center gap-1.5 text-[11px]">
            <Stethoscope className="w-3.5 h-3.5 text-primary" />
            Doctor 基础设施降本与容量建议
          </div>
          <div className="space-y-1">
            {data.doctorRecommendations.map((rec, i) => (
              <p key={i} className="text-[11px] text-muted-foreground leading-relaxed flex items-start gap-1">
                <ChevronRight className="w-3 h-3 text-primary shrink-0 mt-0.5" />
                <span>{rec}</span>
              </p>
            ))}
          </div>
        </div>
      </div>

      {/* 自助 Provision 准入门禁试算器 */}
      {onCheckQuota && (
        <div className="px-4 pb-4">
          <div
            data-testid="quota-check-simulator"
            className="p-3 rounded-lg bg-background border border-border/80 space-y-2.5"
          >
            <div className="font-semibold text-foreground flex items-center justify-between text-[11px]">
              <span className="flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-sky-500" />
                自助 Provision 准入门禁核验 (Fail-Closed)
              </span>
              <span className="text-[10px] text-muted-foreground font-normal">
                创建或启动前预先校验
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <select
                aria-label="选择申请资源类型"
                value={selectedResource}
                onChange={(e) => setSelectedResource(e.target.value as ResourceType)}
                className="px-2 py-1 rounded border border-border bg-muted/40 text-[11px] text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
              >
                {data.quotas.map((q) => (
                  <option key={q.resourceType} value={q.resourceType}>
                    {q.displayName} ({q.unit})
                  </option>
                ))}
              </select>

              <input
                aria-label="输入拟申请量"
                type="number"
                min="1"
                max="500"
                value={checkAmount}
                onChange={(e) => setCheckAmount(Number(e.target.value))}
                className="w-16 px-2 py-1 rounded border border-border bg-muted/40 text-[11px] text-foreground font-mono focus:outline-none focus:ring-1 focus:ring-primary"
              />

              <button
                type="button"
                data-testid="simulate-check-btn"
                disabled={isChecking}
                onClick={handleSimulateCheck}
                className="px-2.5 py-1 rounded bg-primary text-primary-foreground font-medium text-[11px] hover:bg-primary/90 transition-colors flex items-center gap-1 disabled:opacity-50"
              >
                {isChecking ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                准入核验
              </button>
            </div>

            {/* 核验结果反馈 */}
            {checkResult && (
              <div
                data-testid="check-result-box"
                className={cn(
                  'p-2.5 rounded border text-[11px] space-y-1',
                  checkResult.allowed
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-800 dark:text-emerald-300'
                    : 'bg-rose-500/10 border-rose-500/30 text-rose-800 dark:text-rose-300'
                )}
              >
                <div className="font-semibold flex items-center gap-1.5">
                  {checkResult.allowed ? (
                    <>
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                      准入核准通过：余量充足，允许即时分配
                    </>
                  ) : (
                    <>
                      <XCircle className="w-3.5 h-3.5 text-rose-500" />
                      Fail-Closed 拦截：资源超限，已阻断分配
                    </>
                  )}
                </div>

                {checkResult.rejectionReason && (
                  <p className="text-[10px] leading-relaxed">{checkResult.rejectionReason}</p>
                )}

                {checkResult.remediationSteps && checkResult.remediationSteps.length > 0 && (
                  <div className="space-y-0.5 pt-1 text-[10px]">
                    <div className="font-medium">建议修复路径:</div>
                    {checkResult.remediationSteps.map((step, idx) => (
                      <div key={idx} className="flex items-center gap-1">
                        • {step}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 底部信息条 */}
      <div className="px-4 py-2 border-t border-border/50 bg-muted/10 text-[10px] text-muted-foreground flex items-center justify-between">
        <span>基于 TiDB Agent Stack 范式：计算与存储单位直达 Agent 自身</span>
        <span className="font-mono">4 维基础设施全量受控</span>
      </div>
    </div>
  );
};
