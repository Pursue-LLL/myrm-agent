/**
 * @orphan-ok Pre-flight execution envelope consent card for desktop control fast-path
 *
 * [INPUT]
 * - react::FC
 * - lucide-react::ShieldCheck, Layers, Lock, ShieldAlert, Zap
 * - zustand::useDesktopControlApprovalStore
 *
 * [OUTPUT]
 * - IntentEnvelopeCard: Pre-flight execution envelope consent card.
 *
 * [POS]
 * Renders the pre-flight scope envelope card in chat flow, allowing users to
 * grant scoped, non-interruptive execution for specific applications with budget limits.
 */

import React from 'react';
import { ShieldCheck, Layers, Lock, Zap } from 'lucide-react';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';

export interface IntentEnvelopeCardProps {
  taskId: string;
  allowedApps: string[];
  maxActions: number;
  onApproveFastPath?: () => void;
  onFallbackStepByStep?: () => void;
}

export const IntentEnvelopeCard: React.FC<IntentEnvelopeCardProps> = ({
  taskId,
  allowedApps,
  maxActions,
  onApproveFastPath,
  onFallbackStepByStep,
}) => {
  const { setEnvelope, activeEnvelope } = useDesktopControlApprovalStore();

  const handleApprove = () => {
    setEnvelope({
      taskId,
      allowedApps,
      maxActions,
      usedActions: 0,
      remainingBudget: maxActions,
      allowSystemDialogs: true,
      status: 'active',
    });
    onApproveFastPath?.();
  };

  const handleStepByStep = () => {
    setEnvelope(null);
    onFallbackStepByStep?.();
  };

  const isAlreadyActive = activeEnvelope?.taskId === taskId && activeEnvelope.status === 'active';

  return (
    <div
      data-testid="intent-envelope-card"
      className="my-3 w-full max-w-lg rounded-xl border border-border bg-card p-4 text-card-foreground shadow-sm transition-all"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h4 className="text-sm font-semibold tracking-tight text-foreground">
              受限意图包络线全局授权
            </h4>
            <p className="text-xs text-muted-foreground">
              声明边界内全速免打扰推进 · 越界动态升格
            </p>
          </div>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
          <Zap className="h-3 w-3" />
          免逐击打扰
        </span>
      </div>

      <div className="mt-3.5 space-y-2.5 rounded-lg border border-border/60 bg-muted/30 p-3 text-xs">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="flex items-center gap-1 font-medium text-muted-foreground">
            <Layers className="h-3.5 w-3.5" />
            授权目标应用:
          </span>
          {allowedApps.map((app) => (
            <span
              key={app}
              className="rounded-md border border-border/80 bg-background px-2 py-0.5 font-mono text-[11px] text-foreground shadow-2xs"
            >
              {app}
            </span>
          ))}
        </div>

        <div className="flex items-center justify-between text-muted-foreground">
          <span>操作步数预算配额:</span>
          <span className="font-semibold text-foreground">{maxActions} 步</span>
        </div>

        <div className="flex items-center gap-1 text-[11px] text-muted-foreground/80">
          <Lock className="h-3 w-3 text-muted-foreground" />
          <span>终端与系统敏感设置严格受保护，任何越界将自动安全挂起并升格二次确认。</span>
        </div>
      </div>

      <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button
          type="button"
          onClick={handleStepByStep}
          className="inline-flex items-center justify-center rounded-lg border border-input bg-background px-3 py-1.5 text-xs font-medium text-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
        >
          逐步逐击确认
        </button>
        <button
          type="button"
          disabled={isAlreadyActive}
          onClick={handleApprove}
          className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-primary px-3.5 py-1.5 text-xs font-medium text-primary-foreground shadow-sm hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          <Zap className="h-3.5 w-3.5" />
          {isAlreadyActive ? '已授权全速推进' : '批准全速推进'}
        </button>
      </div>
    </div>
  );
};

export default IntentEnvelopeCard;
