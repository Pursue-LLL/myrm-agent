// @orphan-ok Active prompt injection and canary exfiltration mitigation card for chat interaction stream
'use client';

import React, { useState } from 'react';
import {
  ShieldAlert,
  CheckCircle2,
  RefreshCw,
  ExternalLink,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';

export interface IndirectInjectionIncident {
  sessionId: string;
  sourceDomain?: string;
  detectedAt?: string;
  summary?: string;
  isRemediated?: boolean;
}

interface IndirectInjectionAlertCardProps {
  incident: IndirectInjectionIncident;
  onRemediate?: (sessionId: string) => Promise<void> | void;
  onViewAudit?: () => void;
  className?: string;
}

export const IndirectInjectionAlertCard: React.FC<IndirectInjectionAlertCardProps> = ({
  incident,
  onRemediate,
  onViewAudit,
  className = '',
}) => {
  const [isRemediating, setIsRemediating] = useState(false);
  const [isResolved, setIsResolved] = useState(incident.isRemediated ?? false);
  const [showDetails, setShowDetails] = useState(false);

  const handleRemediate = async () => {
    if (isRemediating || isResolved) return;
    setIsRemediating(true);
    try {
      if (onRemediate) {
        await onRemediate(incident.sessionId);
      }
      setIsResolved(true);
    } catch {
      // Keep state intact on failure
    } finally {
      setIsRemediating(false);
    }
  };

  return (
    <div
      className={`w-full max-w-2xl rounded-xl border border-destructive/20 bg-destructive/5 dark:bg-destructive/10 p-4 sm:p-5 shadow-sm transition-all duration-200 ${className}`}
      role="alert"
      aria-live="assertive"
    >
      <div className="flex items-start gap-3 sm:gap-4">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-destructive/10 dark:bg-destructive/20 text-destructive">
          {isResolved ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-500" />
          ) : (
            <ShieldAlert className="h-5 w-5" />
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="text-sm sm:text-base font-semibold text-foreground">
              {isResolved
                ? '外部威胁已隔离并恢复安全'
                : '安全主动防御：非受信网页威胁已阻断'}
            </h4>
            <span className="inline-flex items-center rounded-md bg-destructive/15 px-2 py-0.5 text-xs font-medium text-destructive dark:bg-destructive/25">
              {isResolved ? '已自愈' : '主动硬拦截'}
            </span>
          </div>

          <p className="mt-1 text-xs sm:text-sm text-muted-foreground leading-relaxed">
            {isResolved
              ? '受污染的外部上下文已被安全净化，会话环境已重置为正常状态，您可以放心地继续对话。'
              : '助手在阅读外部网页或文档时，检测并成功阻断了一次恶意外发凭据的诱导指令。您的真实密钥与工作区数据完好无损。'}
          </p>

          {incident.sourceDomain && (
            <div className="mt-2 text-xs text-muted-foreground/80 flex items-center gap-1.5 font-mono">
              <span>威胁来源:</span>
              <span className="truncate max-w-[260px] text-foreground font-medium">
                {incident.sourceDomain}
              </span>
            </div>
          )}

          {showDetails && (
            <div className="mt-3 rounded-lg bg-background/60 dark:bg-background/40 p-3 text-xs text-muted-foreground border border-border/40 space-y-1">
              <div className="flex justify-between">
                <span>防御模块:</span>
                <span className="font-mono text-foreground">Loopback Egress Honeytoken Trap</span>
              </div>
              <div className="flex justify-between">
                <span>网络处置:</span>
                <span className="font-mono text-foreground">TCP Socket RST (Fail-Closed)</span>
              </div>
              <div className="flex justify-between">
                <span>系统提示词缓存:</span>
                <span className="font-mono text-emerald-600 dark:text-emerald-400">100% 保持命中</span>
              </div>
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-center gap-2 sm:gap-3">
            {!isResolved ? (
              <button
                type="button"
                onClick={handleRemediate}
                disabled={isRemediating}
                className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-primary px-3.5 py-1.5 text-xs sm:text-sm font-medium text-primary-foreground shadow-sm transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
              >
                {isRemediating ? (
                  <>
                    <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                    <span>正在自愈隔离...</span>
                  </>
                ) : (
                  <span>净化受污染上下文并继续</span>
                )}
              </button>
            ) : (
              <span className="text-xs text-emerald-600 dark:text-emerald-400 font-medium flex items-center gap-1">
                <CheckCircle2 className="h-3.5 w-3.5" />
                会话已恢复安全
              </span>
            )}

            <button
              type="button"
              onClick={() => setShowDetails(!showDetails)}
              className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
            >
              <span>{showDetails ? '收起详情' : '技术详情'}</span>
              {showDetails ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </button>

            {onViewAudit && (
              <button
                type="button"
                onClick={onViewAudit}
                className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors ml-auto"
              >
                <span>安全日志</span>
                <ExternalLink className="h-3 w-3" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
