'use client';

import { useState } from 'react';
import type { useTranslations } from 'next-intl';
import { CheckCircleIcon, XCircleIcon } from './goal-icons';
import type { AcceptanceResultItem, AcceptanceHistoryEntry } from './goalStatusTypes';

interface AcceptanceCriteriaPanelProps {
  criteria: { type: string; command?: string; criteria?: string }[];
  results?: AcceptanceResultItem[];
  history?: AcceptanceHistoryEntry[];
  t: ReturnType<typeof useTranslations>;
}

export function AcceptanceCriteriaPanel({ criteria, results, history, t }: AcceptanceCriteriaPanelProps) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  const [showHistory, setShowHistory] = useState(false);

  const passedCount = results?.filter((r) => r.passed).length ?? 0;
  const totalCount = results?.length ?? criteria.length;
  const hasResults = results && results.length > 0;

  return (
    <div className="mt-3 border-t border-border/50 pt-3">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-medium text-primary/80">{t('acceptanceCriteria')}</span>
        {hasResults && (
          <span
            className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
              passedCount === totalCount
                ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                : 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
            }`}
          >
            {passedCount}/{totalCount}
          </span>
        )}
      </div>

      <ul className="space-y-1">
        {criteria.map((ac, idx) => {
          const result = results?.[idx];
          const isExpanded = expandedIdx === idx;

          return (
            <li key={idx} className="text-xs">
              <div
                className={`flex items-start gap-2 p-1.5 rounded-lg border cursor-pointer transition-colors ${
                  result
                    ? result.passed
                      ? 'bg-green-50/50 border-green-200/50 dark:bg-green-900/10 dark:border-green-800/30'
                      : 'bg-red-50/50 border-red-200/50 dark:bg-red-900/10 dark:border-red-800/30'
                    : 'bg-primary/5 border-primary/10'
                }`}
                onClick={() => setExpandedIdx(isExpanded ? null : idx)}
              >
                <span className="flex-shrink-0 mt-0.5">
                  {result ? (
                    result.passed ? (
                      <CheckCircleIcon className="h-3.5 w-3.5 text-green-600 dark:text-green-400" />
                    ) : (
                      <XCircleIcon className="h-3.5 w-3.5 text-red-600 dark:text-red-400" />
                    )
                  ) : (
                    <span className="text-primary/60 font-mono text-[10px]">
                      {ac.type === 'shell' ? '$' : '>'}
                    </span>
                  )}
                </span>
                <span className="text-foreground/80 break-words leading-relaxed flex-1">
                  {ac.type === 'shell' ? ac.command : ac.criteria}
                </span>
                {result && (
                  <span className="flex-shrink-0 text-[10px] text-muted-foreground tabular-nums">
                    {result.duration_ms}ms
                  </span>
                )}
              </div>
              {isExpanded && result && !result.passed && result.error_logs && (
                <pre className="mt-1 ml-6 p-2 text-[10px] bg-muted/60 rounded border border-border/50 overflow-x-auto max-h-32 whitespace-pre-wrap text-muted-foreground">
                  {result.error_logs}
                </pre>
              )}
              {isExpanded && result && result.reason && (
                <p className="mt-1 ml-6 text-[10px] text-muted-foreground italic">
                  {result.reason}
                </p>
              )}
            </li>
          );
        })}
      </ul>

      {history && history.length > 1 && (
        <div className="mt-2">
          <button
            className="text-[10px] text-muted-foreground hover:text-foreground transition-colors"
            onClick={() => setShowHistory(!showHistory)}
          >
            {showHistory ? t('hideHistory') : t('showHistory', { count: history.length })}
          </button>
          {showHistory && (
            <div className="mt-1.5 space-y-1.5 max-h-40 overflow-y-auto">
              {history.slice(0, -1).reverse().map((entry, hIdx) => {
                const hPassed = entry.results.filter((r) => r.passed).length;
                const hTotal = entry.results.length;
                return (
                  <div
                    key={hIdx}
                    className="flex items-center gap-2 text-[10px] text-muted-foreground/70 pl-2 border-l-2 border-border/30"
                  >
                    <span className="tabular-nums">
                      {new Date(entry.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                    <span className={hPassed === hTotal ? 'text-green-600' : 'text-orange-600'}>
                      {hPassed}/{hTotal}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
