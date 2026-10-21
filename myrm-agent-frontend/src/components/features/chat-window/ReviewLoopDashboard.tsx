'use client';

import React, { useState } from 'react';
import {
  ShieldCheck,
  FlaskConical,
  Feather,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  RefreshCw,
  X,
  FileCode,
  Sparkles,
} from 'lucide-react';

export type ReviewPerspectiveType = 'correctness' | 'test_coverage' | 'simplicity';
export type FindingSeverityType = 'blocker' | 'critical' | 'major' | 'minor' | 'suggestion';
export type ReviewLoopStatusType = 'pending' | 'in_review' | 'fixing' | 'converged' | 'max_rounds_reached';

export interface ReviewFindingData {
  perspective: ReviewPerspectiveType;
  severity: FindingSeverityType;
  file_path: string;
  issue: string;
  suggestion: string;
  line_number?: number | null;
}

export interface PerspectiveReportData {
  perspective: ReviewPerspectiveType;
  reviewer_name: string;
  approved: boolean;
  findings: ReviewFindingData[];
  summary: string;
}

export interface LoopRoundData {
  round_number: number;
  perspective_reports: Record<string, PerspectiveReportData>;
  all_findings: ReviewFindingData[];
  has_blocking_issues: boolean;
  fix_description?: string | null;
  converged: boolean;
  timestamp?: string;
}

export interface ReviewLoopDashboardProps {
  loopId: string;
  sessionId: string;
  status: ReviewLoopStatusType;
  currentRound: number;
  maxRounds: number;
  isClean: boolean;
  rounds: LoopRoundData[];
  onAdvanceRound?: (loopId: string) => void;
  onApprove?: (loopId: string) => void;
  onClose?: () => void;
  className?: string;
}

const PERSPECTIVE_CONFIG: Record<
  ReviewPerspectiveType,
  { label: string; icon: React.ComponentType<{ className?: string }>; color: string }
> = {
  correctness: {
    label: '正确性探针',
    icon: ShieldCheck,
    color: 'text-emerald-600 dark:text-emerald-400 border-emerald-300 dark:border-emerald-800',
  },
  test_coverage: {
    label: '测试完整性',
    icon: FlaskConical,
    color: 'text-sky-600 dark:text-sky-400 border-sky-300 dark:border-sky-800',
  },
  simplicity: {
    label: '反过度设计',
    icon: Feather,
    color: 'text-amber-600 dark:text-amber-400 border-amber-300 dark:border-amber-800',
  },
};

const SEVERITY_BADGE: Record<FindingSeverityType, string> = {
  blocker: 'bg-rose-100 text-rose-800 dark:bg-rose-950/80 dark:text-rose-300 border-rose-300',
  critical: 'bg-red-100 text-red-800 dark:bg-red-950/80 dark:text-red-300 border-red-300',
  major: 'bg-amber-100 text-amber-800 dark:bg-amber-950/80 dark:text-amber-300 border-amber-300',
  minor: 'bg-blue-100 text-blue-800 dark:bg-blue-950/80 dark:text-blue-300 border-blue-300',
  suggestion: 'bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300 border-zinc-200',
};

export const ReviewLoopDashboard: React.FC<ReviewLoopDashboardProps> = ({
  loopId,
  status,
  currentRound,
  maxRounds,
  isClean,
  rounds,
  onAdvanceRound,
  onApprove,
  onClose,
  className = '',
}) => {
  const [selectedPerspective, setSelectedPerspective] = useState<ReviewPerspectiveType | 'all'>('all');
  const latestRound = rounds[rounds.length - 1];

  const filteredFindings = latestRound?.all_findings.filter((f) => {
    if (selectedPerspective === 'all') {
      return true;
    }
    return f.perspective === selectedPerspective;
  }) || [];

  return (
    <div
      data-testid="review-loop-dashboard"
      className={`flex flex-col bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl shadow-lg overflow-hidden transition-all duration-200 ${className}`}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-zinc-50 dark:bg-zinc-900/80 border-b border-zinc-200 dark:border-zinc-800">
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
          <span className="font-semibold text-sm text-zinc-900 dark:text-zinc-100">
            多视角并发代码评审 & 有界自愈环
          </span>
          <span className="px-2 py-0.5 rounded-full text-xs font-mono font-medium bg-zinc-200/80 dark:bg-zinc-800 text-zinc-700 dark:text-zinc-300">
            Round {currentRound}/{maxRounds}
          </span>
          {isClean ? (
            <span
              data-testid="clean-diff-badge"
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800 dark:bg-emerald-950/80 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-700"
            >
              <CheckCircle2 className="w-3 h-3" />
              Clean Diff 已收敛
            </span>
          ) : status === 'max_rounds_reached' ? (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-rose-100 text-rose-800 dark:bg-rose-950/80 dark:text-rose-300 border border-rose-300">
              <AlertCircle className="w-3 h-3" />
              已达最大轮次上限 ({maxRounds})
            </span>
          ) : (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-amber-100 text-amber-800 dark:bg-amber-950/80 dark:text-amber-300 border border-amber-300">
              <RefreshCw className="w-3 h-3 animate-spin" />
              自愈复审中
            </span>
          )}
        </div>

        {onClose && (
          <button
            type="button"
            data-testid="close-dashboard-button"
            onClick={onClose}
            className="p-1 rounded-md text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200 hover:bg-zinc-200/60 dark:hover:bg-zinc-800 transition-colors"
            title="关闭面板"
            aria-label="关闭面板"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Tri-Perspective Status Grid */}
      <div className="grid grid-cols-3 gap-3 p-4 bg-zinc-50/50 dark:bg-zinc-900/40 border-b border-zinc-200 dark:border-zinc-800">
        {(['correctness', 'test_coverage', 'simplicity'] as ReviewPerspectiveType[]).map((p) => {
          const cfg = PERSPECTIVE_CONFIG[p];
          const Icon = cfg.icon;
          const report = latestRound?.perspective_reports[p];
          const isApproved = report?.approved ?? false;
          const issueCount = report?.findings.length ?? 0;
          const isSelected = selectedPerspective === p;

          return (
            <button
              type="button"
              key={p}
              data-testid={`perspective-card-${p}`}
              onClick={() => setSelectedPerspective(isSelected ? 'all' : p)}
              className={`flex flex-col gap-1.5 p-3 rounded-lg border text-left transition-all cursor-pointer ${
                isSelected
                  ? 'border-indigo-500 ring-2 ring-indigo-500/20 bg-indigo-50/40 dark:bg-indigo-950/30'
                  : 'border-zinc-200 dark:border-zinc-800 hover:border-zinc-300 dark:hover:border-zinc-700 bg-white dark:bg-zinc-800/80'
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Icon className={`w-4 h-4 ${cfg.color.split(' ')[0]}`} />
                  <span className="font-medium text-xs text-zinc-800 dark:text-zinc-200">
                    {cfg.label}
                  </span>
                </div>
                {isApproved ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                ) : (
                  <AlertTriangle className="w-4 h-4 text-amber-500 shrink-0" />
                )}
              </div>
              <div className="flex items-center justify-between text-[11px] text-zinc-500 dark:text-zinc-400">
                <span>{isApproved ? '审查通过' : `${issueCount} 项需修复`}</span>
                <span className="font-mono text-[10px] text-zinc-400">{report?.reviewer_name || p}</span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Findings List */}
      <div className="flex flex-col flex-1 max-h-72 overflow-y-auto p-4 divide-y divide-zinc-100 dark:divide-zinc-800">
        {filteredFindings.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-center text-zinc-400">
            <CheckCircle2 className="w-8 h-8 text-emerald-500/80 mb-2" />
            <p className="text-xs font-medium text-zinc-600 dark:text-zinc-300">
              当前视角无待修复问题
            </p>
            <p className="text-[11px] text-zinc-400 mt-0.5">代码规范、测试用例与复杂度均符合工业级标准</p>
          </div>
        ) : (
          filteredFindings.map((finding, idx) => (
            <div
              key={`${finding.file_path}-${idx}`}
              data-testid={`finding-item-${idx}`}
              className="py-2.5 first:pt-0 last:pb-0 flex flex-col gap-1.5"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 text-xs font-medium">
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold border ${
                      SEVERITY_BADGE[finding.severity]
                    }`}
                  >
                    {finding.severity.toUpperCase()}
                  </span>
                  <span className="flex items-center gap-1 text-zinc-600 dark:text-zinc-300 font-mono text-[11px]">
                    <FileCode className="w-3 h-3 text-zinc-400" />
                    {finding.file_path}
                    {finding.line_number && `:${finding.line_number}`}
                  </span>
                </div>
                <span className="text-[10px] font-mono text-zinc-400 uppercase">
                  {finding.perspective}
                </span>
              </div>

              <p className="text-xs text-zinc-800 dark:text-zinc-200 pl-1 border-l-2 border-amber-400 dark:border-amber-600">
                {finding.issue}
              </p>

              <div className="text-[11px] text-zinc-500 dark:text-zinc-400 bg-zinc-50 dark:bg-zinc-800/50 p-2 rounded border border-zinc-100 dark:border-zinc-800">
                <span className="font-semibold text-zinc-600 dark:text-zinc-300">建议自愈方案：</span>{' '}
                {finding.suggestion}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Footer Controls */}
      <div className="flex items-center justify-between px-4 py-3 bg-zinc-50 dark:bg-zinc-900 border-t border-zinc-200 dark:border-zinc-800">
        <div className="text-xs text-zinc-500 dark:text-zinc-400 truncate max-w-sm">
          {latestRound?.fix_description
            ? `上轮自愈：${latestRound.fix_description}`
            : '等待自愈闭环或合并确认'}
        </div>

        <div className="flex items-center gap-2">
          {!isClean && currentRound < maxRounds && onAdvanceRound && (
            <button
              type="button"
              data-testid="advance-round-button"
              onClick={() => onAdvanceRound(loopId)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 transition-colors shadow-sm"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              推进下一轮自愈修复 (Round {currentRound + 1})
            </button>
          )}

          {isClean && onApprove && (
            <button
              type="button"
              data-testid="approve-clean-diff-button"
              onClick={() => onApprove(loopId)}
              className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-medium text-white bg-emerald-600 hover:bg-emerald-700 transition-colors shadow-sm"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              采纳交付 Clean Diff
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ReviewLoopDashboard;
