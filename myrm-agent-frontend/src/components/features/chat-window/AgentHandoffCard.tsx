/**
 * [INPUT]
 * - react (POS: UI 组件与内部状态驱动)
 * - lucide-react (POS: 矢量图标库)
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind 样式合并纯函数)
 *
 * [OUTPUT]
 * - AgentHandoffCard: 对话内 @Bot 任务移交视觉卡组件
 * - AgentHandoffCardProps: 组件属性接口
 * - HandoffStageItem: 五阶段生命周期阶段数据类型
 * - AgentParticipant: 智能体角色与人设数据类型
 * - HandoffCardStatus: 移交生命周期状态枚举类型
 *
 * [POS]
 * 智能体对话窗口内专用的任务移交视觉卡（ChatAtBotTaskHandoffDelegation）。
 * 呈现目标 Bot Avatar、角色、Persona 标签与意图，
 * 驱动 BkashJosi 五阶段编排进度条，支持人权审批闸门、
 * 一键直通 PR / 采纳 CTA 以及 Orchestrator 汇总报告折叠展示。
 */
import React, { useState } from 'react';
import {
  ArrowRight,
  ShieldCheck,
  CheckCircle2,
  Clock,
  AlertTriangle,
  XCircle,
  GitPullRequest,
  Check,
  ChevronDown,
  ChevronUp,
  RotateCcw,
  Sparkles,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export type HandoffStageStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | 'blocked';

export interface HandoffStageItem {
  stageId: string;
  label: string;
  status: HandoffStageStatus;
  summary?: string;
  timestamp?: number;
}

export interface AgentParticipant {
  profileId: string;
  name: string;
  avatar?: string;
  role: string;
  personalityTags?: string[];
}

export type HandoffCardStatus = 'pending' | 'awaiting_approval' | 'in_progress' | 'completed' | 'rejected';

export interface AgentHandoffCardProps {
  handoffId: string;
  sourceAgent: AgentParticipant;
  targetAgent: AgentParticipant;
  taskIntent: string;
  status: HandoffCardStatus;
  stages: HandoffStageItem[];
  requiresApproval?: boolean;
  resumeContextNote?: string | null;
  deliverables?: string[];
  orchestratorSummary?: string | null;
  onApprove?: (handoffId: string) => Promise<void> | void;
  onReject?: (handoffId: string, comment?: string) => Promise<void> | void;
  onSendToPR?: (handoffId: string) => Promise<void> | void;
  onAccept?: (handoffId: string) => Promise<void> | void;
  className?: string;
}

const renderStageIcon = (status: HandoffStageStatus) => {
  switch (status) {
    case 'completed':
      return <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />;
    case 'in_progress':
      return <div className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse shrink-0" />;
    case 'failed':
    case 'blocked':
      return <XCircle className="w-4 h-4 text-rose-500 shrink-0" />;
    case 'pending':
    default:
      return <div className="w-2 h-2 rounded-full bg-neutral-300 dark:bg-neutral-600 shrink-0" />;
  }
};

export const AgentHandoffCard: React.FC<AgentHandoffCardProps> = ({
  handoffId,
  sourceAgent,
  targetAgent,
  taskIntent,
  status,
  stages,
  requiresApproval = false,
  resumeContextNote,
  deliverables = [],
  orchestratorSummary,
  onApprove,
  onReject,
  onSendToPR,
  onAccept,
  className,
}) => {
  const [isSummaryExpanded, setIsSummaryExpanded] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const runAction = async (actionFn?: (id: string) => Promise<void> | void) => {
    if (!actionFn || isSubmitting) {
      return;
    }
    setIsSubmitting(true);
    try {
      await actionFn(handoffId);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      data-testid="agent-handoff-card"
      data-handoff-id={handoffId}
      className={cn(
        'rounded-xl border p-4 transition-all duration-200 shadow-sm text-sm',
        'bg-white dark:bg-neutral-900 border-neutral-200 dark:border-neutral-800',
        status === 'awaiting_approval' && 'border-amber-300 dark:border-amber-700/60 ring-1 ring-amber-400/30',
        status === 'completed' && 'border-emerald-300/80 dark:border-emerald-800/60',
        className
      )}
    >
      {/* 头部：来源与目标 Agent 画像、角色定位与状态徽章 */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-neutral-100 dark:border-neutral-800">
        <div className="flex items-center gap-2 flex-wrap">
          <div className="flex items-center gap-1.5 font-medium text-neutral-700 dark:text-neutral-200">
            {sourceAgent.avatar ? (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img src={sourceAgent.avatar} alt={sourceAgent.name} className="w-5 h-5 rounded-full object-cover" />
            ) : (
              <span className="w-5 h-5 rounded-full bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center text-[10px] text-neutral-600 dark:text-neutral-300 font-bold">
                {sourceAgent.name.charAt(0)}
              </span>
            )}
            <span className="text-xs">{sourceAgent.name}</span>
          </div>

          <ArrowRight className="w-3.5 h-3.5 text-neutral-400" />

          <div className="flex items-center gap-1.5 font-semibold text-neutral-900 dark:text-neutral-100">
            {targetAgent.avatar ? (
              /* eslint-disable-next-line @next/next/no-img-element */
              <img src={targetAgent.avatar} alt={targetAgent.name} className="w-6 h-6 rounded-full object-cover ring-1 ring-blue-500/40" />
            ) : (
              <span className="w-6 h-6 rounded-full bg-blue-100 dark:bg-blue-900/60 flex items-center justify-center text-xs text-blue-600 dark:text-blue-300 font-bold">
                {targetAgent.name.charAt(0)}
              </span>
            )}
            <span>{targetAgent.name}</span>
            <span className="text-[11px] font-normal px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300 border border-blue-200/60 dark:border-blue-800/50">
              {targetAgent.role}
            </span>
          </div>

          {targetAgent.personalityTags && targetAgent.personalityTags.length > 0 && (
            <div className="flex items-center gap-1">
              {targetAgent.personalityTags.map((tag) => (
                <span
                  key={tag}
                  className="text-[10px] px-1.5 py-0.5 rounded bg-purple-50 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300 border border-purple-200/50 dark:border-purple-800/40"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
        </div>

        {/* 状态徽章与恢复标记 */}
        <div className="flex items-center gap-2">
          {resumeContextNote && (
            <span
              data-testid="resume-context-badge"
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] bg-indigo-50 text-indigo-700 dark:bg-indigo-950/60 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800/60"
              title={resumeContextNote}
            >
              <RotateCcw className="w-3 h-3" />
              <span>恢复上下文</span>
            </span>
          )}

          {status === 'awaiting_approval' && (
            <span
              data-testid="awaiting-approval-badge"
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-100 text-amber-800 dark:bg-amber-950/80 dark:text-amber-200 animate-pulse border border-amber-300 dark:border-amber-700"
            >
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600 dark:text-amber-400" />
              <span>等待审批</span>
            </span>
          )}

          {status === 'in_progress' && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 text-blue-700 dark:bg-blue-950/60 dark:text-blue-300">
              <span className="w-2 h-2 rounded-full bg-blue-500 animate-ping" />
              <span>执行中</span>
            </span>
          )}

          {status === 'completed' && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              <span>已完成</span>
            </span>
          )}

          {status === 'rejected' && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-rose-50 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300">
              <XCircle className="w-3.5 h-3.5 text-rose-600 dark:text-rose-400" />
              <span>已驳回</span>
            </span>
          )}
        </div>
      </div>

      {/* 移交任务意图 */}
      <div className="mt-3">
        <p className="text-sm text-neutral-800 dark:text-neutral-200 leading-relaxed font-medium">
          {taskIntent}
        </p>
      </div>

      {/* BkashJosi 五阶段编排生命周期状态条 */}
      <div className="mt-4 pt-3 border-t border-neutral-100 dark:border-neutral-800">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-neutral-400 dark:text-neutral-500 mb-2 flex items-center justify-between">
          <span>五阶段交付流水线 (Five-Stage Stack)</span>
          <span className="text-[10px] lowercase text-neutral-400">
            {stages.filter((s) => s.status === 'completed').length}/{stages.length} 完成
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-5 gap-2" data-testid="five-stages-container">
          {stages.map((stage, idx) => (
            <div
              key={stage.stageId}
              data-testid={`stage-item-${stage.stageId}`}
              className={cn(
                'p-2 rounded-lg border text-xs flex flex-col gap-1 transition-all',
                stage.status === 'completed' && 'bg-emerald-50/50 dark:bg-emerald-950/20 border-emerald-200/60 dark:border-emerald-800/40 text-emerald-900 dark:text-emerald-200',
                stage.status === 'in_progress' && 'bg-blue-50/60 dark:bg-blue-950/30 border-blue-300 dark:border-blue-700 text-blue-900 dark:text-blue-100 ring-1 ring-blue-400/20',
                stage.status === 'pending' && 'bg-neutral-50 dark:bg-neutral-800/40 border-neutral-200/50 dark:border-neutral-700/40 text-neutral-500 dark:text-neutral-400',
                (stage.status === 'failed' || stage.status === 'blocked') && 'bg-rose-50 dark:bg-rose-950/30 border-rose-300 dark:border-rose-800 text-rose-800 dark:text-rose-200'
              )}
            >
              <div className="flex items-center justify-between gap-1">
                <span className="text-[10px] font-mono text-neutral-400 dark:text-neutral-500">0{idx + 1}</span>
                {renderStageIcon(stage.status)}
              </div>
              <div className="font-medium truncate" title={stage.label}>
                {stage.label}
              </div>
              {stage.summary && (
                <div className="text-[10px] text-neutral-500 dark:text-neutral-400 line-clamp-2 mt-0.5 leading-tight">
                  {stage.summary}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 人权审批闸门操作区 (Human Gate & Inline CTA) */}
      {status === 'awaiting_approval' && requiresApproval && (
        <div
          data-testid="approval-actions-container"
          className="mt-4 p-3 rounded-lg bg-amber-50/80 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/50 flex flex-wrap items-center justify-between gap-3"
        >
          <div className="flex items-center gap-2 text-xs text-amber-800 dark:text-amber-200">
            <ShieldCheck className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
            <span>此任务涉及专职委托，需您审批确认后立即启动执行。</span>
          </div>

          <div className="flex items-center gap-2 ml-auto">
            <button
              type="button"
              data-testid="reject-button"
              disabled={isSubmitting}
              onClick={() => runAction(onReject)}
              className="px-3 py-1.5 text-xs font-medium rounded-md bg-white dark:bg-neutral-800 text-neutral-700 dark:text-neutral-300 border border-neutral-300 dark:border-neutral-700 hover:bg-neutral-50 dark:hover:bg-neutral-700 disabled:opacity-50 transition-colors"
            >
              驳回移交
            </button>
            <button
              type="button"
              data-testid="approve-button"
              disabled={isSubmitting}
              onClick={() => runAction(onApprove)}
              className="px-3.5 py-1.5 text-xs font-medium rounded-md bg-blue-600 hover:bg-blue-700 text-white shadow-sm disabled:opacity-50 transition-colors flex items-center gap-1.5"
            >
              <Check className="w-3.5 h-3.5" />
              <span>批准派发</span>
            </button>
          </div>
        </div>
      )}

      {/* 成果交付与直通 PR 操作区 (Deliverables & Completion CTA) */}
      {status === 'completed' && (
        <div className="mt-4 p-3 rounded-lg bg-neutral-50 dark:bg-neutral-800/60 border border-neutral-200 dark:border-neutral-700/60 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-neutral-800 dark:text-neutral-200 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-amber-500" />
              任务已交付完成
            </span>
            {deliverables.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 mt-0.5">
                {deliverables.map((item) => (
                  <span
                    key={item}
                    className="text-[11px] font-mono px-2 py-0.5 rounded bg-white dark:bg-neutral-900 border border-neutral-200 dark:border-neutral-700 text-neutral-700 dark:text-neutral-300"
                  >
                    {item}
                  </span>
                ))}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2 ml-auto">
            {onSendToPR && (
              <button
                type="button"
                data-testid="send-to-pr-button"
                disabled={isSubmitting}
                onClick={() => runAction(onSendToPR)}
                className="px-3 py-1.5 text-xs font-medium rounded-md bg-white dark:bg-neutral-800 text-neutral-800 dark:text-neutral-200 border border-neutral-300 dark:border-neutral-600 hover:bg-neutral-100 dark:hover:bg-neutral-700 transition-colors flex items-center gap-1.5"
              >
                <GitPullRequest className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" />
                <span>直通提交 PR</span>
              </button>
            )}
            {onAccept && (
              <button
                type="button"
                data-testid="accept-deliverable-button"
                disabled={isSubmitting}
                onClick={() => runAction(onAccept)}
                className="px-3.5 py-1.5 text-xs font-medium rounded-md bg-emerald-600 hover:bg-emerald-700 text-white shadow-sm transition-colors flex items-center gap-1.5"
              >
                <Check className="w-3.5 h-3.5" />
                <span>采纳成果</span>
              </button>
            )}
          </div>
        </div>
      )}

      {/* Orchestrator 汇总汇报与折叠控制 */}
      {orchestratorSummary && (
        <div className="mt-3 pt-2">
          <button
            type="button"
            data-testid="toggle-summary-button"
            onClick={() => setIsSummaryExpanded(!isSummaryExpanded)}
            className="flex items-center justify-between w-full text-xs font-medium text-neutral-500 hover:text-neutral-700 dark:text-neutral-400 dark:hover:text-neutral-200 py-1 transition-colors"
          >
            <span className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-neutral-400" />
              <span>主编排器汇报总结 (Orchestrator Review)</span>
            </span>
            {isSummaryExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>

          {isSummaryExpanded && (
            <div
              data-testid="orchestrator-summary-content"
              className="mt-1 p-2.5 rounded-lg bg-neutral-50 dark:bg-neutral-800/40 text-xs text-neutral-700 dark:text-neutral-300 leading-relaxed border border-neutral-200/60 dark:border-neutral-700/40"
            >
              {orchestratorSummary}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
