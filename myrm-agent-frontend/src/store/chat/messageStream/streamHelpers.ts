/**
 * [INPUT]
 * @/store/chat/types::Source, ProgressItem, ClarificationForm, GoalStatusPayload, ErrorKind (POS: Chat SSE types)
 * @/components/features/chat-window/goals/GoalStatusCard::GoalState (POS: Goal UI state)
 *
 * [OUTPUT]
 * Pure helpers: task step status, source merge, goal/clarification normalization, friendly errors
 *
 * [POS]
 * Shared utilities for messageStream/handlers/* event slices.
 */

import type {
  Source,
  ProgressItem,
  ClarificationForm,
  ClarificationOption,
  ClarificationQuestion,
  GoalStatusPayload,
  ErrorKind,
} from '@/store/chat/types';
import type { GoalState } from '@/components/features/chat-window/goals/GoalStatusCard';
import type { SubagentStatus } from '../useSubagentStore';

const SUBAGENT_STATUSES = new Set<SubagentStatus>([
  'running',
  'completed',
  'failed',
  'cancelled',
  'timed_out',
  'checkpoint',
]);

export function mapTaskStepStatus(status: string | undefined): ProgressItem['status'] | undefined {
  switch (status) {
    case 'completed':
      return 'success';
    case 'partial_success':
      return 'warning';
    case 'error':
      return 'error';
    case 'cancelled':
      return 'cancelled';
    default:
      return undefined;
  }
}

export function normalizeGoalState(payload: GoalStatusPayload): GoalState {
  return {
    goalId: payload.goal_id,
    objective: payload.objective,
    uiSummary: payload.ui_summary,
    status: payload.status,
    tokensUsed: payload.tokens_used,
    timeUsedSeconds: payload.time_used_seconds,
    costUsd: payload.cost_usd,
    turnsUsed: payload.turns_used,
    noProgressStreak: payload.no_progress_streak,
    loopRestarts: payload.loop_restarts,
    budget: payload.budget
      ? {
          maxTokens: payload.budget.max_tokens,
          maxUsd: payload.budget.max_usd,
          maxTimeSeconds: payload.budget.max_time_seconds,
          maxTurns: payload.budget.max_turns,
          convergenceWindow: payload.budget.convergence_window,
          loopOnPause: payload.budget.loop_on_pause,
          maxLoopRestarts: payload.budget.max_loop_restarts,
        }
      : undefined,
    verdict: payload.verdict,
    reason: payload.reason,
    constraints: payload.constraints,
    acceptanceCriteria: payload.acceptance_criteria,
    subgoals: payload.subgoals,
    executionSummary: payload.metadata?.execution_summary,
  };
}

function getSourceKey(source: Source): string {
  if (source.source_key) return source.source_key;
  if (source.type === 'conversation_history' && source.conversation_id) {
    return `conversation:${source.conversation_id}:${source.message_id ?? ''}`;
  }
  if (source.url) return `url:${source.url}`;
  if (source.skill_name) return `mcp:${source.skill_name}`;
  return `index:${source.index}`;
}

export function mergeMessageSources(existingSources: Source[], incomingSources: Source[]): Source[] {
  const mergedSources = [...existingSources];
  const usedIndexes = new Set(mergedSources.map((source) => source.index));
  let maxIndex = Math.max(0, ...mergedSources.map((source) => source.index));

  for (const incoming of incomingSources) {
    const sourceKey = getSourceKey(incoming);
    const existingIndex = mergedSources.findIndex((source) => getSourceKey(source) === sourceKey);
    if (existingIndex !== -1) {
      mergedSources[existingIndex] = {
        ...mergedSources[existingIndex],
        ...incoming,
        index: mergedSources[existingIndex].index,
      };
      continue;
    }

    const nextSource = { ...incoming };
    if (usedIndexes.has(nextSource.index)) {
      maxIndex += 1;
      nextSource.index = maxIndex;
    }
    usedIndexes.add(nextSource.index);
    maxIndex = Math.max(maxIndex, nextSource.index);
    mergedSources.push(nextSource);
  }

  return mergedSources.sort((a, b) => a.index - b.index);
}

export function normalizeSubagentStatus(status: string | undefined): SubagentStatus {
  if (status && SUBAGENT_STATUSES.has(status as SubagentStatus)) {
    return status as SubagentStatus;
  }
  return 'completed';
}

export function getContextOverflowMessage(): string {
  const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
  return lang?.startsWith('zh')
    ? '对话已超出模型上下文限制，当前消息未发送。请开始新对话。'
    : 'Context limit exceeded. Message not sent. Please start a new conversation.';
}

interface FriendlyError {
  message: string;
  hint?: string;
}

export async function getUserFriendlyError(
  _errorKind: ErrorKind | undefined,
  rawError: string,
  _cooldownMs?: number,
): Promise<FriendlyError> {
  return { message: rawError };
}

export function normalizeClarificationForm(value: unknown): ClarificationForm | undefined {
  if (!value || typeof value !== 'object') return undefined;

  const rawForm = value as Record<string, unknown>;
  const title = typeof rawForm.title === 'string' && rawForm.title.trim() ? rawForm.title.trim() : undefined;
  const rawQuestions = Array.isArray(rawForm.questions) ? rawForm.questions : [];
  const questions: ClarificationQuestion[] = [];

  for (const rawQuestionValue of rawQuestions) {
    if (!rawQuestionValue || typeof rawQuestionValue !== 'object') continue;
    const rawQuestion = rawQuestionValue as Record<string, unknown>;
    const id = typeof rawQuestion.id === 'string' ? rawQuestion.id.trim() : '';
    const prompt = typeof rawQuestion.prompt === 'string' ? rawQuestion.prompt.trim() : '';
    if (!id || !prompt) continue;

    const question: ClarificationQuestion = { id, prompt };
    if (typeof rawQuestion.allow_multiple === 'boolean') {
      question.allowMultiple = rawQuestion.allow_multiple;
    }

    if (Array.isArray(rawQuestion.options)) {
      const options: ClarificationOption[] = [];
      for (const rawOptionValue of rawQuestion.options) {
        if (!rawOptionValue || typeof rawOptionValue !== 'object') continue;
        const rawOption = rawOptionValue as Record<string, unknown>;
        const optionId = typeof rawOption.id === 'string' ? rawOption.id.trim() : '';
        const label = typeof rawOption.label === 'string' ? rawOption.label.trim() : '';
        if (!optionId || !label) continue;

        const option: ClarificationOption = { id: optionId, label };
        if (typeof rawOption.description === 'string' && rawOption.description.trim()) {
          option.description = rawOption.description.trim();
        }
        options.push(option);
      }
      if (options.length > 0) {
        question.options = options;
      }
    }

    questions.push(question);
  }

  if (questions.length === 0) return undefined;
  return {
    ...(title ? { title } : {}),
    questions,
  };
}
