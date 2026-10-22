'use client';

/**
 * [INPUT]
 * - ./types::TriageReport (POS: 失效分诊契约)
 * - lucide-react::Stethoscope, AlertCircle, ShieldAlert (POS: 视觉指示图标)
 *
 * [OUTPUT]
 * - AgentDiagnosticCapsule: 智能体失效诊断胶囊浮动小部件
 *
 * [POS]
 * src/components/features/system-monitor/AgentDiagnosticCapsule.tsx — 智能体运行异常轻量诊断胶囊。
 */

import React from 'react';
import { Stethoscope, AlertCircle, ShieldAlert } from 'lucide-react';
import type { TriageReport } from './types';

interface AgentDiagnosticCapsuleProps {
  report: TriageReport | null;
  onOpenDoctor: () => void;
  className?: string;
}

const SYMPTOM_SHORT_NAMES: Record<string, string> = {
  looping: '死循环反思',
  context_exhaustion: '上下文爆满',
  tool_execution_failed: '沙箱崩溃',
  human_rejection: '审批拦截',
  unknown: '执行异常',
};

export const AgentDiagnosticCapsule: React.FC<AgentDiagnosticCapsuleProps> = ({
  report,
  onOpenDoctor,
  className = '',
}) => {
  if (!report) {
    return null;
  }

  const isHardFailure = report.is_system_failure;
  const symptomText = SYMPTOM_SHORT_NAMES[report.symptom] || '执行受阻';

  return (
    <button
      type="button"
      onClick={onOpenDoctor}
      aria-label="查看智能体排障向导"
      className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium border shadow-sm transition-all hover:scale-[1.02] active:scale-[0.98] ${
        isHardFailure
          ? 'bg-destructive/15 text-destructive border-destructive/30 hover:bg-destructive/20'
          : 'bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/30 hover:bg-amber-500/20'
      } ${className}`}
    >
      {isHardFailure ? (
        <ShieldAlert className="w-3.5 h-3.5 shrink-0 animate-pulse text-destructive" />
      ) : (
        <AlertCircle className="w-3.5 h-3.5 shrink-0 text-amber-600 dark:text-amber-400" />
      )}
      <span className="truncate">
        诊断: {symptomText}
      </span>
      <span className="w-1.5 h-1.5 rounded-full bg-current opacity-60" />
      <span className="inline-flex items-center gap-1 text-[11px] underline underline-offset-2 opacity-90">
        <Stethoscope className="w-3 h-3" />
        排障
      </span>
    </button>
  );
};
