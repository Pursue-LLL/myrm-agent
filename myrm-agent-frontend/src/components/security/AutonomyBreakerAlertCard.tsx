// @orphan-ok Data-driven autonomy circuit breaker exception governance alert card
'use client';

import React, { useState } from 'react';
import {
  ZapOff,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Clock,
  Terminal,
  RotateCcw,
  ShieldAlert,
  Loader2,
  CheckCircle,
} from 'lucide-react';
import type { AutonomyBreakerIncident } from './types';

interface AutonomyBreakerAlertCardProps {
  incident: AutonomyBreakerIncident;
  onAcknowledgeAndRecover?: (incidentId: string) => Promise<void> | void;
  onDegradeToManual?: (incidentId: string) => Promise<void> | void;
  onViewAudit?: () => void;
  className?: string;
}

const getAutonomyLevelLabel = (level: number): string => {
  switch (level) {
    case 1:
      return 'L1 建议模式 (只读)';
    case 2:
      return 'L2 协作审批 (单步确认)';
    case 3:
      return 'L3 监督执行 (批量审查)';
    case 4:
      return 'L4 条件自治 (异常触发)';
    case 5:
      return 'L5 隔离自治 (沙盒闭环)';
    default:
      return `L${level} 自治等级`;
  }
};

export const AutonomyBreakerAlertCard: React.FC<AutonomyBreakerAlertCardProps> = ({
  incident,
  onAcknowledgeAndRecover,
  onDegradeToManual,
  onViewAudit,
  className = '',
}) => {
  const [showDetails, setShowDetails] = useState<boolean>(false);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [actionDone, setActionDone] = useState<string | null>(null);

  const handleRecover = async (): Promise<void> => {
    if (isProcessing || !onAcknowledgeAndRecover) {
      return;
    }
    setIsProcessing(true);
    try {
      await onAcknowledgeAndRecover(incident.incidentId);
      setActionDone('recovered');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleDegrade = async (): Promise<void> => {
    if (isProcessing || !onDegradeToManual) {
      return;
    }
    setIsProcessing(true);
    try {
      await onDegradeToManual(incident.incidentId);
      setActionDone('degraded');
    } finally {
      setIsProcessing(false);
    }
  };

  if (actionDone) {
    return (
      <div
        className={`p-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 text-emerald-800 dark:text-emerald-300 text-sm flex items-center justify-between transition-all ${className}`}
        data-testid="autonomy-breaker-resolved"
      >
        <div className="flex items-center gap-2">
          <CheckCircle className="h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
          <span>
            {actionDone === 'recovered'
              ? '已确认恢复执行：断路器进入半开试探状态 (Half-Open)'
              : '已确认降级：系统已切换为严格协作审批模式 (L2)'}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`rounded-xl border border-rose-500/30 bg-rose-500/5 dark:bg-rose-950/20 backdrop-blur-sm p-4 sm:p-5 transition-all shadow-sm ${className}`}
      data-testid="autonomy-breaker-alert-card"
    >
      {/* 头部：标题与降级状态指示 */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-rose-500/10 dark:bg-rose-500/20 text-rose-600 dark:text-rose-400 shrink-0">
            <ZapOff className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h4 className="font-semibold text-sm sm:text-base text-rose-950 dark:text-rose-100">
                自主执行断路器跳闸熔断
              </h4>
              <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-rose-500/15 text-rose-700 dark:text-rose-300 border border-rose-500/20">
                10ms 物理阻断
              </span>
            </div>
            <p className="text-xs text-rose-800/80 dark:text-rose-300/80 mt-0.5">
              检测到工具异常重试或未授信动作，自治等级已由{' '}
              <span className="font-mono font-semibold underline">{getAutonomyLevelLabel(incident.previousLevel)}</span>{' '}
              强制降级为{' '}
              <span className="font-mono font-semibold underline">{getAutonomyLevelLabel(incident.degradedLevel)}</span>
            </p>
          </div>
        </div>

        {incident.timestamp && (
          <div className="hidden sm:flex items-center gap-1 text-[11px] text-muted-foreground whitespace-nowrap">
            <Clock className="h-3 w-3" />
            <span>{incident.timestamp}</span>
          </div>
        )}
      </div>

      {/* 核心原因展示 */}
      <div className="mt-3.5 p-3 rounded-lg bg-rose-500/10 dark:bg-rose-900/20 border border-rose-500/15 text-xs text-rose-950 dark:text-rose-200 flex flex-col gap-1">
        <div className="flex items-center gap-1.5 font-medium text-rose-800 dark:text-rose-300">
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span>熔断原因: {incident.reason}</span>
        </div>
        <div className="flex items-center gap-2 font-mono text-[11px] text-muted-foreground mt-0.5">
          <Terminal className="h-3 w-3 shrink-0" />
          <span>触发工具: {incident.triggeredTool}</span>
          {incident.consecutiveFailures && incident.consecutiveFailures > 1 && (
            <span className="text-rose-600 dark:text-rose-400 font-semibold">
              (连续失败 {incident.consecutiveFailures} 次)
            </span>
          )}
        </div>
      </div>

      {/* 折叠区：详细错误堆栈 */}
      {showDetails && (
        <div
          className="mt-3 p-3 rounded-lg bg-background/80 dark:bg-muted/40 border border-border text-xs font-mono overflow-x-auto max-h-48 scrollbar-thin text-foreground"
          data-testid="breaker-error-details"
        >
          <div className="text-[11px] font-semibold text-muted-foreground mb-1">诊断堆栈与上下文信息:</div>
          <pre className="whitespace-pre-wrap break-all text-[11px] leading-relaxed">
            {incident.errorDetails || '未提供详细错误堆栈'}
          </pre>
        </div>
      )}

      {/* 底部动作工具栏 */}
      <div className="mt-4 pt-3 border-t border-rose-500/15 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-2.5">
        <button
          type="button"
          onClick={() => setShowDetails(!showDetails)}
          className="text-xs text-muted-foreground hover:text-foreground flex items-center justify-center sm:justify-start gap-1 py-1 transition-colors"
          data-testid="toggle-details-btn"
        >
          {showDetails ? (
            <>
              <ChevronUp className="h-3.5 w-3.5" />
              <span>收起技术诊断</span>
            </>
          ) : (
            <>
              <ChevronDown className="h-3.5 w-3.5" />
              <span>展开技术诊断</span>
            </>
          )}
        </button>

        <div className="flex items-center gap-2 flex-wrap justify-end">
          {onViewAudit && (
            <button
              type="button"
              onClick={onViewAudit}
              className="text-xs px-2.5 py-1.5 rounded-lg border border-border hover:bg-muted text-foreground transition-colors"
            >
              审计记录
            </button>
          )}

          {onDegradeToManual && (
            <button
              type="button"
              disabled={isProcessing}
              onClick={handleDegrade}
              className="text-xs px-3 py-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 hover:bg-rose-500/20 text-rose-800 dark:text-rose-200 font-medium transition-colors flex items-center gap-1 disabled:opacity-50"
              data-testid="degrade-btn"
            >
              <ShieldAlert className="h-3.5 w-3.5" />
              <span>降级为严格审批</span>
            </button>
          )}

          {onAcknowledgeAndRecover && (
            <button
              type="button"
              disabled={isProcessing}
              onClick={handleRecover}
              className="text-xs px-3.5 py-1.5 rounded-lg bg-rose-600 hover:bg-rose-700 text-white font-medium shadow-sm transition-colors flex items-center gap-1.5 disabled:opacity-50"
              data-testid="recover-btn"
            >
              {isProcessing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
              <span>确认并试探恢复</span>
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
