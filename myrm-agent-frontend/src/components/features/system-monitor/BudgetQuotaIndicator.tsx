'use client';

/**
 * [INPUT]
 * - lucide-react::AlertTriangle, ShieldAlert, CheckCircle2 (POS: 视觉指示图标)
 *
 * [OUTPUT]
 * - BudgetQuotaIndicator: 任务多维资源预算配额与防超支熔断指示器
 *
 * [POS]
 * src/components/features/system-monitor/BudgetQuotaIndicator.tsx — 预算配额水位与熔断预警进度条。
 */

import React from 'react';
import { AlertTriangle, ShieldAlert, CheckCircle2 } from 'lucide-react';

interface QuotaBarProps {
  label: string;
  current: number;
  max: number;
  unit: string;
  formatFn?: (val: number) => string;
}

const QuotaBar: React.FC<QuotaBarProps> = ({
  label,
  current,
  max,
  unit,
  formatFn = (v) => v.toString(),
}) => {
  const percentage = Math.min(100, Math.max(0, (current / max) * 100));
  const isOver = current > max;
  const isWarning = percentage >= 80 && !isOver;

  let barColor = 'bg-primary';
  let textColor = 'text-muted-foreground';

  if (isOver) {
    barColor = 'bg-destructive';
    textColor = 'text-destructive font-semibold';
  } else if (isWarning) {
    barColor = 'bg-amber-500';
    textColor = 'text-amber-600 dark:text-amber-400 font-medium';
  }

  return (
    <div className="space-y-1 text-xs">
      <div className="flex items-center justify-between">
        <span className="text-muted-foreground">{label}</span>
        <span className={`font-mono text-[11px] ${textColor}`}>
          {formatFn(current)} / {formatFn(max)} {unit}
          {isOver && ' (超限熔断)'}
        </span>
      </div>
      <div className="h-1.5 w-full rounded-full bg-muted/60 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
};

export interface BudgetQuotaIndicatorProps {
  currentSeconds?: number;
  maxSeconds?: number | null;
  currentTokens?: number;
  maxTokens?: number | null;
  currentCredits?: number;
  maxCredits?: number | null;
  className?: string;
}

export const BudgetQuotaIndicator: React.FC<BudgetQuotaIndicatorProps> = ({
  currentSeconds,
  maxSeconds,
  currentTokens,
  maxTokens,
  currentCredits,
  maxCredits,
  className = '',
}) => {
  const hasQuota = Boolean(maxSeconds || maxTokens || maxCredits);

  if (!hasQuota) {
    return null;
  }

  return (
    <div className={`p-3 rounded-lg border border-border bg-muted/20 space-y-2.5 ${className}`}>
      <div className="flex items-center justify-between text-xs font-medium text-foreground">
        <span className="flex items-center gap-1.5">
          <ShieldAlert className="w-3.5 h-3.5 text-primary" />
          任务多维预算配额水位 (Budget Guard)
        </span>
      </div>

      <div className="space-y-2">
        {maxSeconds != null && currentSeconds != null && (
          <QuotaBar
            label="物理沙箱时长"
            current={currentSeconds}
            max={maxSeconds}
            unit="秒"
            formatFn={(v) => v.toFixed(0)}
          />
        )}

        {maxTokens != null && currentTokens != null && (
          <QuotaBar
            label="认知 Token 消耗"
            current={currentTokens}
            max={maxTokens}
            unit="Tokens"
            formatFn={(v) => v.toLocaleString()}
          />
        )}

        {maxCredits != null && currentCredits != null && (
          <QuotaBar
            label="总算力积分消耗"
            current={currentCredits}
            max={maxCredits}
            unit="Credits"
            formatFn={(v) => v.toFixed(1)}
          />
        )}
      </div>
    </div>
  );
};
