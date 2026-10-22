'use client';

/**
 * [INPUT]
 * - mobileCockpitTypes: MobileHitlApprovalCardProps, HitlRiskLevel, HitlDecisionType
 * - lucide-react icons
 * - next-intl: useTranslations
 *
 * [OUTPUT]
 * - MobileHitlApprovalCard: One-Tap Decision & Approval Card for mobile viewports
 *
 * [POS]
 * Mobile Remote Companion touch-optimized HITL approval surface for one-handed thumb interaction.
 */

import React, { useState, useCallback, ChangeEvent } from 'react';
import { useTranslations } from 'next-intl';
import {
  ShieldAlert,
  ShieldCheck,
  Check,
  Ban,
  Compass,
  AlertTriangle,
  SendHorizontal,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import {
  MobileHitlApprovalCardProps,
  HitlRiskLevel,
} from './mobileCockpitTypes';

export const MobileHitlApprovalCard: React.FC<MobileHitlApprovalCardProps> = ({
  payload,
  onDecision,
  isProcessing = false,
  className = '',
}) => {
  let t = (key: string): string => key;
  try {
    const translation = useTranslations('mobileCockpit.hitlApproval');
    t = (key: string): string => translation(key);
  } catch {
    // Fallback for tests or SSR
  }

  const [mode, setMode] = useState<'idle' | 'rejecting' | 'steering'>('idle');
  const [rejectReason, setRejectReason] = useState<string>('');
  const [steerText, setSteerText] = useState<string>('');
  const [paramsExpanded, setParamsExpanded] = useState<boolean>(false);

  const getRiskBadge = (level: HitlRiskLevel) => {
    switch (level) {
      case 'low': {
        return {
          label: t('riskLow'),
          color: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
          icon: ShieldCheck,
        };
      }
      case 'medium': {
        return {
          label: t('riskMedium'),
          color: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
          icon: AlertTriangle,
        };
      }
      case 'high': {
        return {
          label: t('riskHigh'),
          color: 'bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/20',
          icon: ShieldAlert,
        };
      }
      case 'critical': {
        return {
          label: t('riskCritical'),
          color: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30',
          icon: ShieldAlert,
        };
      }
      default: {
        return {
          label: t('riskMedium'),
          color: 'bg-amber-500/10 text-amber-600 border-amber-500/20',
          icon: AlertTriangle,
        };
      }
    }
  };

  const riskBadge = getRiskBadge(payload.riskLevel);
  const RiskIcon = riskBadge.icon;

  const handleApprove = useCallback(async () => {
    if (isProcessing) {
      return;
    }
    await onDecision({
      requestId: payload.requestId,
      decision: 'approve',
    });
  }, [isProcessing, onDecision, payload.requestId]);

  const handleConfirmReject = useCallback(async () => {
    if (isProcessing) {
      return;
    }
    await onDecision({
      requestId: payload.requestId,
      decision: 'reject',
      reason: rejectReason.trim() || undefined,
    });
    setMode('idle');
  }, [isProcessing, onDecision, payload.requestId, rejectReason]);

  const handleConfirmSteer = useCallback(async () => {
    if (isProcessing || !steerText.trim()) {
      return;
    }
    await onDecision({
      requestId: payload.requestId,
      decision: 'steer',
      steerInstruction: steerText.trim(),
    });
    setMode('idle');
  }, [isProcessing, onDecision, payload.requestId, steerText]);

  return (
    <div
      data-testid="mobile-hitl-card"
      className={`rounded-3xl border border-border/80 bg-card/95 p-4 shadow-xl backdrop-blur-md transition-all ${className}`}
    >
      <div className="flex items-start justify-between gap-2 pb-2.5 border-b border-border/50">
        <div className="space-y-0.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {t('title')}
          </span>
          <h4 className="text-sm font-bold text-foreground line-clamp-1">
            {payload.actionTitle}
          </h4>
        </div>
        <span
          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${riskBadge.color}`}
        >
          <RiskIcon className="h-3 w-3" />
          <span>{riskBadge.label}</span>
        </span>
      </div>

      <div className="my-3 space-y-2 text-xs">
        <div className="rounded-xl bg-muted/50 p-2.5">
          <span className="text-[11px] font-medium text-muted-foreground block mb-0.5">
            {t('commandOrAction')}
          </span>
          <code className="text-xs font-mono text-foreground break-all">
            {payload.commandOrTool}
          </code>
        </div>

        <div className="flex items-center justify-between text-muted-foreground px-1">
          <span className="text-[11px]">{t('affectedScope')}</span>
          <span className="text-xs font-medium text-foreground">
            {payload.scopeDescription}
          </span>
        </div>

        {payload.rawParams && Object.keys(payload.rawParams).length > 0 ? (
          <div className="pt-1">
            <button
              type="button"
              onClick={() => {
                setParamsExpanded(!paramsExpanded);
              }}
              className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground"
            >
              <span>参数详情 ({Object.keys(payload.rawParams).length})</span>
              {paramsExpanded ? (
                <ChevronUp className="h-3 w-3" />
              ) : (
                <ChevronDown className="h-3 w-3" />
              )}
            </button>
            {paramsExpanded ? (
              <div className="mt-1.5 max-h-32 overflow-y-auto rounded-lg bg-muted/40 p-2 font-mono text-[11px] space-y-0.5">
                {Object.entries(payload.rawParams).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-2">
                    <span className="text-muted-foreground">{k}:</span>
                    <span className="text-foreground truncate">{String(v)}</span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      {mode === 'rejecting' ? (
        <div className="mt-3 space-y-2 rounded-2xl border border-destructive/20 bg-destructive/5 p-3 animate-in fade-in duration-150">
          <input
            type="text"
            value={rejectReason}
            onChange={(e: ChangeEvent<HTMLInputElement>) => {
              setRejectReason(e.target.value);
            }}
            placeholder={t('rejectReasonPlaceholder')}
            className="w-full rounded-xl border border-border/80 bg-background px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-destructive focus:outline-none focus:ring-1 focus:ring-destructive/30"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                setMode('idle');
              }}
              className="flex-1 h-10 rounded-xl border border-border bg-card text-xs font-medium text-foreground"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleConfirmReject}
              disabled={isProcessing}
              className="flex-1 h-10 rounded-xl bg-destructive text-xs font-semibold text-destructive-foreground shadow hover:bg-destructive/90"
            >
              {t('rejectConfirm')}
            </button>
          </div>
        </div>
      ) : null}

      {mode === 'steering' ? (
        <div className="mt-3 space-y-2 rounded-2xl border border-primary/20 bg-primary/5 p-3 animate-in fade-in duration-150">
          <input
            type="text"
            value={steerText}
            onChange={(e: ChangeEvent<HTMLInputElement>) => {
              setSteerText(e.target.value);
            }}
            placeholder={t('steerPlaceholder')}
            className="w-full rounded-xl border border-border/80 bg-background px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground/60 focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary/30"
          />
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => {
                setMode('idle');
              }}
              className="flex-1 h-10 rounded-xl border border-border bg-card text-xs font-medium text-foreground"
            >
              取消
            </button>
            <button
              type="button"
              onClick={handleConfirmSteer}
              disabled={isProcessing || !steerText.trim()}
              className="flex-1 h-10 rounded-xl bg-primary text-xs font-semibold text-primary-foreground shadow hover:bg-primary/90 disabled:opacity-40"
            >
              <SendHorizontal className="inline-block mr-1 h-3.5 w-3.5" />
              {t('steerSubmit')}
            </button>
          </div>
        </div>
      ) : null}

      {mode === 'idle' ? (
        <div className="mt-3.5 grid grid-cols-3 gap-2">
          <button
            type="button"
            data-testid="hitl-reject-btn"
            onClick={() => {
              setMode('rejecting');
            }}
            disabled={isProcessing}
            className="flex h-12 flex-col items-center justify-center rounded-2xl border border-border/80 bg-card text-foreground hover:bg-destructive/10 hover:border-destructive/30 active:scale-95 transition-all disabled:opacity-50"
          >
            <Ban className="h-4 w-4 text-destructive mb-0.5" />
            <span className="text-[11px] font-semibold">{t('rejectNo')}</span>
          </button>

          <button
            type="button"
            data-testid="hitl-steer-btn"
            onClick={() => {
              setMode('steering');
            }}
            disabled={isProcessing}
            className="flex h-12 flex-col items-center justify-center rounded-2xl border border-border/80 bg-card text-foreground hover:bg-primary/10 hover:border-primary/30 active:scale-95 transition-all disabled:opacity-50"
          >
            <Compass className="h-4 w-4 text-primary mb-0.5" />
            <span className="text-[11px] font-semibold">{t('steerGuide')}</span>
          </button>

          <button
            type="button"
            data-testid="hitl-approve-btn"
            onClick={handleApprove}
            disabled={isProcessing}
            className="flex h-12 flex-col items-center justify-center rounded-2xl bg-emerald-600 text-white shadow-md hover:bg-emerald-700 active:scale-95 transition-all disabled:opacity-50"
          >
            <Check className="h-4 w-4 mb-0.5" />
            <span className="text-[11px] font-bold">{t('approveYes')}</span>
          </button>
        </div>
      ) : null}
    </div>
  );
};
