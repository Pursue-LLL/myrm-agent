import type { StreamCtx } from '../streamContext';
import { AgentEventType } from '../../types/agentStream/part1';
import type { StatusStreamEvent } from '../../types/agentStream/part2';
import * as H from './handlerDeps';

function requireStatusStreamEvent(event: StreamCtx['data']): StatusStreamEvent {
  if (event.type !== AgentEventType.STATUS) {
    throw new Error(`Expected status SSE event, received ${event.type}`);
  }
  return event;
}

const PROGRESS_STEP_KEYS = new Set([
  'model_failover',
  'model_failover_unconfigured',
  'safety_fallback_unconfigured',
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
  'thinking_signature_recovery',
  'tool_history_recovery',
  'image_shrink_recovery',
  'long_context_tier_recovery',
  'allowed_tools_rejected_recovery',
  'ux_warning_truncated',
  'turn_prewarm_agent',
  'turn_prewarm_agent_clear',
  'turn_prewarm_memory',
  'turn_prewarm_memory_clear',
  'wiki_knowledge_lane',
  'wiki_knowledge_lane_clear',
  'consensus_active',
  'consensus_reference_done',
  'moa_overlay_active',
  'moa_ref_done',
  'moa_overlay_skipped',
  'workflow_init',
  'workflow_planning',
  'workflow_execution',
  'workflow_stage',
  'loop_guard_warn',
  'loop_guard_break',
  'waiting_for_turn',
]);

export function isStatusProgressStep(stepKey: string | undefined): boolean {
  return stepKey !== undefined && PROGRESS_STEP_KEYS.has(stepKey);
}

/** Recovery STATUS can arrive before the first MESSAGE chunk; ensure a placeholder exists. */
function isEarlyRecoveryProgressStep(stepKey: string): boolean {
  return (
    stepKey === 'model_failover' ||
    stepKey === 'model_failover_unconfigured' ||
    stepKey === 'safety_fallback_active' ||
    stepKey === 'safety_fallback_unconfigured' ||
    stepKey === 'transient_retry' ||
    stepKey === 'waiting_for_turn'
  );
}

export async function applyStatusProgressStep(ctx: StreamCtx, stepKey: string): Promise<void> {
  const data = requireStatusStreamEvent(ctx.data);
  const { actions } = ctx;
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
  if (stepKey === 'context_compaction' && data.data?.phase) {
    const phase = data.data.phase as string;
    if (phase !== 'active') {
      displayKey = `context_compaction_${phase}`;
    }
  }
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
      : stepKey === 'context_compaction' && data.data?.phase
        ? _formatCompactionItemText(data.data as Record<string, unknown>)
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
                  : stepKey === 'moa_overlay_active' && data.data?.reference_models
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
    if (
      messageIndex === -1 &&
      (isMediaAnalysis || isArchiveRestoreStatus || isEarlyRecoveryProgressStep(stepKey))
    ) {
      if (isMediaAnalysis || isArchiveRestoreStatus) {
        state.messages.push({
          content: '',
          messageId: data.messageId,
          chatId: state.messages[0]?.chatId || '',
          role: 'assistant',
          progressSteps: [],
          mediaAnalysisStatus: isMediaAnalysis ? (stepKey as 'analyzing_image' | 'analyzing_video') : null,
          visionBackend:
            isMediaAnalysis &&
            typeof (data.data as Record<string, unknown> | undefined)?.vision_backend === 'string'
              ? ((data.data as Record<string, unknown>).vision_backend as string)
              : null,
          createdAt: new Date(),
          metadata: data.metadata,
        });
        messageIndex = state.messages.length - 1;
      } else {
        messageIndex = H.ensureAssistantStreamMessage(
          state.messages,
          data.messageId,
          state.messages[0]?.chatId || '',
        );
      }
      if (messageIndex !== -1) {
        ctx.added = true;
      }
    }

    if (messageIndex !== -1) {
      if (!state.messages[messageIndex].progressSteps) {
        state.messages[messageIndex].progressSteps = [];
      }
      const compactionPhase = stepKey === 'context_compaction' ? (data.data as Record<string, unknown> | undefined)?.phase : undefined;
      const progressStep: H.ProgressItem = {
        step_key: displayKey,
        items: data.items ?? (itemText ? [{ text: itemText }] : []),
        tool_name: stepKey === 'archive_checkpoint' ? undefined : (data.tool_name ?? undefined),
        status:
          stepKey === 'waiting_for_turn'
            ? undefined
            : compactionPhase === 'timeout' || compactionPhase === 'circuit_open'
              ? 'warning'
              : compactionPhase === 'completed'
                ? 'complete'
                : data.status,
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
        stepKey === 'context_compaction' ||
        stepKey === 'loop_guard_warn' ||
        stepKey === 'loop_guard_break' ||
        stepKey === 'workflow_stage' ||
        stepKey === 'model_failover' ||
        stepKey === 'safety_fallback_active'
      ) {
        const existingStep = state.messages[messageIndex].progressSteps!.find(
          (step) =>
            stepKey === 'model_failover'
              ? step.step_key?.startsWith('model_failover')
              : stepKey === 'context_compaction'
                ? step.step_key?.startsWith('context_compaction')
                : step.step_key === displayKey,
        );
        if (existingStep) {
          const isFailoverStep =
            stepKey === 'model_failover' || stepKey === 'safety_fallback_active';
          const firstItem = existingStep.items?.[0];
          const existingHasFullLabel =
            isFailoverStep &&
            typeof firstItem === 'object' &&
            firstItem !== null &&
            'text' in firstItem &&
            typeof firstItem.text === 'string' &&
            firstItem.text.includes('→');
          if (existingHasFullLabel) {
            Object.assign(existingStep, { ...progressStep, items: existingStep.items });
          } else {
            Object.assign(existingStep, progressStep);
          }
        } else {
          state.messages[messageIndex].progressSteps!.push(progressStep);
        }
      } else {
        state.messages[messageIndex].progressSteps!.push(progressStep);
      }
      if (
        (stepKey === 'consensus_active' || stepKey === 'moa_overlay_active') &&
        data.data?.reference_models
      ) {
        const models = data.data.reference_models as string[];
        if (models.length > 0) {
          state.messages[messageIndex].consensusRefsExpected = models.length;
        }
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
      if (stepKey === 'moa_ref_done' && data.data) {
        const rd = data.data as Record<string, unknown>;
        if (!state.messages[messageIndex].consensusRefs) {
          state.messages[messageIndex].consensusRefs = [];
        }
        state.messages[messageIndex].consensusRefs!.push({
          model: String(rd.model ?? ''),
          success: Boolean(rd.success),
          elapsed: typeof rd.elapsed === 'number' ? rd.elapsed : 0,
          content: typeof rd.content === 'string' ? rd.content : undefined,
          source: 'moa_overlay',
        });
      }
      if (isMediaAnalysis) {
        state.messages[messageIndex].mediaAnalysisStatus = stepKey as 'analyzing_image' | 'analyzing_video';
        const visionBackend = (data.data as Record<string, unknown> | undefined)?.vision_backend;
        if (typeof visionBackend === 'string' && visionBackend.length > 0) {
          state.messages[messageIndex].visionBackend = visionBackend;
        }
      }
    }
  });
  if (
    (stepKey === 'context_pruned' ||
      (stepKey === 'context_compaction' &&
        (data.data as Record<string, unknown> | undefined)?.phase === 'completed')) &&
    typeof data.tokens_saved === 'number' &&
    data.tokens_saved > 0
  ) {
    const snapshotPath =
      typeof data.snapshot_path === 'string'
        ? data.snapshot_path
        : typeof (data.data as Record<string, unknown> | undefined)?.snapshot_path === 'string'
          ? ((data.data as Record<string, unknown>).snapshot_path as string)
          : undefined;
    const { default: useChatStore } = await import('@/store/useChatStore');
    const chatId = useChatStore.getState().chatId;
    if (chatId) {
      await useChatStore.getState().refreshCompactionState(chatId, {
        tokensSaved: data.tokens_saved,
        snapshotPath,
      });
    }
  }
  if (stepKey === 'archive_restore_blocked') {
    const message = archiveRestoreBlock?.message ?? 'Archived context restore was blocked.';
    const { toast } = await import('@/lib/utils/toast');
    toast.warning(message, { duration: 6000 });
  }

  if (stepKey === 'loop_guard_break') {
    const firstItem = data.items?.[0];
    const breakMsg =
      firstItem && typeof firstItem === 'object' && firstItem !== null && 'text' in firstItem
        ? String((firstItem as { text: string }).text)
        : 'Agent loop detected and stopped.';
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

  if (stepKey === 'moa_overlay_skipped') {
    const payloadData = data.data as Record<string, unknown> | undefined;
    const reason = typeof payloadData?.reason === 'string' ? payloadData.reason : '';
    const { showI18nToast } = await import('@/services/i18nToastService');
    const reasonKey =
      reason === 'no_reference_configs'
        ? 'settings.defaultModel.moaPreset.skippedNoReferenceConfigs'
        : reason === 'no_reference_llms'
          ? 'settings.defaultModel.moaPreset.skippedNoReferenceLlms'
          : reason === 'budget_pressure'
            ? 'settings.defaultModel.moaPreset.skippedBudgetPressure'
            : reason === 'insufficient_refs'
              ? 'settings.defaultModel.moaPreset.skippedInsufficientRefs'
              : 'settings.defaultModel.moaPreset.skippedGeneric';
    showI18nToast(reasonKey, undefined, { type: 'warning', duration: 8000 });
  }

  if (stepKey === 'model_failover_unconfigured' || stepKey === 'safety_fallback_unconfigured') {
    const { showI18nToast } = await import('@/services/i18nToastService');
    const { SETTINGS_AGENTS_LOADOUT_PATH, SETTINGS_DEFAULT_MODEL_PATH } = await import(
      '@/lib/skills/integrationOAuthDisplay'
    );
    const settingsPath =
      stepKey === 'safety_fallback_unconfigured'
        ? SETTINGS_AGENTS_LOADOUT_PATH
        : SETTINGS_DEFAULT_MODEL_PATH;
    showI18nToast(`progressSteps.${stepKey}`, undefined, {
      type: 'warning',
      duration: 8000,
      action: {
        label: 'chat.configError.goToSettings',
        onClick: () => {
          if (typeof window !== 'undefined') {
            window.location.assign(settingsPath);
          }
        },
      },
    });
  }
}

function _formatCompactionItemText(data: Record<string, unknown>): string {
  const phase = data.phase as string;
  const elapsedS = typeof data.elapsed_s === 'number' ? data.elapsed_s : 0;
  const tokensSaved = typeof data.tokens_saved === 'number' ? data.tokens_saved : 0;

  switch (phase) {
    case 'active':
      return `(${elapsedS}s)`;
    case 'timeout':
      return `(${elapsedS}s)`;
    case 'circuit_open':
      return '';
    case 'fallback':
      return '';
    case 'completed':
      return tokensSaved > 0 ? `(Tokens saved: ${tokensSaved})` : '';
    default:
      return '';
  }
}
