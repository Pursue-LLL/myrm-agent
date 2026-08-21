/**
 * [INPUT]
 * @/services/kanban::KanbanTask (POS: 看板任务数据模型)
 *
 * [OUTPUT]
 * - DecisionFrame: 决策帧结构化模型 (waitingEntity, recommendedActionKey, recommendedActionFallback, safetyTier, responsibility)
 * - deriveTaskDecisionFrame: 纯函数，根据任务状态与元数据推导首屏决策帧
 * - filterTasksByResponsibility: 根据责任矩阵 (All / Needs Human / Autonomous) 过滤任务
 *
 * [POS]
 * 看板首屏决策帧与责任矩阵逻辑层 (Item 27: KanbanDecisionFrameView)。
 * 零副作用纯函数，为 KanbanTaskCard 与 KanbanBoardView 提供统一的决策视图投影。
 */

import type { KanbanTask } from '@/services/kanban';

export type WaitingEntity = 'human' | 'agent' | 'system' | 'none';
export type SafetyTier = 'safe_auto' | 'hitl_guarded' | 'neutral';
export type ResponsibilityFilter = 'all' | 'needs_action' | 'autonomous';

export interface DecisionFrame {
  waitingEntity: WaitingEntity;
  recommendedActionKey: string;
  recommendedActionFallback: string;
  safetyTier: SafetyTier;
  responsibility: ResponsibilityFilter;
  hasAttention: boolean;
}

function hasKanbanCompletionIntent(metadata: Record<string, unknown> | null | undefined): boolean {
  if (!metadata) return false;
  return Boolean(
    metadata.completion_intent ??
    metadata.verification_requested ??
    metadata.requires_review
  );
}

/**
 * 纯函数：推导任务的首屏决策帧要素
 */
export function deriveTaskDecisionFrame(task: KanbanTask): DecisionFrame {
  const metadata = task.metadata || {};
  const requiresApproval = Boolean(task.require_approval || metadata.requires_approval);
  const isVerifying = task.status === 'running' && hasKanbanCompletionIntent(metadata);

  // 1. in_review 阶段：等待人工审查
  if (task.status === 'in_review') {
    return {
      waitingEntity: 'human',
      recommendedActionKey: 'decisionFrame.actionReview',
      recommendedActionFallback: 'Review verification & approve completion',
      safetyTier: 'hitl_guarded',
      responsibility: 'needs_action',
      hasAttention: true,
    };
  }

  // 2. blocked 阶段：阻塞，需用户介入或等待解锁
  if (task.status === 'blocked') {
    const isHumanBlock = task.block_kind === 'human' || requiresApproval;
    return {
      waitingEntity: isHumanBlock ? 'human' : 'system',
      recommendedActionKey: isHumanBlock ? 'decisionFrame.actionUnblockHuman' : 'decisionFrame.actionCheckBlock',
      recommendedActionFallback: isHumanBlock ? 'Resolve blocker / grant approval' : 'Waiting for dependency or schedule',
      safetyTier: isHumanBlock ? 'hitl_guarded' : 'neutral',
      responsibility: isHumanBlock ? 'needs_action' : 'autonomous',
      hasAttention: isHumanBlock,
    };
  }

  // 3. failed 阶段：失败，等待人工重试或排查
  if (task.status === 'failed') {
    return {
      waitingEntity: 'human',
      recommendedActionKey: 'decisionFrame.actionRetryOrDiagnose',
      recommendedActionFallback: 'Retry task or inspect failure diagnostic',
      safetyTier: 'hitl_guarded',
      responsibility: 'needs_action',
      hasAttention: true,
    };
  }

  // 4. triage 阶段：待分拣需求
  if (task.status === 'triage') {
    return {
      waitingEntity: 'human',
      recommendedActionKey: 'decisionFrame.actionSpecify',
      recommendedActionFallback: 'Specify criteria & move to ready',
      safetyTier: 'neutral',
      responsibility: 'needs_action',
      hasAttention: false,
    };
  }

  // 5. running 阶段：Agent 自主执行中
  if (task.status === 'running') {
    if (isVerifying) {
      return {
        waitingEntity: 'agent',
        recommendedActionKey: 'decisionFrame.actionVerifying',
        recommendedActionFallback: 'Agent verifying acceptance criteria',
        safetyTier: 'safe_auto',
        responsibility: 'autonomous',
        hasAttention: false,
      };
    }
    return {
      waitingEntity: 'agent',
      recommendedActionKey: 'decisionFrame.actionRunning',
      recommendedActionFallback: task.progress_note || 'Agent executing autonomous plan',
      safetyTier: requiresApproval ? 'hitl_guarded' : 'safe_auto',
      responsibility: 'autonomous',
      hasAttention: false,
    };
  }

  // 6. ready 阶段：等待调度器派发给 Agent
  if (task.status === 'ready') {
    return {
      waitingEntity: 'agent',
      recommendedActionKey: 'decisionFrame.actionDispatching',
      recommendedActionFallback: 'Queued for next available agent runner',
      safetyTier: requiresApproval ? 'hitl_guarded' : 'safe_auto',
      responsibility: 'autonomous',
      hasAttention: false,
    };
  }

  // 7. backlog 阶段：待办储备
  if (task.status === 'backlog') {
    return {
      waitingEntity: 'none',
      recommendedActionKey: 'decisionFrame.actionBacklog',
      recommendedActionFallback: 'Prioritize or schedule for execution',
      safetyTier: 'neutral',
      responsibility: 'autonomous',
      hasAttention: false,
    };
  }

  // 8. completed / archived
  return {
    waitingEntity: 'none',
    recommendedActionKey: 'decisionFrame.actionDone',
    recommendedActionFallback: 'Task completed successfully',
    safetyTier: 'safe_auto',
    responsibility: 'autonomous',
    hasAttention: false,
  };
}

/**
 * 根据责任过滤筛选任务列表
 */
export function filterTasksByResponsibility(
  tasks: KanbanTask[],
  filter: ResponsibilityFilter
): KanbanTask[] {
  if (filter === 'all') return tasks;
  return tasks.filter((task) => {
    const frame = deriveTaskDecisionFrame(task);
    return frame.responsibility === filter;
  });
}
