/**
 * [INPUT]
 * - chatId: string
 * - risks?: OwnerRiskItem[] (optional overrides, defaults to store risks)
 *
 * [OUTPUT]
 * - OwnerActionRiskCard: Deliverable tail accordion card for owner verification & risk checklist
 *
 * [POS]
 * Message box risk checklist component (Item 42 P0).
 * Strictly under 240 lines. Zero `any`.
 */

'use client';

import React, { useState } from 'react';
import {
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  CheckSquare,
  Square,
  ShieldAlert,
  CheckCircle2,
  HelpCircle,
} from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useSwarmExecutionStore } from '@/components/features/swarm/useSwarmExecutionStore';
import type { OwnerRiskItem, RiskSeverityLevel } from '@/components/features/swarm/swarmTypes';

interface OwnerActionRiskCardProps {
  chatId: string;
  risks?: OwnerRiskItem[];
  className?: string;
}

const severityBadgeStyles: Record<RiskSeverityLevel, string> = {
  critical: 'bg-rose-500/15 text-rose-700 border-rose-500/30 dark:text-rose-400',
  high: 'bg-amber-500/15 text-amber-700 border-amber-500/30 dark:text-amber-400',
  medium: 'bg-blue-500/15 text-blue-700 border-blue-500/30 dark:text-blue-400',
  low: 'bg-slate-500/15 text-slate-700 border-slate-500/30 dark:text-slate-400',
};

export const OwnerActionRiskCard: React.FC<OwnerActionRiskCardProps> = ({
  chatId,
  risks: propRisks,
  className = '',
}) => {
  const t = useTranslations('swarmExecution');
  const storeRisks = useSwarmExecutionStore((s) => s.ownerRisks);
  const toggleRiskConfirm = useSwarmExecutionStore((s) => s.toggleRiskConfirm);

  const [isExpanded, setIsExpanded] = useState(true);

  const effectiveRisks = propRisks || storeRisks;
  if (!effectiveRisks || effectiveRisks.length === 0) {
    return null;
  }

  const confirmedCount = effectiveRisks.filter((r) => r.isConfirmed).length;
  const isAllConfirmed = confirmedCount === effectiveRisks.length;

  const handleToggleConfirm = (riskId: string, currentConfirmed: boolean) => {
    void toggleRiskConfirm(chatId, riskId, !currentConfirmed, 'store_owner');
  };

  return (
    <div
      className={`my-3 flex flex-col rounded-xl border transition-all ${
        isAllConfirmed
          ? 'border-emerald-200 bg-emerald-50/40 dark:border-emerald-900/40 dark:bg-emerald-950/20'
          : 'border-amber-300 bg-amber-50/50 dark:border-amber-900/60 dark:bg-amber-950/30'
      } ${className}`}
    >
      {/* Header Bar */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
        aria-label={t('riskChecklistAriaLabel')}
        className="flex w-full items-center justify-between p-3.5 text-left transition-colors hover:bg-black/5 dark:hover:bg-white/5"
      >
        <div className="flex items-center gap-2.5 truncate">
          <div
            className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-lg ${
              isAllConfirmed
                ? 'bg-emerald-500/20 text-emerald-600 dark:text-emerald-400'
                : 'bg-amber-500/20 text-amber-600 dark:text-amber-400'
            }`}
          >
            {isAllConfirmed ? <CheckCircle2 className="h-4 w-4" /> : <AlertTriangle className="h-4 w-4" />}
          </div>
          <div className="flex flex-col truncate">
            <span className="text-xs font-semibold text-slate-900 dark:text-slate-100">
              {t('ownerRiskCardTitle')}
            </span>
            <span className="text-[11px] text-slate-500 dark:text-slate-400">
              {t('riskProgressCue', { confirmed: confirmedCount, total: effectiveRisks.length })}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400 shrink-0">
          <span className="text-[11px] font-medium">{isExpanded ? t('collapse') : t('expand')}</span>
          {isExpanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </div>
      </button>

      {/* Expanded Checklist Body */}
      {isExpanded && (
        <div className="border-t border-black/5 p-3.5 flex flex-col gap-2.5 dark:border-white/5">
          <div className="flex items-center gap-1.5 text-[11px] text-slate-600 dark:text-slate-300">
            <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
            <span>{t('ownerRiskDescriptionNotice')}</span>
          </div>

          <div className="flex flex-col gap-2 mt-1">
            {effectiveRisks.map((item) => (
              <div
                key={item.riskId}
                className={`flex items-start justify-between gap-3 rounded-xl border p-3 transition-all ${
                  item.isConfirmed
                    ? 'border-emerald-200 bg-white/90 shadow-2xs dark:border-emerald-800/40 dark:bg-slate-900/80'
                    : 'border-slate-200 bg-white/95 shadow-xs dark:border-slate-800 dark:bg-slate-900/90'
                }`}
              >
                <div className="flex flex-col gap-1 flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span
                      className={`rounded border px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                        severityBadgeStyles[item.severity]
                      }`}
                    >
                      {item.severity}
                    </span>
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                      {item.externalConstraintType}
                    </span>
                    <h4 className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate">
                      {item.title}
                    </h4>
                  </div>
                  <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                    {item.description}
                  </p>
                  {item.remediationHint && (
                    <div className="flex items-center gap-1 text-[11px] text-amber-700/90 dark:text-amber-400/90 mt-0.5">
                      <HelpCircle className="h-3 w-3 shrink-0" />
                      <span>
                        {t('remediationHintLabel')}: {item.remediationHint}
                      </span>
                    </div>
                  )}
                </div>

                {/* Checkbox Button */}
                <button
                  type="button"
                  onClick={() => handleToggleConfirm(item.riskId, item.isConfirmed)}
                  aria-label={item.isConfirmed ? t('markUnconfirmed') : t('markConfirmed')}
                  className={`flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-all ${
                    item.isConfirmed
                      ? 'border-emerald-500 bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:border-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-300'
                      : 'border-slate-300 bg-slate-50 text-slate-700 hover:border-slate-400 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'
                  }`}
                >
                  {item.isConfirmed ? (
                    <>
                      <CheckSquare className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400" />
                      <span>{t('confirmed')}</span>
                    </>
                  ) : (
                    <>
                      <Square className="h-3.5 w-3.5 text-slate-400" />
                      <span>{t('verifyNow')}</span>
                    </>
                  )}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default OwnerActionRiskCard;
