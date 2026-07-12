import type { StreamCtx } from '../streamContext';
import * as H from './handlerDeps';

const PROGRESS_STEP_KEYS = new Set([
  'model_failover',
  'context_compaction',
  'context_truncation',
  'safety_fallback_active',
  'memory_archived',
  'context_pruned',
  'archive_checkpoint',
  'archive_restore_blocked',
  'archive_restore_result',
  'thinking_budget_exhausted',
  'tool_call_truncated',
  'text_continuation',
  'text_continuation_exhausted',
  'transient_retry',
  'analyzing_image',
  'analyzing_video',
  'media_stripped',
  'media_rejected_recovery',
  'ux_warning_truncated',
  'consensus_active',
  'consensus_reference_done',
  'workflow_init',
  'workflow_planning',
  'workflow_execution',
  'workflow_stage',
  'loop_guard_warn',
  'loop_guard_break',
  'crawl_task_progress',
]);

export function isStatusProgressStep(stepKey: string | undefined): boolean {
  return stepKey !== undefined && PROGRESS_STEP_KEYS.has(stepKey);
}

export async function applyStatusProgressStep(ctx: StreamCtx, stepKey: string): Promise<void> {
  const { data, actions } = ctx;
  const isMediaAnalysis = stepKey === 'analyzing_image' || stepKey === 'analyzing_video';
  const isArchiveRestoreStatus = stepKey === 'archive_restore_blocked' || stepKey === 'archive_restore_result';
  const archiveRestoreBlock =
    stepKey === 'archive_restore_blocked'
      ? H.parseArchiveRestoreBlockPayload(data.data?.archive_restore_block)
      : undefined;
  const archiveRestoreResult =
    stepKey === 'archive_restore_result'
      ? H.parseArchiveRestoreResultPayload(data.data?.archive_restore_result)
      : undefined;
  const archiveRestoreActions = H.buildArchiveRestoreActions(archiveRestoreBlock);
  let displayKey =
    stepKey === 'model_failover' && data.error_kind ? `model_failover_${data.error_kind}` : stepKey;
  if (stepKey === 'workflow_stage') {
    const stageData = data.data as Record<string, unknown> | undefined;
    const category =
      stageData && typeof stageData.notify_category === 'string' && stageData.notify_category
        ? stageData.notify_category
        : 'default';
    displayKey = `workflow_stage:${category}`;
  }
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
                  : (stepKey === 'workflow_init' ||
                        stepKey === 'workflow_planning' ||
                        stepKey === 'workflow_execution' ||
                        stepKey === 'workflow_stage') &&
                      typeof data.data?.message === 'string'
                    ? data.data.message
                    : '';
  actions.setMessages((state) => {
    let messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
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
      ctx.added = true;
    }

    if (messageIndex !== -1) {
      if (!state.messages[messageIndex].progressSteps) {
        state.messages[messageIndex].progressSteps = [];
      }
      const progressStep: H.ProgressItem = {
        step_key: displayKey,
        items: data.items ?? (itemText ? [{ text: itemText }] : []),
        tool_name: stepKey === 'archive_checkpoint' ? undefined : (data.tool_name ?? undefined),
        status: data.status,
      };
      if (stepKey === 'workflow_stage') {
        const sd = data.data as Record<string, unknown> | undefined;
        if (sd) {
          const message =
            typeof sd.message === 'string'
              ? sd.message
              : typeof sd.notify_message === 'string'
                ? sd.notify_message
                : undefined;
          if (message) {
            progressStep.notify_message = message;
          }
          const notifyLevel = sd.notify_level;
          if (notifyLevel === 'alert') {
            progressStep.status = 'error';
          } else if (notifyLevel === 'warn') {
            progressStep.status = 'warning';
          }
          if (typeof sd.notify_progress === 'number' && sd.notify_progress >= 0) {
            progressStep.notify_progress = sd.notify_progress;
            progressStep.progress_percent = sd.notify_progress;
          }
          if (typeof sd.notify_step_index === 'number') {
            progressStep.notify_step_index = sd.notify_step_index;
          }
          if (typeof sd.notify_total_steps === 'number') {
            progressStep.notify_total_steps = sd.notify_total_steps;
          }
          if (typeof sd.notify_category === 'string') {
            progressStep.notify_category = sd.notify_category;
          }
          if (typeof notifyLevel === 'string') {
            progressStep.notify_level = notifyLevel as 'info' | 'warn' | 'alert';
          }
          const stepIndex = sd.notify_step_index;
          const totalSteps = sd.notify_total_steps;
          if (typeof stepIndex === 'number' && typeof totalSteps === 'number' && totalSteps > 0) {
            progressStep.reason = `${stepIndex} / ${totalSteps}`;
          }
        }
      }
      if (archiveRestoreBlock) {
        progressStep.archive_restore_block = archiveRestoreBlock;
      }
      if (archiveRestoreActions.length > 0) {
        progressStep.archive_restore_actions = archiveRestoreActions;
      }
      if (archiveRestoreResult) {
        progressStep.archive_restore_result = archiveRestoreResult;
      }
      if (
        stepKey === 'archive_restore_blocked' ||
        stepKey === 'loop_guard_warn' ||
        stepKey === 'loop_guard_break' ||
        stepKey === 'crawl_task_progress' ||
        stepKey === 'workflow_stage'
      ) {
        const existingStep = state.messages[messageIndex].progressSteps!.find(
          (step) => step.step_key === displayKey,
        );
        if (existingStep) {
          Object.assign(existingStep, progressStep);
        } else {
          state.messages[messageIndex].progressSteps!.push(progressStep);
        }
      } else {
        state.messages[messageIndex].progressSteps!.push(progressStep);
      }
      if (stepKey === 'consensus_reference_done' && data.data) {
        const rd = data.data as Record<string, unknown>;
        if (!state.messages[messageIndex].consensusRefs) {
          state.messages[messageIndex].consensusRefs = [];
        }
        state.messages[messageIndex].consensusRefs!.push({
          model: String(rd.model ?? ''),
          success: Boolean(rd.success),
          elapsed: typeof rd.elapsed === 'number' ? rd.elapsed : 0,
          content: typeof rd.content === 'string' ? rd.content : undefined,
        });
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

  if (stepKey === 'loop_guard_break') {
    const breakMsg = data.items?.[0]?.text ?? 'Agent loop detected and stopped.';
    const { toast } = await import('@/lib/utils/toast');
    toast.error(breakMsg, { duration: 8000 });
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
