/**
 * [INPUT]
 * - react (POS: React 核心与状态钩子)
 * - lucide-react (POS: 矢量图标库，包含 CheckCircle2, ArrowRight, ShieldCheck, Sparkles, RefreshCw, AlertCircle, Layers 等)
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind 样式合并纯函数)
 *
 * [OUTPUT]
 * - SplitSessionGoalCard: 交付与规划双会话流转 Goal 模版监控与操作卡片
 * - SplitSessionGoalCardProps: 组件属性契约
 * - GoalPhase: 阶段联合类型
 * - DeliverableItem: 交付产物条目契约
 * - NextPlanDraft: 下一轮规划草案契约
 * - SplitSessionGoalData: 双会话 Goal 数据实体契约
 *
 * [POS]
 * 对话窗口内双会话流转 Goal 卡片（SplitSessionShipPlanGoalTemplate）。
 * 明确划分 Window 1: Ship (交付实施与硬门禁验证) 与 Window 2: Plan (干净上下文规划与目标衔接)，
 * 提供双阶段步进指示器、交付凭证核验徽章、上下文隔离收益展示与下阶段目标流转触发器。
 */
import React, { useState } from 'react';
import {
  CheckCircle2,
  ArrowRight,
  ShieldCheck,
  Sparkles,
  AlertCircle,
  FileCheck2,
  Terminal,
  Zap,
  Check,
  Ban,
  Clock,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export type GoalPhase =
  | 'ship_in_progress'
  | 'ship_verified'
  | 'plan_in_progress'
  | 'completed'
  | 'abandoned';

export interface DeliverableItem {
  id: string;
  title: string;
  type: 'code_diff' | 'test_report' | 'doc' | 'artifact';
  verified: boolean;
  uri?: string;
}

export interface NextPlanDraft {
  title: string;
  summary: string;
  targetObjectives: string[];
  suggestedTemplateId?: string;
}

export interface SplitSessionGoalData {
  goalId: string;
  templateId: string;
  templateName: string;
  phase: GoalPhase;
  shipSessionId: string;
  planSessionId?: string;
  testPassRatePct?: number;
  automatedTestsPassed: boolean;
  deliverables: DeliverableItem[];
  contextTokensSaved?: number;
  weeklyQuotaSavedPct?: number;
  nextPlanDraft?: NextPlanDraft;
}

export interface SplitSessionGoalCardProps {
  goal: SplitSessionGoalData;
  isLoading?: boolean;
  onAdvanceStage?: (goalId: string, nextPhase: GoalPhase) => Promise<void> | void;
  onDraftNextGoal?: (goalId: string, draft: NextPlanDraft) => Promise<void> | void;
  onAbandon?: (goalId: string) => Promise<void> | void;
  className?: string;
}

function getNextPhase(current: GoalPhase): GoalPhase | null {
  switch (current) {
    case 'ship_in_progress':
      return 'ship_verified';
    case 'ship_verified':
      return 'plan_in_progress';
    case 'plan_in_progress':
      return 'completed';
    default:
      return null;
  }
}

function getPhaseLabel(phase: GoalPhase): string {
  switch (phase) {
    case 'ship_in_progress':
      return 'Window 1: 交付实施中';
    case 'ship_verified':
      return 'Window 1: 交付已核验';
    case 'plan_in_progress':
      return 'Window 2: 下阶段规划中';
    case 'completed':
      return '已完成双阶段流转';
    case 'abandoned':
      return '已终止';
  }
}

export const SplitSessionGoalCard: React.FC<SplitSessionGoalCardProps> = ({
  goal,
  isLoading = false,
  onAdvanceStage,
  onDraftNextGoal,
  onAbandon,
  className,
}) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const nextPhase = getNextPhase(goal.phase);

  const handleAdvance = async (): Promise<void> => {
    if (!nextPhase || !onAdvanceStage || isSubmitting) {
      return;
    }
    try {
      setIsSubmitting(true);
      await onAdvanceStage(goal.goalId, nextPhase);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleAbandon = async (): Promise<void> => {
    if (!onAbandon || isSubmitting) {
      return;
    }
    try {
      setIsSubmitting(true);
      await onAbandon(goal.goalId);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePublishDraft = async (): Promise<void> => {
    if (!goal.nextPlanDraft || !onDraftNextGoal || isSubmitting) {
      return;
    }
    try {
      setIsSubmitting(true);
      await onDraftNextGoal(goal.goalId, goal.nextPlanDraft);
    } finally {
      setIsSubmitting(false);
    }
  };

  const isShipActive = goal.phase === 'ship_in_progress' || goal.phase === 'ship_verified';
  const isShipDone = goal.phase === 'plan_in_progress' || goal.phase === 'completed';
  const isPlanActive = goal.phase === 'plan_in_progress';
  const isAllDone = goal.phase === 'completed';

  return (
    <div
      data-testid="split-session-goal-card"
      className={cn(
        'w-full max-w-2xl rounded-xl border border-border/80 bg-card/95 text-card-foreground shadow-sm overflow-hidden text-xs transition-all',
        className
      )}
    >
      {/* 头部信息 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border/50 bg-muted/20">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-primary/10 text-primary">
            <Zap className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-sm text-foreground">{goal.templateName}</span>
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-muted text-muted-foreground">
                {goal.templateId}
              </span>
            </div>
            <p className="text-[11px] text-muted-foreground mt-0.5">
              双会话流转目标 · ID: <span className="font-mono">{goal.goalId}</span>
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span
            data-testid="phase-badge"
            className={cn(
              'px-2 py-0.5 rounded-full font-medium text-[11px] border',
              goal.phase === 'completed' && 'bg-emerald-500/10 text-emerald-600 border-emerald-500/30',
              goal.phase === 'abandoned' && 'bg-muted text-muted-foreground border-border',
              goal.phase === 'ship_in_progress' && 'bg-sky-500/10 text-sky-600 border-sky-500/30',
              goal.phase === 'ship_verified' && 'bg-indigo-500/10 text-indigo-600 border-indigo-500/30',
              goal.phase === 'plan_in_progress' && 'bg-amber-500/10 text-amber-600 border-amber-500/30'
            )}
          >
            {getPhaseLabel(goal.phase)}
          </span>
        </div>
      </div>

      {/* 双窗口流转 Stepper */}
      <div className="px-4 py-3 bg-background/50 border-b border-border/40">
        <div className="flex items-center justify-between gap-2">
          {/* Step 1: Ship Window */}
          <div
            className={cn(
              'flex-1 flex items-center gap-2.5 p-2 rounded-lg border transition-all',
              isShipDone && 'bg-emerald-500/5 border-emerald-500/30 text-emerald-700 dark:text-emerald-400',
              isShipActive && 'bg-primary/5 border-primary/40 text-foreground ring-1 ring-primary/20',
              !isShipActive && !isShipDone && 'bg-muted/30 border-transparent text-muted-foreground'
            )}
          >
            <div
              className={cn(
                'w-6 h-6 rounded-full flex items-center justify-center font-bold text-[11px] shrink-0',
                isShipDone && 'bg-emerald-500 text-white',
                isShipActive && 'bg-primary text-primary-foreground',
                !isShipActive && !isShipDone && 'bg-muted text-muted-foreground'
              )}
            >
              {isShipDone ? <Check className="w-3.5 h-3.5" /> : '1'}
            </div>
            <div className="min-w-0">
              <div className="font-medium truncate">Window 1: Ship (交付)</div>
              <div className="text-[10px] text-muted-foreground truncate">
                代码实现与硬门禁验证
              </div>
            </div>
          </div>

          <ArrowRight className="w-4 h-4 text-muted-foreground shrink-0" />

          {/* Step 2: Plan Window */}
          <div
            className={cn(
              'flex-1 flex items-center gap-2.5 p-2 rounded-lg border transition-all',
              isAllDone && 'bg-emerald-500/5 border-emerald-500/30 text-emerald-700 dark:text-emerald-400',
              isPlanActive && 'bg-amber-500/5 border-amber-500/40 text-foreground ring-1 ring-amber-500/20',
              !isPlanActive && !isAllDone && 'bg-muted/30 border-transparent text-muted-foreground'
            )}
          >
            <div
              className={cn(
                'w-6 h-6 rounded-full flex items-center justify-center font-bold text-[11px] shrink-0',
                isAllDone && 'bg-emerald-500 text-white',
                isPlanActive && 'bg-amber-500 text-white',
                !isPlanActive && !isAllDone && 'bg-muted text-muted-foreground'
              )}
            >
              {isAllDone ? <Check className="w-3.5 h-3.5" /> : '2'}
            </div>
            <div className="min-w-0">
              <div className="font-medium truncate">Window 2: Plan (规划)</div>
              <div className="text-[10px] text-muted-foreground truncate">
                干净上下文架构起草
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* 主体区域：交付验证与产物 */}
      <div className="p-4 space-y-3.5">
        {/* 硬门禁与测试状态 */}
        <div className="flex flex-wrap items-center justify-between gap-2 p-2.5 rounded-lg bg-muted/40 border border-border/60">
          <div className="flex items-center gap-2">
            {goal.automatedTestsPassed ? (
              <ShieldCheck className="w-4 h-4 text-emerald-500 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 text-amber-500 shrink-0" />
            )}
            <span className="font-medium">
              自动化硬门禁:{' '}
              <span
                className={cn(
                  'font-semibold',
                  goal.automatedTestsPassed ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'
                )}
              >
                {goal.automatedTestsPassed ? '100% 测试通过' : '测试待验证或未通过'}
              </span>
            </span>
            {goal.testPassRatePct !== undefined && (
              <span className="text-[11px] text-muted-foreground">({goal.testPassRatePct}% 达成)</span>
            )}
          </div>

          <div className="text-[11px] text-muted-foreground flex items-center gap-1.5 font-mono">
            <Terminal className="w-3.5 h-3.5" />
            会话: {goal.shipSessionId}
          </div>
        </div>

        {/* 交付产物清单 */}
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="font-semibold text-foreground flex items-center gap-1">
              <FileCheck2 className="w-3.5 h-3.5 text-primary" />
              交付凭证清单 (Dossier Deliverables)
            </span>
            <span className="text-[10px] text-muted-foreground">
              {goal.deliverables.length} 项产物
            </span>
          </div>

          <div className="space-y-1.5" data-testid="deliverables-list">
            {goal.deliverables.map((item) => (
              <div
                key={item.id}
                className="flex items-center justify-between px-2.5 py-1.5 rounded-md bg-background border border-border/50 text-[11px]"
              >
                <div className="flex items-center gap-2 truncate">
                  <span
                    className={cn(
                      'w-1.5 h-1.5 rounded-full shrink-0',
                      item.verified ? 'bg-emerald-500' : 'bg-muted-foreground'
                    )}
                  />
                  <span className="font-medium truncate">{item.title}</span>
                  <span className="px-1 py-0.2 rounded text-[9px] font-mono bg-muted text-muted-foreground uppercase">
                    {item.type}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {item.verified ? (
                    <span className="text-emerald-600 dark:text-emerald-400 flex items-center gap-0.5 text-[10px]">
                      <CheckCircle2 className="w-3 h-3" /> 已核验
                    </span>
                  ) : (
                    <span className="text-muted-foreground flex items-center gap-0.5 text-[10px]">
                      <Clock className="w-3 h-3" /> 待核验
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 上下文重置收益与 Token 经济学 (Token Economy) */}
        {(goal.contextTokensSaved !== undefined || goal.weeklyQuotaSavedPct !== undefined) && (
          <div
            data-testid="token-economy-banner"
            className="flex items-center gap-2.5 px-3 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-800 dark:text-emerald-300"
          >
            <Sparkles className="w-4 h-4 text-emerald-600 dark:text-emerald-400 shrink-0" />
            <div className="text-[11px]">
              <span className="font-medium">上下文隔离收益:</span> 拆分到新规划窗口重置了冗余上下文，已节省约{' '}
              <span className="font-semibold font-mono">
                {goal.contextTokensSaved?.toLocaleString() ?? 0}
              </span>{' '}
              Tokens
              {goal.weeklyQuotaSavedPct !== undefined && (
                <span> (周配额预计节省 {goal.weeklyQuotaSavedPct}%)</span>
              )}
              。
            </div>
          </div>
        )}

        {/* 下一轮规划草案（Window 2 产物） */}
        {goal.nextPlanDraft && (
          <div
            data-testid="next-plan-draft-card"
            className="p-3 rounded-lg bg-background border border-border/80 space-y-2"
          >
            <div className="flex items-center justify-between">
              <div className="font-medium text-foreground flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-amber-500" />
                下一迭代规划草案: {goal.nextPlanDraft.title}
              </div>
              {onDraftNextGoal && (
                <button
                  type="button"
                  data-testid="publish-draft-button"
                  disabled={isSubmitting || isLoading}
                  onClick={handlePublishDraft}
                  className="px-2 py-1 rounded bg-primary text-primary-foreground text-[10px] font-medium hover:bg-primary/90 transition-colors flex items-center gap-1"
                >
                  <ArrowRight className="w-3 h-3" />
                  起草下个会话 Goal
                </button>
              )}
            </div>
            <p className="text-[11px] text-muted-foreground">{goal.nextPlanDraft.summary}</p>
            {goal.nextPlanDraft.targetObjectives.length > 0 && (
              <div className="space-y-1">
                <div className="text-[10px] text-muted-foreground font-medium">规划核心目标:</div>
                <div className="flex flex-wrap gap-1.5">
                  {goal.nextPlanDraft.targetObjectives.map((obj, i) => (
                    <span
                      key={i}
                      className="px-1.5 py-0.5 rounded bg-muted text-muted-foreground text-[10px]"
                    >
                      • {obj}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 底部操作控制条 */}
      <div className="flex items-center justify-between px-4 py-2.5 border-t border-border/50 bg-muted/10">
        <div>
          {goal.phase !== 'completed' && goal.phase !== 'abandoned' && onAbandon && (
            <button
              type="button"
              data-testid="abandon-goal-button"
              disabled={isSubmitting || isLoading}
              onClick={handleAbandon}
              className="text-muted-foreground hover:text-destructive text-[11px] flex items-center gap-1 transition-colors"
            >
              <Ban className="w-3.5 h-3.5" />
              终止流转
            </button>
          )}
        </div>

        <div className="flex items-center gap-2">
          {nextPhase && onAdvanceStage && (
            <button
              type="button"
              data-testid="advance-stage-button"
              disabled={isSubmitting || isLoading}
              onClick={handleAdvance}
              className="px-3 py-1.5 rounded-lg bg-primary text-primary-foreground font-medium text-xs hover:bg-primary/90 transition-colors flex items-center gap-1.5 shadow-sm disabled:opacity-50"
            >
              {isSubmitting ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <ArrowRight className="w-3.5 h-3.5" />
              )}
              推进至: {getPhaseLabel(nextPhase)}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
