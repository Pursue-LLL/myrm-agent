// @orphan-ok Object-Capability (OCap) violation interception alert card for subagent boundaries
'use client';

import React, { useState } from 'react';
import {
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  AlertOctagon,
  Clock,
  Cpu,
  FileCode,
  Globe,
  Terminal,
  CheckCircle2,
  Ban,
  Loader2,
} from 'lucide-react';

export interface CapabilityViolationIncident {
  incidentId: string;
  capabilityId: string;
  subagentRole?: string;
  action: 'read' | 'write' | 'execute' | 'egress' | 'mcp';
  target: string;
  violationReason: string;
  interceptedAt?: string;
  isDismissed?: boolean;
}

interface CapabilityViolationAlertCardProps {
  incident: CapabilityViolationIncident;
  onDismiss?: (incidentId: string) => void;
  onViewAudit?: () => void;
  onRevoke?: (capabilityId: string) => Promise<void> | void;
  className?: string;
}

const getActionIcon = (action: CapabilityViolationIncident['action']) => {
  switch (action) {
    case 'read':
    case 'write':
      return <FileCode className="h-4 w-4" />;
    case 'execute':
      return <Terminal className="h-4 w-4" />;
    case 'egress':
      return <Globe className="h-4 w-4" />;
    case 'mcp':
      return <Cpu className="h-4 w-4" />;
    default:
      return <AlertOctagon className="h-4 w-4" />;
  }
};

const getActionLabel = (action: CapabilityViolationIncident['action']) => {
  switch (action) {
    case 'read':
      return '读取未授权文件';
    case 'write':
      return '写入未授权路径';
    case 'execute':
      return '执行未授权命令';
    case 'egress':
      return '未授权外网请求';
    case 'mcp':
      return '未授权 MCP 工具调用';
    default:
      return '未授权操作';
  }
};

export const CapabilityViolationAlertCard: React.FC<CapabilityViolationAlertCardProps> = ({
  incident,
  onDismiss,
  onViewAudit,
  onRevoke,
  className = '',
}) => {
  const [showDetails, setShowDetails] = useState(false);
  const [isDismissed, setIsDismissed] = useState(incident.isDismissed ?? false);
  const [isRevoking, setIsRevoking] = useState(false);
  const [isRevoked, setIsRevoked] = useState(false);

  const handleDismiss = () => {
    setIsDismissed(true);
    if (onDismiss) {
      onDismiss(incident.incidentId);
    }
  };

  const handleRevoke = async () => {
    if (!onRevoke || isRevoking) {
      return;
    }
    try {
      setIsRevoking(true);
      await onRevoke(incident.capabilityId);
      setIsRevoked(true);
    } finally {
      setIsRevoking(false);
    }
  };

  if (isRevoked) {
    return (
      <div
        className={`w-full max-w-2xl rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-xs text-foreground flex items-center justify-between ${className}`}
        data-testid="capability-violation-alert-revoked"
      >
        <span className="flex items-center gap-1.5 font-medium text-destructive">
          <Ban className="h-4 w-4" />
          该权能句柄已即时级联撤销并熔断 (ID: {incident.capabilityId.slice(0, 10)})
        </span>
      </div>
    );
  }

  if (isDismissed) {
    return (
      <div
        className={`w-full max-w-2xl rounded-lg border border-border/40 bg-muted/30 p-3 text-xs text-muted-foreground flex items-center justify-between ${className}`}
        data-testid="capability-violation-alert-dismissed"
      >
        <span className="flex items-center gap-1.5 font-medium">
          <CheckCircle2 className="h-4 w-4 text-emerald-500" />
          该越界调用已拦截并确认为安全隔离事件 (ID: {incident.incidentId.slice(0, 8)})
        </span>
      </div>
    );
  }

  return (
    <div
      className={`w-full max-w-2xl rounded-xl border border-destructive/30 bg-destructive/5 dark:bg-destructive/10 p-4 sm:p-5 shadow-sm transition-all duration-200 ${className}`}
      role="alert"
      aria-live="assertive"
      data-testid="capability-violation-alert-card"
    >
      <div className="flex items-start gap-3 sm:gap-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-destructive/15 text-destructive">
          <ShieldAlert className="h-5 w-5" />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="text-sm sm:text-base font-semibold text-foreground flex items-center gap-1.5">
              <span>零信任 OCap 拘禁：越界调用已被拦截</span>
            </h4>
            <span className="inline-flex items-center rounded-md bg-destructive/15 px-2 py-0.5 text-xs font-semibold text-destructive">
              强制阻断 (Fail-Closed)
            </span>
          </div>

          <p className="mt-1 text-xs sm:text-sm text-muted-foreground leading-relaxed">
            检测到子任务尝试执行超出其派生授权范围的操作。底层不可伪造能力句柄（OCap）已实时阻断该行为，未产生任何系统副作用。
          </p>

          <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs bg-background/60 dark:bg-background/40 p-2.5 rounded-lg border border-border/40 font-mono">
            <div className="flex items-center gap-1.5 text-foreground">
              <span className="text-muted-foreground font-sans">拦截操作:</span>
              <span className="flex items-center gap-1 font-semibold text-destructive">
                {getActionIcon(incident.action)}
                {incident.action.toUpperCase()} ({getActionLabel(incident.action)})
              </span>
            </div>

            <div className="flex items-center gap-1.5 text-foreground">
              <span className="text-muted-foreground font-sans">受限主体:</span>
              <span className="truncate max-w-[150px]" title={incident.subagentRole ?? incident.capabilityId}>
                {incident.subagentRole ?? incident.capabilityId.slice(0, 10)}
              </span>
            </div>

            <div className="flex items-center gap-1.5 text-foreground col-span-1 sm:col-span-2">
              <span className="text-muted-foreground font-sans shrink-0">越界目标:</span>
              <span className="truncate max-w-full text-foreground font-medium" title={incident.target}>
                {incident.target}
              </span>
            </div>

            {incident.interceptedAt && (
              <div className="flex items-center gap-1.5 text-muted-foreground col-span-1 sm:col-span-2 text-[11px]">
                <Clock className="h-3 w-3 shrink-0" />
                <span>拦截时刻: {incident.interceptedAt}</span>
              </div>
            )}
          </div>

          {showDetails && (
            <div className="mt-3 rounded-lg bg-background/80 dark:bg-background/60 p-3 text-xs text-muted-foreground border border-border/50 space-y-2">
              <div>
                <span className="font-semibold text-foreground">阻断原因：</span>
                <p className="mt-0.5 text-foreground/90 font-mono text-[11px] leading-relaxed">
                  {incident.violationReason}
                </p>
              </div>

              <div className="flex justify-between items-center pt-2 border-t border-border/40 text-[11px]">
                <span>能力句柄:</span>
                <span className="font-mono text-foreground font-semibold">{incident.capabilityId}</span>
              </div>
              <div className="flex justify-between items-center text-[11px]">
                <span>安全模型:</span>
                <span className="font-mono text-emerald-600 dark:text-emerald-400">
                  Object-Capability Non-Forging Token
                </span>
              </div>
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2 sm:gap-3">
            <button
              type="button"
              onClick={handleDismiss}
              className="inline-flex items-center justify-center rounded-lg bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground hover:bg-secondary/80 focus:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
            >
              我知道了并确认安全
            </button>

            {onRevoke && (
              <button
                type="button"
                onClick={handleRevoke}
                disabled={isRevoking}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-destructive px-3 py-1.5 text-xs font-medium text-destructive-foreground hover:bg-destructive/90 focus:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors disabled:opacity-50"
                data-testid="capability-revoke-button"
              >
                {isRevoking ? (
                  <>
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    <span>正在撤销...</span>
                  </>
                ) : (
                  <>
                    <Ban className="h-3.5 w-3.5" />
                    <span>立即撤销授权并熔断</span>
                  </>
                )}
              </button>
            )}

            {onViewAudit && (
              <button
                type="button"
                onClick={onViewAudit}
                className="inline-flex items-center justify-center rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent hover:text-accent-foreground focus:outline-none focus-visible:ring-1 focus-visible:ring-ring transition-colors"
              >
                查看安全审计详情
              </button>
            )}

            <button
              type="button"
              onClick={() => setShowDetails(!showDetails)}
              className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground rounded-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background transition-colors"
              aria-expanded={showDetails}
            >
              <span>{showDetails ? '收起详情' : '展开证据链'}</span>
              {showDetails ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
