/**
 * [INPUT]
 * @/store/chat/types::AgentStreamEvent, ClarificationForm (POS: Chat state and SSE event type definitions)
 * ./archiveRestoreActions (POS: Typed archive restore action utility layer. Keeps parsing, normalization and send-time matching outside the chat stream reducer and input hook.)
 * ./memoryCitationUtils (POS: Chat memory citation normalization helpers)
 * ./adaptiveScheduler::AdaptiveScheduler (POS: Streaming UI update scheduler)
 *
 * [OUTPUT]
 * handleMessageStream: merges Agent SSE events into chat Message state (including synthetic
 * progressSteps rows for orphaned file_diff when TASKS_STEPS lacked a matching file_path);
 * FILE_DIFF 合并使用统一的 `ProgressFileItem` 形状（含可选 `diff_truncated`）；若当前 messageId
 * 尚无 assistant 行则插入占位 assistant，避免在「尾部 user 消息」场景下把 diff 误并入上一轮；
 * 对同一 file_path 的连续 FILE_DIFF 取「更丰富」的 unified diff（+/- 优于仅 +），避免弱 hunks 覆盖 str_replace。
 *
 * [POS]
 * Chat stream reducer. It translates runtime events into user-visible message content,
 * progress, tool output, citations, artifacts, routing metadata and completion state.
 */

import {
  Source,
  Message,
  File,
  ToolApprovalRequest,
  AgentEventType,
  AgentStreamEvent,
  type ClarificationForm,
  type ClarificationOption,
  type ClarificationQuestion,
  type Artifact,
  type ArtifactType,
  type ErrorKind,
  type GoalStatusPayload,
  type ProgressItem,
  type UIArtifact,
} from '@/store/chat/types';
import {
  buildArchiveRestoreActions,
  parseArchiveRestoreBlockPayload,
  parseArchiveRestoreResultPayload,
} from './archiveRestoreActions';
import { findAssistantMessageIndex } from './messageUtils';
import {
  isMemoryRecallToolName,
  mergeCitedMemoryReferences,
  normalizeCitedMemoryReferences,
} from './memoryCitationUtils';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import useToolsSnapshotStore from '@/store/useToolsSnapshotStore';
import useChatStore from '@/store/useChatStore';
import { AdaptiveScheduler } from './adaptiveScheduler';
import { playCompletionSound } from '@/lib/utils/completionSound';
import useConfigStore from '@/store/useConfigStore';
import type { SubagentStatus } from './useSubagentStore';
import type { GoalState } from '@/components/features/chat-window/goals/GoalStatusCard';

/** progressSteps file row mutated when merging FILE_DIFF */
type ProgressFileItem = {
  file_path: string;
  line_range?: string;
  action_type?: string;
  size_bytes?: string;
  diff?: string;
  diff_truncated?: boolean;
};

// eslint-disable-next-line no-control-regex
const UNICODE_CONTROL_RE = /[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F\uFFFD]/g;

const SUBAGENT_STATUSES = new Set<SubagentStatus>([
  'running',
  'completed',
  'failed',
  'cancelled',
  'timed_out',
  'checkpoint',
]);

function mapTaskStepStatus(status: string | undefined): ProgressItem['status'] | undefined {
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

function parseProgressFilePath(item: unknown): string | undefined {
  if (!item || typeof item !== 'object' || !('file_path' in item)) return undefined;
  const fp = (item as { file_path?: unknown }).file_path;
  return typeof fp === 'string' ? fp : undefined;
}

function pathsMatchForFileDiff(diffPath: string, itemPath: string): boolean {
  return itemPath === diffPath || diffPath.endsWith(itemPath) || itemPath.endsWith(diffPath);
}

/** Prefer richer unified diffs when merging FILE_DIFF bursts (weak “from /dev/null” must not overwrite str_replace). */
function scoreUnifiedDiffForMerge(diff: string): number {
  let hasMinus = false;
  let hasPlus = false;
  for (const line of diff.split('\n')) {
    if (line.startsWith('-') && !line.startsWith('---')) hasMinus = true;
    if (line.startsWith('+') && !line.startsWith('+++')) hasPlus = true;
  }
  let score = 0;
  if (hasMinus && hasPlus) score += 100;
  else if (hasMinus || hasPlus) score += 10;
  if (diff.includes('@@')) score += 5;
  score += Math.min(diff.length, 500_000) / 50_000;
  return score;
}

function diffHasMinusAndPlusLinesMerge(diff: string): boolean {
  let hasMinus = false;
  let hasPlus = false;
  for (const line of diff.split('\n')) {
    if (line.startsWith('-') && !line.startsWith('---')) hasMinus = true;
    if (line.startsWith('+') && !line.startsWith('+++')) hasPlus = true;
    if (hasMinus && hasPlus) return true;
  }
  return false;
}

function pickMergedFileDiffPayload(
  current: { diff?: string; diff_truncated?: boolean },
  incomingDiff: string,
  incomingTruncated: boolean,
): { diff: string; diff_truncated: boolean } {
  const cur = current.diff;
  if (!cur) {
    return { diff: incomingDiff, diff_truncated: incomingTruncated };
  }
  const sc = scoreUnifiedDiffForMerge(cur);
  const si = scoreUnifiedDiffForMerge(incomingDiff);
  if (si > sc) {
    return { diff: incomingDiff, diff_truncated: incomingTruncated };
  }
  if (sc > si) {
    return { diff: cur, diff_truncated: Boolean(current.diff_truncated) };
  }
  const cm = diffHasMinusAndPlusLinesMerge(cur);
  const im = diffHasMinusAndPlusLinesMerge(incomingDiff);
  if (im && !cm) {
    return { diff: incomingDiff, diff_truncated: incomingTruncated };
  }
  if (cm && !im) {
    return { diff: cur, diff_truncated: Boolean(current.diff_truncated) };
  }
  return incomingDiff.length >= cur.length
    ? { diff: incomingDiff, diff_truncated: incomingTruncated }
    : { diff: cur, diff_truncated: Boolean(current.diff_truncated) };
}

function normalizeGoalState(payload: GoalStatusPayload): GoalState {
  return {
    goalId: payload.goal_id,
    objective: payload.objective,
    uiSummary: payload.ui_summary,
    status: payload.status,
    tokensUsed: payload.tokens_used,
    timeUsedSeconds: payload.time_used_seconds,
    costUsd: payload.cost_usd,
    turnsUsed: payload.turns_used,
    budget: payload.budget
      ? {
          maxTokens: payload.budget.max_tokens,
          maxUsd: payload.budget.max_usd,
          maxTimeSeconds: payload.budget.max_time_seconds,
          maxTurns: payload.budget.max_turns,
        }
      : undefined,
    verdict: payload.verdict,
    reason: payload.reason,
    constraints: payload.constraints,
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

function mergeMessageSources(existingSources: Source[], incomingSources: Source[]): Source[] {
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

function normalizeSubagentStatus(status: string | undefined): SubagentStatus {
  if (status && SUBAGENT_STATUSES.has(status as SubagentStatus)) {
    return status as SubagentStatus;
  }
  return 'completed';
}

function getContextOverflowMessage(): string {
  const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
  return lang?.startsWith('zh')
    ? '对话已超出模型上下文限制，当前消息未发送。请开始新对话。'
    : 'Context limit exceeded. Message not sent. Please start a new conversation.';
}

interface FriendlyError {
  message: string;
  hint?: string;
}

async function getUserFriendlyError(
  errorKind: ErrorKind | undefined,
  rawError: string,
  _cooldownMs?: number,
): Promise<FriendlyError> {
  // The backend now translates errors and sends localized text directly in `rawError`.
  // We no longer need client-side translation mapping.
  return { message: rawError };
}

function normalizeClarificationForm(value: unknown): ClarificationForm | undefined {
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

export interface StreamMutableState {
  messages: Message[];
  messageAppeared: boolean;
  loading: boolean;
}

export interface StreamHandlerState extends StreamMutableState {
  scheduler: AdaptiveScheduler;
}

export interface StreamHandlerActions {
  setMessages: (updater: (state: StreamMutableState) => void) => void;
  setMessageAppeared: (appeared: boolean) => void;
  setLoading: (loading: boolean) => void;
  _processSuggestions: (lastMsg: Message) => Promise<void>;
  scheduleAutoSave: () => void;
}

/**
 * 处理流式消息数据
 */
export const handleMessageStream = async (
  data: AgentStreamEvent,
  input: string,
  sources: Source[] | undefined,
  added: boolean,
  recievedMessage: string,
  state: StreamHandlerState,
  actions: StreamHandlerActions,
  _files: File[] = [],
): Promise<{
  added: boolean;
  recievedMessage: string;
}> => {
  // Co-located Mascot state stream synchronization
  if (data && typeof data === 'object' && 'mascot_status' in data && typeof data.mascot_status === 'string') {
    try {
      const companionStore = (await import('@/store/useCompanionStore')).default;
      companionStore.getState().setMascotStatus(data.mascot_status);
    } catch {
      // safe fallback
    }
  }

  // Handle Mascot XP updates
  if (data.type === 'mascot_xp_update') {
    try {
      const companionStore = (await import('@/store/useCompanionStore')).default;
      companionStore.getState().setMascotXpState(data.data);
    } catch {
      // safe fallback
    }
    return { added, recievedMessage };
  }

  // Handle DAG state updates
  if (data.type === 'dag_state_update') {
    try {
      const companionStore = (await import('@/store/useCompanionStore')).default;
      companionStore.getState().setDagData(data.data as Record<string, unknown> | null);
    } catch {
      // safe fallback
    }
    return { added, recievedMessage };
  }

  if (data.type === 'catchup_snapshot') {
    const snap = data.data;
    actions.setMessages((state) => {
      const msgIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (msgIndex !== -1) {
        const msg = state.messages[msgIndex];
        msg.content = snap.content || '';
        msg.thinkingItems = snap.reasoning ? [snap.reasoning] : [];
        msg.progressSteps = snap.progress_steps || [];
        msg.sources = snap.sources || [];
      }
    });
    return { added, recievedMessage: snap.content || '' };
  }

  if (data.type === 'rate_limit_updated') {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('rate_limit_updated'));
    }
    return { added, recievedMessage };
  }

  if (data.type === 'rate_limit_warning') {
    const payload = data.data as { provider: string; model: string; usage_pct: number };
    if (payload) {
      const pct = Math.round(payload.usage_pct * 100);
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const toastMessage = lang?.startsWith('zh')
        ? `${payload.provider} (${payload.model}) 速率限制已达 ${pct}%。Agent 可能会放缓速度。`
        : `Rate limit usage for ${payload.provider} (${payload.model}) is at ${pct}%. Agent may slow down.`;

      import('@/lib/utils/toast').then(({ toast }) => {
        toast.warning(toastMessage, { duration: 8000 });
      });

      if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('rate_limit_updated'));
      }
    }
    return { added, recievedMessage };
  }

  if (data.type === 'rate_limit_throttled') {
    const payload = data.data as { wait_seconds: number };
    if (payload) {
      const waitSec = Math.round(payload.wait_seconds);
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const toastMessage = lang?.startsWith('zh')
        ? `所有 API 配额已耗尽，正在等待恢复（约 ${waitSec} 秒）...`
        : `All API quotas exhausted, waiting for recovery (~${waitSec}s)...`;

      import('@/lib/utils/toast').then(({ toast }) => {
        toast.info(toastMessage, { duration: Math.min(waitSec * 1000, 30000) });
      });
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.ERROR) {
    let errorText: string;
    let hint: string | undefined;

    // Prioritize backend diagnostic_result (i18n + resolution steps)
    if (data.diagnostic_result) {
      const diagnostic = data.diagnostic_result;
      errorText = diagnostic.user_message;

      // Format resolution steps
      if (diagnostic.resolution_steps.length > 0) {
        const stepsText = diagnostic.resolution_steps.map((step, i) => `${i + 1}. ${step}`).join('\n');
        hint = stepsText;
      }
    } else {
      // Use frontend translation when backend sends an untranslated error token.
      const rawError = data.error || data.data || 'Unknown error';
      const friendlyError = await getUserFriendlyError(data.error_kind, rawError, data.cooldown_remaining_ms);
      errorText = friendlyError.message;
      hint = friendlyError.hint;
    }

    actions.setMessages((state) => {
      const errorStep = {
        step_key: 'processing_failed',
        items: [{ text: errorText }],
        error: hint || (true as boolean | string),
        recovery_actions: data.recovery_actions,
      };
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        state.messages[messageIndex].progressSteps!.push(errorStep);
      } else {
        state.messages.push({
          content: '',
          messageId: data.messageId,
          chatId: state.messages[0]?.chatId || '',
          role: 'assistant',
          progressSteps: [errorStep],
          createdAt: new Date(),
          metadata: data.metadata,
        });
        added = true;
      }
    });

    if (data.retry_after_ms || data.cooldown_remaining_ms) {
      const retryAfterMs = data.retry_after_ms || data.cooldown_remaining_ms;
      const retryAfterSeconds = Math.ceil(retryAfterMs / 1000);
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const toastMessage = lang?.startsWith('zh')
        ? `已达到速率限制。请在 ${retryAfterSeconds} 秒后重试。`
        : `Rate limit exceeded. Please retry after ${retryAfterSeconds} seconds.`;

      import('@/lib/utils/toast').then(({ toast }) => {
        toast.error(toastMessage, { duration: Math.min(retryAfterMs, 10000) });
      });
    }

    actions.setLoading(false);
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.AGENT_CANCELLED) {
    const reason = data.data?.reason || 'user_cancelled';
    const cancelText = reason === 'user_cancelled' ? '已取消' : '已终止';

    actions.setMessages((state) => {
      const cancelStep = {
        step_key: 'agent_cancelled',
        items: [{ text: cancelText }],
        status: 'cancelled' as const,
      };
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        state.messages[messageIndex].progressSteps!.push(cancelStep);
      }
    });
    actions.setLoading(false);
    // Release the processing lock on cancellation
    useToolApprovalStore.getState().unmarkProcessing(data.messageId);
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.STEERING) {
    const steerData = data.data as { count?: number; messages?: string[] } | string | undefined;
    let steerText = 'Steering applied';
    if (typeof steerData === 'object' && steerData?.messages?.length) {
      const preview = steerData.messages[0].slice(0, 80);
      const suffix = steerData.messages[0].length > 80 || steerData.messages.length > 1 ? '...' : '';
      steerText = `Steering: "${preview}${suffix}"`;
    }
    actions.setMessages((state) => {
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        state.messages[messageIndex].progressSteps!.push({
          step_key: 'steering_applied',
          items: [{ text: steerText }],
          status: 'success' as const,
        });
      }
    });
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.ITERATION_LIMIT_REACHED) {
    const limitData = data.data as { limit?: number; nodes_completed?: number } | undefined;
    const limit = limitData?.limit ?? '?';
    const nodes = limitData?.nodes_completed ?? '?';

    actions.setMessages((state) => {
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        state.messages[messageIndex].progressSteps!.push({
          step_key: 'iteration_limit_reached',
          items: [{ text: `${limit} iterations / ${nodes} nodes` }],
          status: 'warning' as const,
        });
      }
    });
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.CONTEXT_OVERFLOW_RESET) {
    const { toast } = await import('@/lib/utils/toast');
    toast.warning(getContextOverflowMessage(), { duration: 8000 });
    useChatStore.getState().initializeChat(undefined);
    actions.setLoading(false);
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.TOOL_FALLBACK) {
    actions.setMessages((state) => {
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        state.messages[messageIndex].progressSteps!.push({
          step_key: 'safety_fallback_active',
          tool_name: null,
          status: 'warning',
          items: [{ text: data.message }],
        });
      }
    });
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.CONTEXT_REFERENCE_WARNING) {
    const { toast } = await import('@/lib/utils/toast');
    const warningMessage = data.data?.message || 'Context reference warning';
    toast.warning(warningMessage, { duration: 6000 });
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.PTC_NOTIFY) {
    const payload = (data.data as Record<string, unknown> | undefined) ?? (data as unknown as Record<string, unknown>);
    const readField = <T>(name: string): T | undefined => {
      const fromPayload = payload ? (payload[name] as T | undefined) : undefined;
      if (fromPayload !== undefined && fromPayload !== null) {
        return fromPayload;
      }
      return (data as unknown as Record<string, T | undefined>)[name];
    };

    const message = readField<string>('message');
    const level = readField<'info' | 'warn' | 'alert'>('level') ?? 'info';
    const progress = readField<number>('progress');
    const stepIndex = readField<number>('step_index');
    const totalSteps = readField<number>('total_steps');
    const category = readField<string>('category');
    const errorCategory = readField<string>('error_category');

    if (!message) {
      return { added, recievedMessage };
    }

    // Inline activity: merge by category (or fallback bucket) into a single
    // progressSteps entry so 100x notify calls render as a single live card
    // with progress bar instead of stacking toasts.
    const stepKey = `ptc_notify:${category ?? 'default'}`;
    actions.setMessages((state) => {
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex === -1) {
        return;
      }
      const message_ = state.messages[messageIndex];
      if (!message_.progressSteps) {
        message_.progressSteps = [];
      }
      const existing = message_.progressSteps.find((s) => s.step_key === stepKey);
      const status: ProgressItem['status'] = level === 'alert' ? 'error' : level === 'warn' ? 'warning' : 'success';
      const reason = stepIndex !== undefined && totalSteps !== undefined ? `${stepIndex} / ${totalSteps}` : undefined;
      const patch: Partial<ProgressItem> = {
        step_key: stepKey,
        notify_message: message,
        notify_level: level,
        status,
      };
      if (progress !== undefined) {
        patch.notify_progress = progress;
        // Drive the existing ProgressSteps progress bar UI by mirroring into
        // the canonical ``progress_percent`` field; ensures pixel-perfect
        // reuse of theme colours and animations.
        patch.progress_percent = progress;
      }
      if (stepIndex !== undefined) {
        patch.notify_step_index = stepIndex;
      }
      if (totalSteps !== undefined) {
        patch.notify_total_steps = totalSteps;
      }
      if (category !== undefined) {
        patch.notify_category = category;
      }
      if (errorCategory !== undefined) {
        // Drive the destructive Badge in ProgressSteps; the harness emits
        // ``oom_killed`` / ``segfault`` / ``signal_terminated`` / ``nonzero_exit``
        // for background process exits so the user immediately sees *why* a
        // long-running task died.
        patch.error_category = errorCategory;
      }
      if (reason !== undefined) {
        patch.reason = reason;
      }
      if (existing) {
        Object.assign(existing, patch);
      } else {
        message_.progressSteps.push(patch as ProgressItem);
      }
    });

    // Loud levels also surface a transient toast so a critical signal is
    // not missed when the user is scrolled away from the activity card.
    if (level === 'alert' || level === 'warn') {
      const { toast } = await import('@/lib/utils/toast');
      if (level === 'alert') {
        toast.error(message, { duration: 8000 });
      } else {
        toast.warning(message, { duration: 6000 });
      }
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.TOOL_PROGRESS) {
    const { tool, progress } = data as { tool: string; progress: { done: number; total: number; failed: number } };
    if (progress && added) {
      const stepKey = `tool_progress:${tool}`;
      const pct = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;
      actions.setMessages((state) => {
        const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex === -1) return;
        const msg = state.messages[messageIndex];
        if (!msg.progressSteps) {
          msg.progressSteps = [];
        }
        const existing = msg.progressSteps.find((s) => s.step_key === stepKey);
        const status: ProgressItem['status'] = progress.failed > 0 ? 'warning' : 'success';
        const patch: Partial<ProgressItem> = {
          step_key: stepKey,
          tool_name: tool,
          progress_percent: pct,
          notify_progress: pct,
          notify_step_index: progress.done,
          notify_total_steps: progress.total,
          reason: `${progress.done}/${progress.total}${progress.failed ? ` (${progress.failed} failed)` : ''}`,
          status,
        };
        if (existing) {
          Object.assign(existing, patch);
        } else {
          msg.progressSteps.push(patch as ProgressItem);
        }
      });
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.TOOL_HEARTBEAT) {
    if (added) {
      actions.setMessages((state) => {
        const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex !== -1 && state.messages[messageIndex].progressSteps) {
          const steps = state.messages[messageIndex].progressSteps!;
          // Find the step that matches this tool_call_id
          const stepIndex = steps.findIndex((step) => step.tool_call_id === data.tool_call_id);
          if (stepIndex !== -1) {
            steps[stepIndex] = {
              ...steps[stepIndex],
              elapsed_ms: data.elapsed_ms,
            };
          }
        }
      });
    }
  }

  if (data.type === AgentEventType.TASKS_STEPS) {
    // 构建步骤对象（使用新的 step_key 结构）
    const stepStatus = mapTaskStepStatus(data.status);
    const stepItem = {
      step_key: data.step_key,
      parent_step_key: data.parent_step_key,
      is_plan: data.is_plan,
      tool_name: data.tool_name,
      tool_call_id: data.tool_call_id,
      agent_instance: data.agent_instance,
      display_name: data.display_name,
      theme_color: data.theme_color,
      items: data.data,
      count: data.count,
      status: stepStatus,
      error: data.status === 'error' ? data.error : undefined,
      error_category: data.error_category,
      error_hint: data.error_hint,
      recovery_actions: data.recovery_actions,
      progress_percent: data.progress_percent,
    };

    if (data.error_category) {
      useChatStore.getState().addEnvironmentAlert(data.error_category);
    }

    if (data.step_key === 'swarm_fission') {
      import('@/store/chat/useSubagentStore').then(({ useSubagentStore }) => {
        const total = typeof data.count === 'number' ? data.count : 0;
        const status = data.status;
        const failedCount = typeof data.failed_count === 'number' ? data.failed_count : status === 'error' ? total : 0;
        const completedCount =
          typeof data.completed_count === 'number' ? data.completed_count : Math.max(0, total - failedCount);
        const partial =
          Boolean(data.partial_success) || status === 'partial_success' || (failedCount > 0 && completedCount > 0);

        if (status === 'running') {
          useSubagentStore.getState().setFissionBatch({
            active: true,
            total,
            completed: 0,
            failed: 0,
            partial: false,
          });
        } else if (status === 'completed' || status === 'error' || status === 'partial_success') {
          useSubagentStore.getState().setFissionBatch({
            active: false,
            total,
            completed: completedCount,
            failed: failedCount,
            partial,
          });

          if (failedCount > 0) {
            import('@/lib/utils/toast').then(({ toast }) => {
              const lang = typeof document !== 'undefined' ? document.documentElement.lang || 'en' : 'en';
              const message = lang.startsWith('zh')
                ? `并行裂变：${completedCount}/${total} 成功，${failedCount} 路失败`
                : `Swarm fission: ${completedCount}/${total} succeeded, ${failedCount} failed`;
              toast.warning(message, { duration: 8000 });
            });
          }
        }
      });
    }

    if (!added) {
      actions.setMessages((state) => {
        state.messages.push({
          content: '',
          messageId: data.messageId,
          chatId: state.messages[0]?.chatId || '',
          role: 'assistant',
          progressSteps: [stepItem],
          createdAt: new Date(),
          metadata: data.metadata,
        });
      });
      added = true;
    } else {
      actions.setMessages((state) => {
        const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex !== -1) {
          // 如果消息存在但没有progressSteps，则初始化一个空数组
          if (!state.messages[messageIndex].progressSteps) {
            state.messages[messageIndex].progressSteps = [];
          }
          state.messages[messageIndex].progressSteps!.push(stepItem);
        } else {
          console.warn('Could not find assistant message with messageId:', data.messageId);
        }
      });
    }
  }

  if (data.type === AgentEventType.SOURCES) {
    const newSources = data.data;

    actions.setMessages((state) => {
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex === -1) {
        return;
      }

      const existingSources = state.messages[messageIndex].sources || [];
      state.messages[messageIndex].sources = mergeMessageSources(existingSources, newSources);

      if (!state.messageAppeared) {
        state.messageAppeared = true;
      }
    });
  }

  if (data.type === AgentEventType.APPROVAL_REQUIRED) {
    const payload = data.data as { type: string; message?: string };
    const cancelText = payload?.message || '任务已暂停：需要人工介入 (Task paused for human intervention)';

    actions.setMessages((state) => {
      const cancelStep = {
        step_key: 'approval_required',
        items: [{ text: cancelText }],
        status: 'error' as const,
      };
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        state.messages[messageIndex].progressSteps!.push(cancelStep);
      }
    });
    actions.setLoading(false);
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.CLARIFICATION_REQUIRED) {
    const form = data.data as ClarificationForm;
    actions.setMessages((state) => {
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        state.messages[messageIndex].clarification = {
          answered: false,
          isResumeMode: true,
          title: form?.title ?? undefined,
          form: form,
        };
      } else {
        state.messages.push({
          content: '',
          messageId: data.messageId,
          chatId: state.messages[0]?.chatId || '',
          role: 'assistant',
          createdAt: new Date(),
          clarification: {
            answered: false,
            isResumeMode: true,
            title: form?.title ?? undefined,
            form: form,
          },
        });
        added = true;
      }
    });
    actions.setLoading(false);
    return { added, recievedMessage };
  }

  // 处理 tool_approval_request 事件：弹出审批对话框
  if (data.type === AgentEventType.TOOL_APPROVAL_REQUEST) {
    const payload = data.data;

    // 从 useChatStore 获取当前上下文（用于 resume 请求）
    const { chatId: currentChatId, actionMode: currentActionMode } = (
      await import('@/store/useChatStore')
    ).default.getState();

    // Parse standard LangChain HITL payload structure (supports batch approval)
    const { actionRequests, reviewConfigs, extensions } = payload;
    const isBatch = actionRequests.length > 1;
    const batchId = isBatch ? extensions.approval.requestId : null;

    // Create approval requests for all actions in the batch
    for (let i = 0; i < actionRequests.length; i++) {
      const action = actionRequests[i];
      const reviewConfig = reviewConfigs?.[i];
      const requestId = isBatch ? `${batchId}_${i}` : extensions.approval.requestId;

      const approvalRequest: ToolApprovalRequest = {
        requestId,
        toolName: action.action,
        toolInput: action.args,
        reason: action.description,
        timeoutSeconds: extensions.timeout.seconds,
        expiresAt: extensions.timeout.expiresAt,
        timeoutBehavior: extensions.timeout.behavior || 'deny',
        messageId: data.messageId,
        displayMode: extensions.displayMode,
        batchId: batchId || undefined,
        batchIndex: isBatch ? i : undefined,
        batchSize: isBatch ? actionRequests.length : undefined,
        chatId: currentChatId!,
        actionMode: currentActionMode,
        domains: Array.isArray(action.domains) ? action.domains : undefined,
        domainApproval: reviewConfig?.domainApproval === true ? true : undefined,
        ptcAnnotations: action.ptc_annotations,
      };
      useToolApprovalStore.getState().addRequest(approvalRequest);
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.APPROVAL_PROCESSED) {
    // When approval is processed (e.g. via text interception), remove the request from the queue
    useToolApprovalStore.getState().removeRequestsByMessageId(data.messageId);
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.TOOLS_SNAPSHOT) {
    useToolsSnapshotStore.getState().setTools(data.data);
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.STATUS) {
    const stepKey = data.step_key;
    if (
      stepKey === 'model_failover' ||
      stepKey === 'context_compaction' ||
      stepKey === 'context_truncation' ||
      stepKey === 'safety_fallback_active' ||
      stepKey === 'memory_archived' ||
      stepKey === 'context_pruned' ||
      stepKey === 'archive_checkpoint' ||
      stepKey === 'archive_restore_blocked' ||
      stepKey === 'archive_restore_result' ||
      stepKey === 'thinking_budget_exhausted' ||
      stepKey === 'tool_call_truncated' ||
      stepKey === 'text_continuation' ||
      stepKey === 'text_continuation_exhausted' ||
      stepKey === 'transient_retry' ||
      stepKey === 'analyzing_image' ||
      stepKey === 'analyzing_video' ||
      stepKey === 'media_stripped' ||
      stepKey === 'media_rejected_recovery' ||
      stepKey === 'ux_warning_truncated' ||
      stepKey === 'consensus_active' ||
      stepKey === 'consensus_reference_done'
    ) {
      const displayKey =
        stepKey === 'model_failover' && data.error_kind ? `model_failover_${data.error_kind}` : stepKey;
      const isMediaAnalysis = stepKey === 'analyzing_image' || stepKey === 'analyzing_video';
      const isArchiveRestoreStatus = stepKey === 'archive_restore_blocked' || stepKey === 'archive_restore_result';
      const archiveRestoreBlock =
        stepKey === 'archive_restore_blocked'
          ? parseArchiveRestoreBlockPayload(data.data?.archive_restore_block)
          : undefined;
      const archiveRestoreResult =
        stepKey === 'archive_restore_result'
          ? parseArchiveRestoreResultPayload(data.data?.archive_restore_result)
          : undefined;
      const archiveRestoreActions = buildArchiveRestoreActions(archiveRestoreBlock);
      const itemText =
        (stepKey === 'model_failover' || stepKey === 'safety_fallback_active') && data.fallback_model
          ? data.fallback_model
          : (stepKey === 'memory_archived' || stepKey === 'context_pruned') && data.tokens_saved
            ? `(Tokens saved: ${data.tokens_saved})`
            : stepKey === 'archive_checkpoint' && data.tool_name
              ? `(${data.tool_name})`
              : stepKey === 'media_stripped' && data.stripped_count
                ? `(${data.stripped_count})`
                : stepKey === 'transient_retry' && data.attempt
                  ? `(${data.attempt}/15)`
                  : stepKey === 'consensus_active' && data.data?.reference_models
                    ? `(${(data.data.reference_models as string[]).join(', ')})`
                    : stepKey === 'consensus_reference_done' && data.data?.model
                      ? `${data.data.model} (${data.data.success ? '✓' : '✗'} ${typeof data.data.elapsed === 'number' ? `${data.data.elapsed.toFixed(1)}s` : ''})`
                      : '';
      actions.setMessages((state) => {
        let messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex === -1 && (isMediaAnalysis || isArchiveRestoreStatus)) {
          state.messages.push({
            content: '',
            messageId: data.messageId,
            chatId: state.messages[0]?.chatId || '',
            role: 'assistant',
            progressSteps: [],
            mediaAnalysisStatus: isMediaAnalysis ? (stepKey as 'analyzing_image' | 'analyzing_video') : null,
            createdAt: new Date(),
            metadata: data.metadata,
          });
          messageIndex = state.messages.length - 1;
          added = true;
        }

        if (messageIndex !== -1) {
          if (!state.messages[messageIndex].progressSteps) {
            state.messages[messageIndex].progressSteps = [];
          }
          const progressStep: ProgressItem = {
            step_key: displayKey,
            items: data.items ?? (itemText ? [{ text: itemText }] : []),
            tool_name: stepKey === 'archive_checkpoint' ? undefined : (data.tool_name ?? undefined),
            status: data.status,
          };
          if (archiveRestoreBlock) {
            progressStep.archive_restore_block = archiveRestoreBlock;
          }
          if (archiveRestoreActions.length > 0) {
            progressStep.archive_restore_actions = archiveRestoreActions;
          }
          if (archiveRestoreResult) {
            progressStep.archive_restore_result = archiveRestoreResult;
          }
          if (stepKey === 'archive_restore_blocked') {
            const existingStep = state.messages[messageIndex].progressSteps!.find(
              (step) => step.step_key === 'archive_restore_blocked',
            );
            if (existingStep) {
              Object.assign(existingStep, progressStep);
            } else {
              state.messages[messageIndex].progressSteps!.push(progressStep);
            }
          } else {
            state.messages[messageIndex].progressSteps!.push(progressStep);
          }
          if (isMediaAnalysis) {
            state.messages[messageIndex].mediaAnalysisStatus = stepKey as 'analyzing_image' | 'analyzing_video';
          }
        }
      });
      if (stepKey === 'archive_restore_blocked') {
        const message = archiveRestoreBlock?.message ?? 'Archived context restore was blocked.';
        const { toast } = await import('@/lib/utils/toast');
        toast.warning(message, { duration: 6000 });
      }

      if (stepKey === 'ux_warning_truncated') {
        const payloadData = data.data as Record<string, unknown> | undefined;
        const msg =
          typeof payloadData?.message === 'string'
            ? payloadData.message
            : 'Warning: Large content was intelligently truncated to fit within context limits.';
        const { toast } = await import('@/lib/utils/toast');
        toast.warning(msg, { duration: 8000 });
      }
    }

    if (stepKey === 'cache_break') {
      const sd = data.data as Record<string, unknown> | undefined;
      const reason = typeof sd?.reason === 'string' ? sd.reason : '';
      const suggestedActions = typeof sd?.suggested_actions === 'string' ? sd.suggested_actions : '';
      if (reason) {
        actions.setMessages((state) => {
          const idx = findAssistantMessageIndex(state.messages, data.messageId);
          if (idx !== -1) {
            state.messages[idx].cacheBreakReason = reason;
            if (suggestedActions) {
              state.messages[idx].cacheSuggestedActions = suggestedActions;
            }
          }
        });
        const notifyEnabled = useConfigStore.getState().enableCacheBreakNotification;
        if (notifyEnabled) {
          const tokenDrop = typeof sd?.token_drop === 'number' ? sd.token_drop : 0;
          const dropText = tokenDrop > 1000 ? `, ~${Math.round(tokenDrop / 1000)}k tokens uncached` : '';
          import('@/lib/utils/toast').then(({ toast }) => {
            toast.info(`Cache reset: ${reason}${dropText}`, { duration: 5000 });
          });
        }
      }
    }

    if (stepKey === 'analyzing_image_clear' || stepKey === 'analyzing_video_clear') {
      const analysisStepKey = stepKey === 'analyzing_image_clear' ? 'analyzing_image' : 'analyzing_video';
      window.setTimeout(() => {
        actions.setMessages((state) => {
          const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
          if (messageIndex !== -1 && state.messages[messageIndex].progressSteps) {
            state.messages[messageIndex].progressSteps = state.messages[messageIndex].progressSteps!.filter(
              (step) => step.step_key !== analysisStepKey,
            );
            state.messages[messageIndex].mediaAnalysisStatus = null;
          }
        });
      }, 250);
    }

    const statusData = data.data;
    if (typeof statusData === 'object' && statusData !== null) {
      const sd = statusData as Record<string, unknown>;

      if ('progress_percent' in sd && typeof sd.progress_percent === 'number') {
        actions.setMessages((state) => {
          const idx = findAssistantMessageIndex(state.messages, data.messageId);
          if (idx !== -1) {
            const steps = state.messages[idx].progressSteps;
            if (steps && steps.length > 0) {
              steps[steps.length - 1].progress_percent = sd.progress_percent as number;
            }
          }
        });
      }

      if (sd.phase === 'clarify' && sd.status === 'resolved') {
        actions.setMessages((state) => {
          const idx = findAssistantMessageIndex(state.messages, data.messageId);
          if (idx !== -1 && state.messages[idx].clarification) {
            state.messages[idx].clarification!.answered = true;
          }
        });
      }

      if (sd.phase === 'plan' && typeof sd.plan === 'string') {
        const planText = (sd.plan as string).trim();
        if (planText) {
          const planLines = planText
            .split('\n')
            .map((line) => line.replace(/^[\d\-.*]+\s*/, '').trim())
            .filter((line) => line.length > 0)
            .slice(0, 10);

          if (planLines.length > 0) {
            actions.setMessages((state) => {
              const idx = findAssistantMessageIndex(state.messages, data.messageId);
              if (idx !== -1) {
                const steps = state.messages[idx].progressSteps;
                if (steps && steps.length > 0) {
                  const lastStep = steps[steps.length - 1];
                  lastStep.items = planLines.map((line) => ({ text: line }));
                }
              }
            });
          }
        }
      }

      if (sd.phase === 'research' && typeof sd.agent_status === 'string') {
        const MAX_DETAIL_ITEMS = 30;
        let detailText: string | null = null;

        if (sd.agent_status === 'started' && typeof sd.task === 'string') {
          detailText = (sd.task as string).slice(0, 120);
        } else if (sd.agent_status === 'tool_call' && typeof sd.tool_name === 'string') {
          detailText = sd.tool_name as string;
        }

        if (detailText) {
          actions.setMessages((state) => {
            const idx = findAssistantMessageIndex(state.messages, data.messageId);
            if (idx !== -1) {
              const steps = state.messages[idx].progressSteps;
              if (steps && steps.length > 0) {
                const lastStep = steps[steps.length - 1];
                if (!lastStep.items || !Array.isArray(lastStep.items)) {
                  lastStep.items = [];
                }
                const items = lastStep.items as { text: string }[];
                items.push({ text: detailText! });
                if (items.length > MAX_DETAIL_ITEMS) {
                  items.splice(0, items.length - MAX_DETAIL_ITEMS);
                }
              }
            }
          });
        }
      }
    }

    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.SUBAGENT_START) {
    // Dispatch to dedicated subagent store for Dashboard tree
    import('@/store/chat/useSubagentStore').then(({ useSubagentStore }) => {
      useSubagentStore.getState().upsertNode({
        task_id: data.data.task_id,
        parent_task_id: data.data.parent_task_id || '',
        agent_type: data.data.agent_type,
        description: data.data.description || '',
        status: 'running',
        progress: 0,
        role: data.data.role,
        control_scope: data.data.control_scope,
        budget: data.data.budget,
        startedAt: Date.now(),
      });
    });

    actions.setMessages((state) => {
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        state.messages[messageIndex].progressSteps!.push({
          step_key: 'subagent_running',
          tool_name: data.data.agent_type,
          items: [{ text: data.data.description || '' }],
        });
      }
    });
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.SUBAGENT_PROGRESS) {
    // Dispatch to dedicated subagent store for Dashboard
    import('@/store/chat/useSubagentStore').then(({ useSubagentStore }) => {
      const pd = data.data;
      const progressPercent = Math.round((pd.progress ?? 0) * 100);
      const taskId = pd.task_id || pd.agent_instance || '';
      if (taskId) {
        const store = useSubagentStore.getState();
        store.updateProgress(taskId, progressPercent, pd.current_step);
        if (typeof pd.eta_seconds === 'number' && pd.eta_seconds > 0) {
          store.updateEstimate(taskId, pd.eta_seconds);
        }
      }
    });

    actions.setMessages((state) => {
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        const progressData = data.data;

        const progressPercent = Math.round((progressData.progress ?? 0) * 100);
        const currentStep = progressData.current_step || 'Processing';
        const isEstimated = progressData.is_estimated ?? false;
        const etaReadable = progressData.eta_readable;
        const toolCount = progressData.tool_count;
        const budgetTokens = progressData.budget_tokens;

        let progressText = `${currentStep}... ${progressPercent}%`;

        if (etaReadable) {
          progressText += ` (预计还需${etaReadable})`;
        }

        if (!budgetTokens && toolCount !== undefined) {
          progressText += ` [${toolCount}/8工具]`;
        }

        if (isEstimated) {
          progressText += ' (估算)';
        }

        state.messages[messageIndex].progressSteps!.push({
          step_key: 'subagent_progress',
          tool_name: progressData.current_step,
          items: [{ text: progressText }],
        });
      }
    });
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.SUBAGENT_LOG) {
    actions.setMessages((state) => {
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        const logData = data.data;
        const msg = logData.message || '';

        state.messages[messageIndex].progressSteps!.push({
          step_key: msg,
          agent_instance: logData.agent_instance,
          tool_name: logData.tool_name || logData.level || 'INFO',
          items: [],
        });
      }
    });
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.SUBAGENT_COMPLETION) {
    actions.setMessages((state) => {
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        state.messages[messageIndex].progressSteps!.push({
          step_key: 'subagent_notification',
          items: [{ text: data.data || '' }],
        });
      }
    });

    // 启动5秒倒计时，若5秒内无MESSAGE事件则显示提示
    if (data.messageId) {
      useChatStore.getState().triggerSubagentPrompt(data.messageId);
    }

    return { added, recievedMessage };
  }

  // SUBAGENT_STATUS_UPDATE: structured completion/failure/timeout event from Harness
  if (data.type === 'subagent_status_update') {
    import('@/store/chat/useSubagentStore').then(({ useSubagentStore }) => {
      const payload = data.data;
      const taskId = payload?.task_id;
      if (taskId) {
        const store = useSubagentStore.getState();
        store.upsertNode({
          task_id: taskId,
          role: payload.role,
          control_scope: payload.control_scope,
          policy_reason: payload.policy_reason,
          policy_details: payload.policy_details,
          budget: payload.budget,
        });
        store.completeNode(taskId, normalizeSubagentStatus(payload.status), payload.error);
      }
    });
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.FISSION_TOPOLOGY) {
    import('@/store/chat/useSubagentStore').then(({ useSubagentStore }) => {
      const payload = data.data as any;
      if (payload && payload.fission_id) {
        useSubagentStore.getState().setFissionTopology({
          fission_id: payload.fission_id,
          nodes: payload.nodes || [],
          total_cost_usd: payload.total_cost_usd || 0,
        });
      }
    });
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.TEAMMATE_MESSAGE) {
    const chatId = useChatStore.getState().chatId;
    const payload = data.data as Record<string, string | number> | undefined;
    if (chatId && payload?.from_task_id && payload?.to_task_id) {
      import('@/lib/utils/teammateMessage').then(({ normalizeTeammateEntry }) => {
        import('@/store/chat/useSubagentStore').then(({ useSubagentStore }) => {
          const entry = normalizeTeammateEntry(payload);
          useSubagentStore.getState().appendTeammateMessage(entry);
          if (typeof window !== 'undefined') {
            window.dispatchEvent(
              new CustomEvent('teammate_message', {
                detail: { chat_id: chatId, message: payload },
              }),
            );
          }
        });
      });
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.FILE_DIFF) {
    const diffData = data.data;
    /** When FILE_DIFF arrives before TASKS_STEPS/ROUTING creates the assistant row, avoid attaching
     *  the diff to the *previous* turn's assistant (last assistant before the trailing user message). */
    let createdAssistantForDiff = false;

    actions.setMessages((state) => {
      let messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex === -1) {
        state.messages.push({
          content: '',
          messageId: data.messageId,
          chatId: state.messages[0]?.chatId || '',
          role: 'assistant',
          progressSteps: [],
          createdAt: new Date(),
        });
        messageIndex = state.messages.length - 1;
        createdAssistantForDiff = true;
      }
      const message = state.messages[messageIndex];
      if (!message.progressSteps) {
        message.progressSteps = [];
      }
      const steps = message.progressSteps;

      let matched = false;
      for (let i = steps.length - 1; i >= 0 && !matched; i -= 1) {
        const step = steps[i];
        if (!step.items || !Array.isArray(step.items)) {
          continue;
        }
        for (const raw of step.items) {
          const fp = parseProgressFilePath(raw);
          if (!fp || !pathsMatchForFileDiff(diffData.path, fp)) {
            continue;
          }
          if (raw && typeof raw === 'object' && 'file_path' in raw) {
            const row = raw as ProgressFileItem;
            const picked = pickMergedFileDiffPayload(
              { diff: row.diff, diff_truncated: row.diff_truncated },
              diffData.diff,
              Boolean(diffData.truncated),
            );
            row.diff = picked.diff;
            row.diff_truncated = picked.diff_truncated;
            matched = true;
            break;
          }
        }
      }

      if (!matched) {
        steps.push({
          step_key: 'file_diff',
          tool_name: null,
          items: [
            {
              file_path: diffData.path,
              action_type: 'write',
              diff: diffData.diff,
              ...(diffData.truncated ? { diff_truncated: true } : {}),
            },
          ],
        });
      }

      const diffArtifactId = `mem-diff-${diffData.path}`;
      const portalState = useArtifactPortalStore.getState();
      const mergedRow = (() => {
        for (let i = steps.length - 1; i >= 0; i -= 1) {
          const step = steps[i];
          if (!step.items || !Array.isArray(step.items)) continue;
          for (const raw of step.items) {
            const fp = parseProgressFilePath(raw);
            if (!fp || !pathsMatchForFileDiff(diffData.path, fp)) continue;
            if (raw && typeof raw === 'object' && 'file_path' in raw) {
              const row = raw as ProgressFileItem;
              if (row.diff) {
                return { diff: row.diff, truncated: Boolean(row.diff_truncated) };
              }
            }
          }
        }
        return { diff: diffData.diff, truncated: Boolean(diffData.truncated) };
      })();
      if (portalState.openTabs.some((t) => t.artifact.id === diffArtifactId)) {
        portalState.updateTabContent(diffArtifactId, mergedRow.diff, {
          truncated: mergedRow.truncated,
        });
      }
    });
    return { added: added || createdAssistantForDiff, recievedMessage };
  }

  if (data.type === AgentEventType.TOOL_IMAGE_OUTPUT) {
    const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex === -1) return { added, recievedMessage };

    const message = state.messages[messageIndex];
    const imgEntry: import('@/store/chat/types').ToolImageOutput = {
      base64: data.data.base64,
      mimeType: data.data.mime_type,
      toolName: data.tool_name,
    };
    message.toolImages = [...(message.toolImages ?? []), imgEntry];
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.BROWSER_VIEW_UPDATE) {
    const { default: useBrowserInspectorStore } = await import('@/store/useBrowserInspectorStore');
    const store = useBrowserInspectorStore.getState();
    store.setBrowserActive(true);
    store.updateViewData({
      screenshotBase64: data.data.screenshot_base64,
      mimeType: data.data.mime_type,
      refs: data.data.refs,
      pageUrl: data.data.page_url,
      pageTitle: data.data.page_title,
      viewportWidth: data.data.viewport_width,
      viewportHeight: data.data.viewport_height,
      updatedAt: Date.now(),
    });
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.DESKTOP_VIEW_UPDATE) {
    const { default: useDesktopInspectorStore } = await import('@/store/useDesktopInspectorStore');
    const store = useDesktopInspectorStore.getState();
    store.setDesktopActive(true);
    store.updateViewData({
      screenshotBase64: data.data.screenshot_base64,
      mimeType: data.data.mime_type,
      refs: data.data.refs,
      appName: data.data.app_name,
      windowTitle: data.data.window_title,
      scope: data.data.scope,
      needsPermission: data.data.needs_permission,
      viewportWidth: data.data.viewport_width,
      viewportHeight: data.data.viewport_height,
      updatedAt: Date.now(),
    });
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.TOOL_START) {
    recievedMessage = '';

    const toolName = String((data as unknown as { tool_name?: string }).tool_name ?? '');
    if (toolName.startsWith('browser_')) {
      const { default: inspectorStore } = await import('@/store/useBrowserInspectorStore');
      inspectorStore.getState().setBrowserActive(true);
    }
    if (toolName.startsWith('desktop_')) {
      const { default: desktopStore } = await import('@/store/useDesktopInspectorStore');
      desktopStore.getState().setDesktopActive(true);
    }

    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.TOOL_END) {
    const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex === -1) return { added, recievedMessage };

    const message = state.messages[messageIndex];
    const steps = message.progressSteps;
    if (steps && steps.length > 0 && data.duration_ms != null) {
      const lastStep = steps[steps.length - 1];
      lastStep.duration_ms = data.duration_ms;
      if (!lastStep.status) {
        lastStep.status = 'success';
      }
    }

    if (data.tool_name?.startsWith('browser_')) {
      const { default: inspectorStore } = await import('@/store/useBrowserInspectorStore');
      void inspectorStore.getState().fetchSnapshot();
    }

    if (data.tool_name?.startsWith('desktop_')) {
      const { default: desktopStore } = await import('@/store/useDesktopInspectorStore');
      void desktopStore.getState().fetchSnapshot();
    }

    if (data.tool_name === 'cron_manage' && data.result) {
      try {
        const resultObj = typeof data.result === 'string' ? JSON.parse(data.result) : data.result;
        if (resultObj && resultObj.status === 'success') {
          message.metadata = {
            ...message.metadata,
            cron_job_result: resultObj,
          };
        }
      } catch {
        // parse failure is expected for non-cron results
      }
    }

    if (isMemoryRecallToolName(data.tool_name)) {
      if (Array.isArray(data.cited_memory_ids)) {
        const ids = data.cited_memory_ids.filter((id): id is string => typeof id === 'string' && id.length > 0);
        const existing = message.citedMemoryIds ?? [];
        message.citedMemoryIds = [...new Set([...existing, ...ids])];
      }

      const refs = normalizeCitedMemoryReferences(data.cited_memory_refs);
      if (refs.length > 0) {
        message.citedMemoryRefs = mergeCitedMemoryReferences(message.citedMemoryRefs, refs);
      }
    }

    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.TOOL_FAILURE) {
    const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex === -1) return { added, recievedMessage };

    const steps = state.messages[messageIndex].progressSteps;
    if (steps && steps.length > 0) {
      const lastStep = steps[steps.length - 1];
      lastStep.duration_ms = data.duration_ms;
      lastStep.status = 'error';
      lastStep.error = data.error;
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.TOOL_STDOUT_CHUNK) {
    const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex === -1) return { added, recievedMessage };

    const steps = state.messages[messageIndex].progressSteps;
    if (steps && steps.length > 0) {
      const lastStep = steps[steps.length - 1];
      // Avoid excessive re-renders by mutating cautiously or depending on how state updates work
      // Since Immer is used, mutating lastStep works
      const newStdout = (lastStep.stdout || '') + data.data;
      // 终端缓冲截断保护，防止浏览器 OOM（保留最后 3 万个字符，并在换行处安全截断以保护 ANSI 边界）
      if (newStdout.length > 30000) {
        const sliced = newStdout.slice(-30000);
        const newlineIndex = sliced.indexOf('\n');
        const safeTruncated = newlineIndex !== -1 ? sliced.substring(newlineIndex + 1) : sliced;
        lastStep.stdout = '...[Terminal output truncated to preserve memory]...\n' + safeTruncated;
      } else {
        lastStep.stdout = newStdout;
      }
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.TOOL_CANCELLED) {
    const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex === -1) return { added, recievedMessage };

    const steps = state.messages[messageIndex].progressSteps;
    if (steps && steps.length > 0) {
      const lastStep = steps[steps.length - 1];
      lastStep.duration_ms = data.duration_ms;
      lastStep.status = 'warning';

      // Format error message with cancel reason
      const cancelReason = data.cancel_reason;
      let errorMsg = 'Tool execution was cancelled';
      if (cancelReason === 'user_cancelled') {
        errorMsg = 'Cancelled by user';
      } else if (cancelReason === 'timeout') {
        errorMsg = 'Cancelled (timeout)';
      } else if (cancelReason === 'session_ended') {
        errorMsg = 'Cancelled (session ended)';
      } else if (data.error) {
        errorMsg = data.error;
      }
      lastStep.error = errorMsg;
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.ROUTING_DECISION) {
    const routingData = data.data;
    const tier = routingData?.tier as 'simple' | 'standard' | 'reasoning' | 'complex' | undefined;
    if (tier) {
      if (!added) {
        actions.setMessages((state) => {
          state.messages.push({
            content: '',
            messageId: data.messageId,
            chatId: state.messages[0]?.chatId || '',
            role: 'assistant',
            routingTier: tier,
            createdAt: new Date(),
            metadata: data.metadata,
          });
        });
        added = true;
      } else {
        actions.setMessages((state) => {
          const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
          if (messageIndex !== -1) {
            state.messages[messageIndex].routingTier = tier;
          }
        });
      }
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.PRIVACY_LEVEL) {
    const privacyData = data.data;
    if (privacyData?.current_turn_level) {
      actions.setMessages((state) => {
        const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex !== -1) {
          state.messages[messageIndex].privacyLevel = privacyData.current_turn_level;
          if (privacyData.action) {
            state.messages[messageIndex].privacyAction = privacyData.action;
          }
        }
      });
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.PRIVACY_ROUTE) {
    const routeData = data.data;
    if (routeData?.route) {
      actions.setMessages((state) => {
        const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex !== -1) {
          state.messages[messageIndex].privacyRoute = routeData.route;
        }
      });
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.TOKEN_USAGE) {
    const tokenData = data.data as {
      usage: import('./types').TokenUsage;
      cost_usd?: number;
      model_name?: string;
    };

    actions.setMessages((state) => {
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        state.messages[messageIndex].usage = tokenData.usage;
        if (tokenData.cost_usd !== undefined) {
          state.messages[messageIndex].costUsd = tokenData.cost_usd;
        }
        if (tokenData.model_name) {
          state.messages[messageIndex].modelName = tokenData.model_name;
        }
      }
    });

    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.REASONING) {
    if (data.data && data.data.length > 0) {
      const reasoningChunk = (data.data as string).replace(UNICODE_CONTROL_RE, '');

      state.scheduler.schedule(() => {
        actions.setMessages((updateState) => {
          const messageIndex = findAssistantMessageIndex(updateState.messages, data.messageId);
          if (messageIndex === -1) return;

          if (!updateState.messages[messageIndex].reasoningStartedAt) {
            updateState.messages[messageIndex].reasoningStartedAt = Date.now();
          }

          const currentReasoning = updateState.messages[messageIndex].reasoning || '';
          updateState.messages[messageIndex].reasoning = currentReasoning + reasoningChunk;

          if (!updateState.messageAppeared) {
            updateState.messageAppeared = true;
          }
        });
      }, 0);
    }
  }

  if (data.type === AgentEventType.MESSAGE) {
    // LLM已响应，清除Subagent提示计时器
    useChatStore.getState().clearSubagentPromptTimer();
    useChatStore.getState().setSubagentPromptVisible(false);

    // Finalize reasoning duration when first content chunk arrives
    actions.setMessages((updateState) => {
      const messageIndex = findAssistantMessageIndex(updateState.messages, data.messageId);
      if (messageIndex === -1) return;
      const msg = updateState.messages[messageIndex];
      if (msg.reasoningStartedAt && !msg.reasoningDurationMs) {
        msg.reasoningDurationMs = Date.now() - msg.reasoningStartedAt;
      }
    });

    const isClarify =
      typeof data.metadata === 'object' &&
      data.metadata !== null &&
      (data.metadata as Record<string, unknown>).phase === 'clarify';

    const clarifyMeta = isClarify ? (data.metadata as Record<string, unknown>) : undefined;
    const clarificationForm = isClarify ? normalizeClarificationForm(clarifyMeta?.form) : undefined;
    let clarifyOptions: string[] | undefined = undefined;
    let clarifyAllowMultiple = false;
    if (isClarify && clarifyMeta) {
      if (Array.isArray(clarifyMeta.options)) {
        clarifyOptions = clarifyMeta.options.filter((item): item is string => typeof item === 'string');
      }
      if (typeof clarifyMeta.allow_multiple === 'boolean') {
        clarifyAllowMultiple = clarifyMeta.allow_multiple;
      }
      if (clarificationForm) {
        const firstQuestion = clarificationForm.questions[0];
        if (firstQuestion?.options && firstQuestion.options.length > 0) {
          clarifyOptions = firstQuestion.options.map((option) => option.label);
        }
        if (typeof firstQuestion?.allowMultiple === 'boolean') {
          clarifyAllowMultiple = firstQuestion.allowMultiple;
        }
      }
    }

    if (data.data && data.data.length > 0) {
      recievedMessage += (data.data as string).replace(UNICODE_CONTROL_RE, '');

      // 使用自适应防抖调度器，而不是直接调用 requestAnimationFrame
      state.scheduler.schedule(() => {
        actions.setMessages((updateState) => {
          const messageIndex = findAssistantMessageIndex(updateState.messages, data.messageId);
          if (messageIndex === -1) return;

          updateState.messages[messageIndex].content = recievedMessage;

          if (isClarify) {
            updateState.messages[messageIndex].clarification = {
              question: recievedMessage,
              answered: false,
              options: clarifyOptions,
              allowMultiple: clarifyAllowMultiple,
              ...(clarificationForm
                ? {
                    title: clarificationForm.title ?? undefined,
                    form: clarificationForm,
                  }
                : {}),
            };
          }

          if (!updateState.messageAppeared) {
            updateState.messageAppeared = true;
          }
        });
      }, recievedMessage.length);
    }
  }

  // 处理 artifacts 事件
  if (data.type === AgentEventType.ARTIFACTS) {
    actions.setMessages((state) => {
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex === -1) {
        return;
      }

      // 初始化 artifacts 数组
      if (!state.messages[messageIndex].artifacts) {
        state.messages[messageIndex].artifacts = [];
      }

      // 添加 artifacts
      if (Array.isArray(data.data)) {
        state.messages[messageIndex].artifacts!.push(...data.data);

        // 如果 Portal 正在显示 artifact，更新其信息（包括 preview_url）
        const portalStore = useArtifactPortalStore.getState();
        const activeTab =
          portalStore.activeTabIndex >= 0 && portalStore.activeTabIndex < portalStore.openTabs.length
            ? portalStore.openTabs[portalStore.activeTabIndex]
            : null;
        if (activeTab) {
          // 检查是否是当前正在预览的 artifact
          const updatedArtifact = data.data.find((a: { id: string }) => a.id === activeTab.artifact?.id);
          if (updatedArtifact) {
            portalStore.updateCurrentArtifact(updatedArtifact);
            // 如果仍在生成中，结束实时预览
            if (activeTab.isGenerating) {
              portalStore.endRealtimePreview();
            }
          }
        }
      }

      if (!state.messageAppeared) {
        state.messageAppeared = true;
      }
    });
  }

  // 处理 artifact 内容实时更新事件（用于实时预览）
  if (data.type === AgentEventType.ARTIFACT_CONTENT) {
    const portalStore = useArtifactPortalStore.getState();
    const activeTab =
      portalStore.activeTabIndex >= 0 && portalStore.activeTabIndex < portalStore.openTabs.length
        ? portalStore.openTabs[portalStore.activeTabIndex]
        : null;

    // 如果是完整内容（文件创建完成）
    if (data.subtype === 'complete' && data.content) {
      // 创建临时 artifact 对象用于实时预览
      const tempArtifact: Artifact = {
        id: data.artifactId,
        filename: data.filename,
        type: (data.artifactType ?? 'code') as ArtifactType,
        content_type: 'text/plain',
        size: data.content.length,
        preview_url: '',
        download_url: '',
        language: data.language,
      };

      // 自动打开 Portal 并显示内容
      portalStore.startRealtimePreview(tempArtifact);
      portalStore.appendContent(data.content);
      portalStore.endRealtimePreview();
    }

    // 如果是新 artifact 开始生成（流式）
    if (data.subtype === 'start') {
      const artifact = data.artifact;
      if (artifact) {
        portalStore.startRealtimePreview(artifact);
      }
    }

    // 如果是内容增量更新（流式）
    if (data.subtype === 'chunk' && data.content) {
      if (activeTab?.isGenerating && activeTab?.artifact?.id === data.artifactId) {
        portalStore.appendContent(data.content);
      }
    }

    // 如果是生成完成（流式）
    if (data.subtype === 'end') {
      if (activeTab?.isGenerating && activeTab?.artifact?.id === data.artifactId) {
        portalStore.endRealtimePreview();
      }
    }
  }

  // 处理 UI 工件事件
  if (data.type === AgentEventType.UI_UPDATE) {
    actions.setMessages((state) => {
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex === -1) {
        return;
      }

      if (data.subtype === 'ui_artifact') {
        // 初始化 uiArtifacts 数组
        if (!state.messages[messageIndex].uiArtifacts) {
          state.messages[messageIndex].uiArtifacts = [];
        }

        // 添加 UI artifacts
        if (Array.isArray(data.data)) {
          state.messages[messageIndex].uiArtifacts!.push(...(data.data as UIArtifact[]));
        }
      }
      // data_update 类型的 UI 更新在前端另行处理（如有需要）

      if (!state.messageAppeared) {
        state.messageAppeared = true;
      }
    });
  }

  // CAPTCHA events → render as progress steps so the user sees the status
  if (
    data.type === AgentEventType.CAPTCHA_DETECTED ||
    data.type === AgentEventType.CAPTCHA_RESOLVED ||
    data.type === AgentEventType.CAPTCHA_TIMEOUT
  ) {
    const captchaStatus: NonNullable<ProgressItem['status']> =
      data.type === AgentEventType.CAPTCHA_DETECTED
        ? 'warning'
        : data.type === AgentEventType.CAPTCHA_RESOLVED
          ? 'success'
          : 'error';

    actions.setMessages((state) => {
      const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        const steps = state.messages[messageIndex].progressSteps ?? [];
        const captchaStepIdx = steps.findIndex((s) => s.step_key === 'captcha_challenge');
        const step = {
          step_key: 'captcha_challenge',
          items: [
            {
              text: data.data?.reason ?? 'CAPTCHA challenge',
              captcha_type: data.data?.captcha_type,
            },
          ],
          status: captchaStatus,
        };
        if (captchaStepIdx !== -1) {
          steps[captchaStepIdx] = step;
        } else {
          steps.push(step);
        }
        state.messages[messageIndex].progressSteps = steps;
      }
    });
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.MODEL_ESCALATED) {
    const payload = data.data as {
      from_model?: string;
      to_model?: string;
      reason?: string;
    };
    if (payload) {
      const from = payload.from_model ?? 'unknown';
      const to = payload.to_model ?? 'unknown';
      const reason = payload.reason;
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const isZh = lang?.startsWith('zh');
      const baseMessage = isZh ? `模型已自动升级: ${from} → ${to}` : `Model auto-upgraded: ${from} → ${to}`;
      const toastMessage = reason
        ? isZh
          ? `${baseMessage}（原因: ${reason}）`
          : `${baseMessage} (reason: ${reason})`
        : baseMessage;

      import('@/lib/utils/toast').then(({ toast }) => {
        toast.info(toastMessage, { duration: 5000 });
      });

      actions.setMessages((state) => {
        const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex !== -1) {
          const steps = state.messages[messageIndex].progressSteps ?? [];
          steps.push({
            step_key: 'model_escalated',
            items: [{ text: toastMessage }],
            status: 'success',
          });
          state.messages[messageIndex].progressSteps = steps;
        }
      });
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.MODEL_FAILOVER) {
    const payload = data.data as
      | {
          fromModel?: string;
          toModel?: string;
          reason?: string;
          errorMessage?: string;
          cooldownMs?: number;
          attemptCount?: number;
        }
      | undefined;
    if (payload) {
      const from = payload.fromModel ?? 'unknown';
      const to = payload.toModel ?? 'unknown';
      const reason = payload.reason;
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const isZh = lang?.startsWith('zh');
      const baseMessage = isZh
        ? `模型已切换以避开故障: ${from} → ${to}`
        : `Model switched to dodge a fault: ${from} → ${to}`;
      const toastMessage = reason
        ? isZh
          ? `${baseMessage}（原因: ${reason}）`
          : `${baseMessage} (reason: ${reason})`
        : baseMessage;

      import('@/lib/utils/toast').then(({ toast }) => {
        toast.warning(toastMessage, { duration: 6000 });
      });

      actions.setMessages((state) => {
        const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex !== -1) {
          const steps = state.messages[messageIndex].progressSteps ?? [];
          steps.push({
            step_key: 'model_failover',
            items: [{ text: toastMessage }],
            status: 'success',
          });
          state.messages[messageIndex].progressSteps = steps;
        }
      });
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.MODEL_RECOVERY) {
    const payload = data.data as
      | {
          model?: string;
          downtimeMs?: number;
        }
      | undefined;
    if (payload?.model) {
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const isZh = lang?.startsWith('zh');
      const downtimeSec = payload.downtimeMs ? Math.round(payload.downtimeMs / 1000) : null;
      const toastMessage = isZh
        ? downtimeSec !== null
          ? `模型已恢复可用: ${payload.model}（停机 ${downtimeSec}s）`
          : `模型已恢复可用: ${payload.model}`
        : downtimeSec !== null
          ? `Model recovered: ${payload.model} (downtime ${downtimeSec}s)`
          : `Model recovered: ${payload.model}`;

      import('@/lib/utils/toast').then(({ toast }) => {
        toast.success(toastMessage, { duration: 4000 });
      });

      actions.setMessages((state) => {
        const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex !== -1) {
          const steps = state.messages[messageIndex].progressSteps ?? [];
          steps.push({
            step_key: 'model_recovery',
            items: [{ text: toastMessage }],
            status: 'success',
          });
          state.messages[messageIndex].progressSteps = steps;
        }
      });
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.CLIENT_ACTION) {
    const actionData = data.data;
    if (actionData && actionData.action === 'write_clipboard') {
      import('@/lib/utils/clipboardUtils').then(({ writeToClipboardByAgent }) => {
        writeToClipboardByAgent(actionData.payload.text);
      });
    }
    return { added, recievedMessage };
  }

  if (data.type === 'goal_status') {
    const { useGoalStore } = await import('./goals/useGoalStore');
    const goalState = normalizeGoalState(data.data);
    useGoalStore.getState().setActiveGoal(goalState);
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.FILE_MUTATION_FAILED) {
    const messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex !== -1 && data.data?.files) {
      actions.setMessages((s) => {
        s.messages[messageIndex].fileMutationFailures = data.data.files;
      });
    }
    return { added, recievedMessage };
  }

  if (data.type === AgentEventType.MESSAGE_END) {
    if (data.goal_status) {
      const { useGoalStore } = await import('./goals/useGoalStore');
      useGoalStore.getState().setActiveGoal(normalizeGoalState(data.goal_status));
    }
    setTimeout(() => {
      actions.setMessages((state) => {
        let messageIndex = findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex === -1 && data.completion_status === 'budget_blocked') {
          state.messages.push({
            content: '',
            messageId: data.messageId,
            chatId: state.messages[0]?.chatId || '',
            role: 'assistant',
            createdAt: new Date(),
            completionStatus: 'budget_blocked',
          });
          messageIndex = state.messages.length - 1;
        }
        if (messageIndex !== -1) {
          state.messages[messageIndex].content = recievedMessage;

          // Finalize reasoning duration if not already set (covers thinking_budget_exhausted edge case)
          const msg = state.messages[messageIndex];
          if (msg.reasoningStartedAt && !msg.reasoningDurationMs) {
            msg.reasoningDurationMs = Date.now() - msg.reasoningStartedAt;
          }

          if (data.usage) {
            state.messages[messageIndex].usage = data.usage;
          }

          if (data.token_economics) {
            state.messages[messageIndex].tokenEconomics = data.token_economics;
          }

          if (data.cost_usd !== undefined) {
            state.messages[messageIndex].costUsd = data.cost_usd;
          }

          if (data.cost_status) {
            state.messages[messageIndex].costStatus = data.cost_status;
          }

          if (data.completion_status) {
            state.messages[messageIndex].completionStatus = data.completion_status;
          }

          if (data.model) {
            state.messages[messageIndex].modelName = data.model;
          }

          if (data.context_budget) {
            state.messages[messageIndex].contextBudget = data.context_budget;
          }

          if (data.citations) {
            state.messages[messageIndex].citations = data.citations;
          }

          if (data.memoryBudget) {
            state.messages[messageIndex].memoryBudget = data.memoryBudget;
          }

          if (data.consensus_meta) {
            state.messages[messageIndex].consensusMeta = data.consensus_meta;
          }
        }

        state.loading = false;
        state.messageAppeared = true;
      });

      const lastMsg = state.messages[state.messages.length - 1];
      if (lastMsg) {
        actions._processSuggestions(lastMsg);
      }

      actions.scheduleAutoSave();

      // Refresh per-chat workspace from API so Active Working Memory chips can open file
      // previews when FILE_DIFF is absent but the session workspace exists (silent=true).
      void import('@/services/chat').then(({ getChatDetail }) => {
        const chatId = useChatStore.getState().chatId;
        if (!chatId) return;
        void getChatDetail(chatId, true)
          .then((detail) => {
            const dir = detail.chat.workspace_dir;
            if (typeof dir === 'string' && dir.trim().length > 0) {
              useChatStore.getState().setWorkspaceDir(dir.trim());
            }
          })
          .catch(() => undefined);
      });
    }, 50);

    if (useConfigStore.getState().enableCompletionSound) {
      playCompletionSound();
    }

    // Release the processing lock when message ends successfully
    useToolApprovalStore.getState().unmarkProcessing(data.messageId);
  }

  return { added, recievedMessage };
};
