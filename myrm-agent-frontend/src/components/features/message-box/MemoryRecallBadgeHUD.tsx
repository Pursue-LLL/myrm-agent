/**
 * [INPUT]
 * - chatId: string
 * - rules?: RecalledRuleItem[] (optional overrides, defaults to store rules)
 *
 * [OUTPUT]
 * - MemoryRecallBadgeHUD: Top-of-message HUD badge displaying recalled rules with expandable toggle inspector
 *
 * [POS]
 * Message box HUD component for Recalled Memory & Rules (Item 42 P0).
 * Strictly under 240 lines. Zero `any`.
 */

'use client';

import React, { useState } from 'react';
import { Lightbulb, ChevronDown, ChevronUp, ShieldCheck, CheckCircle2, XCircle } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { useSwarmExecutionStore } from '@/components/features/swarm/useSwarmExecutionStore';
import type { RecalledRuleItem } from '@/components/features/swarm/swarmTypes';

interface MemoryRecallBadgeHUDProps {
  chatId: string;
  rules?: RecalledRuleItem[];
  className?: string;
}

export const MemoryRecallBadgeHUD: React.FC<MemoryRecallBadgeHUDProps> = ({
  chatId,
  rules: propRules,
  className = '',
}) => {
  const t = useTranslations('swarmExecution');
  const storeRules = useSwarmExecutionStore((s) => s.recalledRules);
  const toggleRuleActive = useSwarmExecutionStore((s) => s.toggleRuleActive);

  const [isExpanded, setIsExpanded] = useState(false);

  const effectiveRules = propRules || storeRules;
  if (!effectiveRules || effectiveRules.length === 0) {
    return null;
  }

  const activeCount = effectiveRules.filter((r) => r.isActive).length;

  const handleToggle = (ruleId: string, currentActive: boolean) => {
    void toggleRuleActive(chatId, ruleId, !currentActive);
  };

  return (
    <div className={`my-2 flex flex-col rounded-xl border border-amber-200/60 bg-amber-50/40 text-xs dark:border-amber-900/40 dark:bg-amber-950/20 ${className}`}>
      {/* Top Banner Trigger */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        aria-expanded={isExpanded}
        aria-label={t('recallBadgeAriaLabel', { count: effectiveRules.length })}
        className="flex w-full items-center justify-between px-3 py-2 text-left transition-colors hover:bg-amber-100/50 dark:hover:bg-amber-900/30"
      >
        <div className="flex items-center gap-2 truncate">
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-amber-500/20 text-amber-600 dark:text-amber-400">
            <Lightbulb className="h-3.5 w-3.5" />
          </div>
          <span className="font-semibold text-amber-900 dark:text-amber-200">
            {t('recalledRulesTitle', { count: effectiveRules.length, active: activeCount })}
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0 text-amber-700 dark:text-amber-400">
          <span className="text-[11px] font-medium">{isExpanded ? t('collapse') : t('viewDetails')}</span>
          {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </div>
      </button>

      {/* Expanded Rule Inspector Panel */}
      {isExpanded && (
        <div className="border-t border-amber-200/50 p-3 flex flex-col gap-2 dark:border-amber-900/40">
          <div className="flex items-center justify-between text-[11px] text-amber-800/80 dark:text-amber-300/80">
            <span>{t('rulesInspectorHint')}</span>
            <span className="flex items-center gap-1 font-medium">
              <ShieldCheck className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
              {t('activeCountLabel', { count: activeCount })}
            </span>
          </div>

          <div className="flex flex-col gap-1.5 mt-1">
            {effectiveRules.map((rule) => (
              <div
                key={rule.ruleId}
                className={`flex items-start justify-between gap-3 rounded-lg border p-2 transition-all ${
                  rule.isActive
                    ? 'border-amber-200 bg-white/80 shadow-xs dark:border-amber-800/60 dark:bg-slate-900/70'
                    : 'border-slate-200 bg-slate-50/60 opacity-60 dark:border-slate-800 dark:bg-slate-950/40'
                }`}
              >
                <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className="rounded bg-amber-500/15 px-1.5 py-0.5 text-[10px] font-semibold text-amber-800 dark:text-amber-300">
                      {rule.category}
                    </span>
                    {rule.sourceTurnId && (
                      <span className="text-[10px] text-slate-400 dark:text-slate-500">
                        {rule.sourceTurnId}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-800 dark:text-slate-200 font-medium leading-relaxed mt-0.5">
                    {rule.summary}
                  </p>
                </div>

                {/* Toggle Active Switch */}
                <button
                  type="button"
                  onClick={() => handleToggle(rule.ruleId, rule.isActive)}
                  aria-label={rule.isActive ? t('disableRule') : t('enableRule')}
                  className={`flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium transition-colors ${
                    rule.isActive
                      ? 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100 dark:bg-emerald-950/40 dark:text-emerald-300'
                      : 'bg-slate-100 text-slate-500 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-400'
                  }`}
                >
                  {rule.isActive ? (
                    <>
                      <CheckCircle2 className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
                      <span>{t('enabled')}</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="h-3 w-3 text-slate-400" />
                      <span>{t('disabled')}</span>
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

export default MemoryRecallBadgeHUD;
