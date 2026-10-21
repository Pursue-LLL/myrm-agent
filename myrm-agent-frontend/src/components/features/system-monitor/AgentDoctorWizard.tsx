'use client';

/**
 * [INPUT]
 * - ./types::TriageReport, BreakpointStage, FailureSymptom, NegativeOutcome, RedispatchResponse (POS: 排障契约)
 * - lucide-react::Stethoscope, CheckCircle2, AlertTriangle, XCircle, ArrowRight, RotateCcw, ShieldAlert, Sparkles, X (POS: 视觉图标)
 *
 * [OUTPUT]
 * - AgentDoctorWizard: 智能体失效自检排障向导与就地重发控制台组件
 *
 * [POS]
 * src/components/features/system-monitor/AgentDoctorWizard.tsx — 智能体失效诊断与分诊向导视窗。
 */

import React, { useState } from 'react';
import {
  Stethoscope,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ArrowRight,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  X,
} from 'lucide-react';
import type {
  TriageReport,
  BreakpointStage,
  FailureSymptom,
  NegativeOutcome,
} from './types';

interface AgentDoctorWizardProps {
  report: TriageReport;
  isOpen: boolean;
  onClose: () => void;
  onRedispatch?: (
    triageId: string,
    traceId: string,
    resumeStage?: BreakpointStage
  ) => Promise<void>;
  isRedispatching?: boolean;
  className?: string;
}

const STAGE_ORDER: BreakpointStage[] = [
  'input_intake',
  'context_retrieval',
  'llm_reasoning',
  'approval_gate',
  'tool_execution',
  'output_delivery',
];

const STAGE_LABELS: Record<BreakpointStage, string> = {
  input_intake: '用户输入摄入',
  context_retrieval: '上下文装配检索',
  llm_reasoning: '大模型推理规划',
  approval_gate: '人机审批网关',
  tool_execution: '工具执行沙箱',
  output_delivery: '最终答复交付',
};

const SYMPTOM_LABELS: Record<FailureSymptom, { label: string; desc: string }> = {
  looping: { label: '死循环反思', desc: '检测到高频重试或循环震荡' },
  context_exhaustion: { label: '上下文窗口爆满', desc: '超出单轮最大 Token 上限' },
  tool_execution_failed: { label: '工具沙箱崩溃', desc: '系统命令执行或超时异常' },
  human_rejection: { label: '人工审批拒绝', desc: '安全规则或人为判定拦截' },
  unknown: { label: '未知执行异常', desc: '未分类的内部链路中断' },
};

const NEGATIVE_OUTCOME_LABELS: Record<NegativeOutcome, string> = {
  none: '非预期异常',
  denied: '安全防御拦截 (Denied)',
  parameter_mismatch: '参数校验不符 (Mismatch)',
  zero_retrieval: '知识库零召回 (Zero Retrieval)',
  budget_exhaustion: '算力/Token 预算耗尽',
};

export const AgentDoctorWizard: React.FC<AgentDoctorWizardProps> = ({
  report,
  isOpen,
  onClose,
  onRedispatch,
  isRedispatching = false,
  className = '',
}) => {
  const [selectedResumeStage, setSelectedResumeStage] = useState<BreakpointStage>(
    report.root_stage
  );
  const [redispatchSuccess, setRedispatchSuccess] = useState<string | null>(null);

  if (!isOpen) {
    return null;
  }

  const rootStageIndex = STAGE_ORDER.indexOf(report.root_stage);
  const symptomMeta = SYMPTOM_LABELS[report.symptom] || SYMPTOM_LABELS.unknown;

  const handleRedispatch = async () => {
    if (!onRedispatch) return;
    try {
      await onRedispatch(report.triage_id, report.trace_id, selectedResumeStage);
      setRedispatchSuccess(`已成功触发就地重发，断点从 [${STAGE_LABELS[selectedResumeStage]}] 恢复。`);
    } catch {
      // 外部已处理错误反馈
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="agent-doctor-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-sm"
    >
      <div
        className={`w-full max-w-2xl bg-card border border-border rounded-xl shadow-2xl flex flex-col max-h-[90vh] overflow-hidden ${className}`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-muted/40">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-primary/10 text-primary">
              <Stethoscope className="w-5 h-5" />
            </div>
            <div>
              <h2 id="agent-doctor-title" className="text-base font-semibold text-foreground">
                智能体故障诊断与分诊向导 (Agent Doctor)
              </h2>
              <p className="text-xs text-muted-foreground">
                分诊号: {report.triage_id} · Trace: {report.trace_id}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="关闭向导"
            className="p-1.5 rounded-md hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Content Body */}
        <div className="p-6 space-y-6 overflow-y-auto">
          {/* 表象与严重级别摘要 */}
          <div
            className={`p-4 rounded-lg border ${
              report.is_system_failure
                ? 'bg-destructive/10 border-destructive/20 text-destructive dark:text-red-400'
                : 'bg-amber-500/10 border-amber-500/20 text-amber-700 dark:text-amber-400'
            }`}
          >
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-2">
                {report.is_system_failure ? (
                  <ShieldAlert className="w-5 h-5 shrink-0" />
                ) : (
                  <Sparkles className="w-5 h-5 shrink-0" />
                )}
                <div>
                  <span className="font-semibold text-sm">
                    {symptomMeta.label}
                  </span>
                  <span className="ml-2 text-xs opacity-80">
                    ({report.is_system_failure ? '系统硬故障' : '业务负例/预期防御'})
                  </span>
                </div>
              </div>
              <span className="text-xs px-2 py-0.5 rounded font-mono bg-background/60 border border-current">
                {NEGATIVE_OUTCOME_LABELS[report.negative_outcome] || report.negative_outcome}
              </span>
            </div>
            <p className="mt-2 text-xs leading-relaxed opacity-90">{report.summary}</p>
          </div>

          {/* 六大断点链路状态流 */}
          <div>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">
              链路断点时序自检 (Breakpoint Lineage)
            </h3>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {STAGE_ORDER.map((stage, idx) => {
                const isPassed = rootStageIndex >= 0 && idx < rootStageIndex;
                const isRoot = idx === rootStageIndex;

                let badgeColor = 'bg-muted/40 border-border text-muted-foreground';
                let Icon = ArrowRight;

                if (isPassed) {
                  badgeColor = 'bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400';
                  Icon = CheckCircle2;
                } else if (isRoot) {
                  if (report.is_system_failure) {
                    badgeColor = 'bg-destructive/15 border-destructive/40 text-destructive font-medium';
                    Icon = XCircle;
                  } else {
                    badgeColor = 'bg-amber-500/15 border-amber-500/40 text-amber-600 dark:text-amber-400 font-medium';
                    Icon = AlertTriangle;
                  }
                }

                return (
                  <div
                    key={stage}
                    className={`flex items-center gap-2 p-2.5 rounded-lg border text-xs transition-all ${badgeColor}`}
                  >
                    <Icon className="w-4 h-4 shrink-0" />
                    <div className="truncate">
                      <div className="font-medium truncate">{STAGE_LABELS[stage]}</div>
                      <div className="text-[10px] opacity-75 font-mono">
                        {isPassed ? '正常通过' : isRoot ? '中断断点' : '未到达'}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 根因分析清单 */}
          <div>
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
              故障诱因诊断 (Detailed Diagnostics)
            </h3>
            <ul className="space-y-1.5">
              {report.detailed_reasons.map((reason, index) => (
                <li
                  key={index}
                  className="flex items-start gap-2 text-xs text-foreground/90 bg-muted/20 p-2 rounded border border-border/50"
                >
                  <span className="font-mono text-muted-foreground shrink-0">{index + 1}.</span>
                  <span>{reason}</span>
                </li>
              ))}
            </ul>
          </div>

          {/* 修复行动方案 */}
          <div className="p-3 bg-accent/40 rounded-lg border border-accent">
            <h3 className="text-xs font-semibold text-foreground flex items-center gap-1.5 mb-1">
              <Sparkles className="w-3.5 h-3.5 text-primary" />
              向导建议方案 (Doctor Remediation)
            </h3>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {report.remediation_action}
            </p>
          </div>

          {/* 成功重发提示 */}
          {redispatchSuccess && (
            <div className="p-3 bg-emerald-500/15 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 rounded-lg text-xs flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 shrink-0" />
              <span>{redispatchSuccess}</span>
            </div>
          )}
        </div>

        {/* Footer 操作栏 */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-muted/40">
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">重发恢复点:</span>
            <select
              value={selectedResumeStage}
              onChange={(e) => setSelectedResumeStage(e.target.value as BreakpointStage)}
              className="text-xs px-2.5 py-1.5 rounded-md bg-background border border-border text-foreground focus:outline-none focus:ring-1 focus:ring-primary"
            >
              {STAGE_ORDER.map((stage) => (
                <option key={stage} value={stage}>
                  {STAGE_LABELS[stage]}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-xs font-medium rounded-lg hover:bg-accent text-foreground transition-colors"
            >
              关闭
            </button>
            <button
              type="button"
              disabled={!report.can_redispatch || isRedispatching}
              onClick={handleRedispatch}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors shadow-sm"
            >
              <RotateCcw className={`w-3.5 h-3.5 ${isRedispatching ? 'animate-spin' : ''}`} />
              <span>{isRedispatching ? '正在重发...' : '就地恢复并重发'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
