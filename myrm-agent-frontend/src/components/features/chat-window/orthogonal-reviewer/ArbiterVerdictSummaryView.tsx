import React from 'react';
import type { ArbiterVerdict } from './types';

interface ArbiterVerdictSummaryViewProps {
  verdict: ArbiterVerdict;
  onDispatchAutoFix?: (prompt: string) => void;
}

export const ArbiterVerdictSummaryView: React.FC<ArbiterVerdictSummaryViewProps> = ({
  verdict,
  onDispatchAutoFix,
}) => {
  const isAdmitted = verdict.decision === 'admitted';
  const isBlocked = verdict.decision === 'blocked';

  const decisionBadgeStyle = isAdmitted
    ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300 border-emerald-300 dark:border-emerald-800'
    : isBlocked
      ? 'bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300 border-rose-300 dark:border-rose-800 animate-pulse'
      : 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 border-amber-300 dark:border-amber-800';

  const decisionTitle = isAdmitted
    ? '双审通过 · 准入合流 (ADMITTED)'
    : isBlocked
      ? '双审拦截 · 阻断合流 (BLOCKED)'
      : '需要修订 · 人工复核 (NEEDS REVISION)';

  return (
    <section
      data-testid="arbiter-verdict-summary"
      aria-label="正交综合仲裁结论"
      className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-gray-50/50 p-3.5 dark:border-gray-800 dark:bg-gray-900/50"
    >
      {/* Decision Banner */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span
            data-testid="arbiter-decision-badge"
            className={`rounded-md border px-2.5 py-1 text-xs font-bold uppercase ${decisionBadgeStyle}`}
          >
            {verdict.decision}
          </span>
          <span className="text-xs font-bold text-gray-900 dark:text-gray-100">{decisionTitle}</span>
        </div>

        {/* Severity Metrics Dashboard */}
        <div className="flex items-center gap-2 text-xs">
          <span className="rounded bg-rose-50 px-2 py-0.5 font-medium text-rose-700 dark:bg-rose-950/50 dark:text-rose-300">
            Critical: <strong className="font-bold">{verdict.critical_count}</strong>
          </span>
          <span className="rounded bg-amber-50 px-2 py-0.5 font-medium text-amber-700 dark:bg-amber-950/50 dark:text-amber-300">
            Major: <strong className="font-bold">{verdict.major_count}</strong>
          </span>
          <span className="rounded bg-blue-50 px-2 py-0.5 font-medium text-blue-700 dark:bg-blue-950/50 dark:text-blue-300">
            Minor: <strong className="font-bold">{verdict.minor_count}</strong>
          </span>
        </div>
      </div>

      {/* Blocker Reasons Alert */}
      {verdict.blocker_reasons.length > 0 && (
        <div
          data-testid="blocker-reasons-panel"
          className="rounded border border-rose-200 bg-rose-50/60 p-2.5 text-xs text-rose-800 dark:border-rose-900 dark:bg-rose-950/30 dark:text-rose-300"
        >
          <div className="mb-1 flex items-center gap-1 font-bold">
            <span aria-hidden="true">⚠️</span>
            <span>触发门禁阻断原因：</span>
          </div>
          <ul className="list-inside list-disc space-y-0.5">
            {verdict.blocker_reasons.map((reason, index) => (
              <li key={`reason-${index}`}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Auto Fix Prompts Section */}
      {verdict.auto_fix_prompts.length > 0 && (
        <div
          data-testid="autofix-prompts-section"
          className="flex flex-col gap-2 rounded border border-indigo-200 bg-indigo-50/40 p-2.5 dark:border-indigo-900/60 dark:bg-indigo-950/30"
        >
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-indigo-900 dark:text-indigo-200">
              🛠️ 仲裁器自动推导自愈修复指令 ({verdict.auto_fix_prompts.length})
            </span>
            <span className="text-[10px] text-gray-500">点击指令立即派发修复子任务</span>
          </div>
          <div className="flex flex-col gap-1.5">
            {verdict.auto_fix_prompts.map((prompt, index) => (
              <div
                key={`autofix-${index}`}
                className="flex items-center justify-between gap-2 rounded bg-white p-2 text-xs shadow-2xs dark:bg-gray-900"
              >
                <code className="line-clamp-2 flex-1 font-mono text-[11px] text-gray-700 dark:text-gray-300">
                  {prompt}
                </code>
                <button
                  type="button"
                  onClick={() => onDispatchAutoFix?.(prompt)}
                  aria-label={`执行自动修复指令 ${index + 1}`}
                  className="rounded bg-indigo-600 px-2.5 py-1 text-[11px] font-semibold text-white transition-colors hover:bg-indigo-700 active:scale-95"
                >
                  派发自愈
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};
