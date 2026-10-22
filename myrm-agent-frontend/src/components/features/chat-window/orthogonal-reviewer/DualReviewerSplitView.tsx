import React from 'react';
import type { ReviewFinding, ReviewerReport } from './types';

interface DualReviewerSplitViewProps {
  reviewerA: ReviewerReport;
  reviewerB: ReviewerReport;
}

const renderFindingItem = (finding: ReviewFinding) => {
  const isCritical = finding.severity === 'critical';
  const isMajor = finding.severity === 'major';

  const badgeColor = isCritical
    ? 'bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300 border-rose-300 dark:border-rose-800'
    : isMajor
      ? 'bg-amber-100 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300 border-amber-300 dark:border-amber-800'
      : 'bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300 border-blue-300 dark:border-blue-800';

  return (
    <li
      key={finding.finding_id}
      className="flex flex-col gap-1.5 rounded-lg border border-gray-100 bg-white p-2.5 text-xs shadow-2xs dark:border-gray-800 dark:bg-gray-900"
    >
      <div className="flex items-center justify-between gap-1.5">
        <span className={`rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase ${badgeColor}`}>
          {finding.severity}
        </span>
        <span className="font-mono text-[11px] text-gray-400">
          {finding.file_path}:{finding.line_range[0]}-{finding.line_range[1]}
        </span>
      </div>
      <div className="font-semibold text-gray-900 dark:text-gray-100">{finding.title}</div>
      <p className="text-gray-600 dark:text-gray-300">{finding.description}</p>
      <div className="mt-1 flex items-start gap-1 rounded bg-gray-50 px-2 py-1 text-[11px] text-gray-700 dark:bg-gray-800/60 dark:text-gray-300">
        <span className="font-semibold text-indigo-600 dark:text-indigo-400" aria-hidden="true">
          建议:
        </span>
        <span>{finding.suggested_action}</span>
      </div>
    </li>
  );
};

export const DualReviewerSplitView: React.FC<DualReviewerSplitViewProps> = ({ reviewerA, reviewerB }) => {
  return (
    <section aria-label="双重视角正交审查分栏" className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {/* Reviewer A: Intent Alignment */}
      <article
        data-testid="reviewer-a-panel"
        className="flex flex-col gap-2.5 rounded-lg border border-indigo-100 bg-indigo-50/30 p-3 dark:border-indigo-950 dark:bg-indigo-950/20"
      >
        <header className="flex items-center justify-between border-b border-indigo-100 pb-2 dark:border-indigo-900/50">
          <div className="flex items-center gap-1.5">
            <span className="text-base" aria-hidden="true">
              🎯
            </span>
            <div>
              <h3 className="text-xs font-bold text-gray-900 dark:text-gray-100">Reviewer A · 意图一致性审查</h3>
              <p className="text-[10px] text-indigo-600 dark:text-indigo-400">共享上下文 · 需求还原与防过度设计</p>
            </div>
          </div>
          <span
            className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
              reviewerA.passed
                ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300'
                : 'bg-rose-100 text-rose-800 dark:bg-rose-950/60 dark:text-rose-300'
            }`}
          >
            {reviewerA.passed ? 'PASSED' : 'DRIFT DETECTED'}
          </span>
        </header>

        <p className="text-xs text-gray-700 dark:text-gray-300">{reviewerA.summary}</p>

        {reviewerA.findings.length > 0 ? (
          <ul className="flex flex-col gap-2 pt-1">
            {reviewerA.findings.map((finding) => renderFindingItem(finding))}
          </ul>
        ) : (
          <div className="flex items-center gap-1.5 rounded border border-emerald-200 bg-emerald-50/50 p-2 text-xs text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300">
            <span aria-hidden="true">✓</span>
            <span>原始需求 100% 达成，未引入任何非预期副作用或范围蔓延。</span>
          </div>
        )}
      </article>

      {/* Reviewer B: Blind Clean Context */}
      <article
        data-testid="reviewer-b-panel"
        className="flex flex-col gap-2.5 rounded-lg border border-purple-100 bg-purple-50/30 p-3 dark:border-purple-950 dark:bg-purple-950/20"
      >
        <header className="flex items-center justify-between border-b border-purple-100 pb-2 dark:border-purple-900/50">
          <div className="flex items-center gap-1.5">
            <span className="text-base" aria-hidden="true">
              🙈
            </span>
            <div>
              <h3 className="text-xs font-bold text-gray-900 dark:text-gray-100">Reviewer B · 盲态无偏代码审查</h3>
              <p className="text-[10px] text-purple-600 dark:text-purple-400">
                100% 零先验独立子智能体 · 零 Any 契约 & 边界鲁棒性
              </p>
            </div>
          </div>
          <span
            data-testid="blind-context-tag"
            className="rounded bg-purple-200 px-1.5 py-0.5 text-[9px] font-bold text-purple-900 dark:bg-purple-900 dark:text-purple-100"
          >
            CLEAN CONTEXT
          </span>
        </header>

        <p className="text-xs text-gray-700 dark:text-gray-300">{reviewerB.summary}</p>

        {reviewerB.findings.length > 0 ? (
          <ul className="flex flex-col gap-2 pt-1">
            {reviewerB.findings.map((finding) => renderFindingItem(finding))}
          </ul>
        ) : (
          <div className="flex items-center gap-1.5 rounded border border-emerald-200 bg-emerald-50/50 p-2 text-xs text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-300">
            <span aria-hidden="true">✓</span>
            <span>盲态核验通过：严格 Type-Safe、边界除零与越界防护健全。</span>
          </div>
        )}
      </article>
    </section>
  );
};
