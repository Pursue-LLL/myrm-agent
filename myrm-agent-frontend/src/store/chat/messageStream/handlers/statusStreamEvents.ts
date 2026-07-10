/**
 * [POS]
 * Chat SSE event handler slice (statusStreamEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import * as H from "./handlerDeps";

export async function statusStreamEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;
  if (data.type === H.AgentEventType.STATUS) {
    const stepKey = data.step_key;

    // Emit pet-status-event for the sprite overlay state machine
    if (typeof window !== 'undefined' && stepKey) {
      window.dispatchEvent(new CustomEvent('pet-status-event', { detail: { step_key: stepKey } }));
    }
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
      stepKey === 'consensus_reference_done' ||
      stepKey === 'workflow_init' ||
      stepKey === 'workflow_planning' ||
      stepKey === 'workflow_execution' ||
      stepKey === 'workflow_stage' ||
      stepKey === 'loop_guard_warn' ||
      stepKey === 'loop_guard_break' ||
      stepKey === 'crawl_task_progress'
    ) {
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
                      : (stepKey === 'workflow_init' || stepKey === 'workflow_planning' || stepKey === 'workflow_execution' || stepKey === 'workflow_stage') && typeof data.data?.message === 'string'
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

    if (stepKey === 'cache_break') {
      const sd = data.data as Record<string, unknown> | undefined;
      const reason = typeof sd?.reason === 'string' ? sd.reason : '';
      const suggestedActions = typeof sd?.suggested_actions === 'string' ? sd.suggested_actions : '';
      if (reason) {
        actions.setMessages((state) => {
          const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
          if (idx !== -1) {
            state.messages[idx].cacheBreakReason = reason;
            if (suggestedActions) {
              state.messages[idx].cacheSuggestedActions = suggestedActions;
            }
          }
        });
        const notifyEnabled = H.useConfigStore.getState().enableCacheBreakNotification;
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
          const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
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
          const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
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
          const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
          if (idx !== -1 && state.messages[idx].clarification) {
            state.messages[idx].clarification!.answered = true;
          }
        });
      }

      if (sd.phase === 'plan_confirm') {
        actions.setMessages((state) => {
          const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
          if (idx === -1) return;
          if (sd.status === 'waiting' && typeof sd.plan === 'string') {
            state.messages[idx].planConfirmation = {
              plan: sd.plan as string,
              status: 'waiting',
            };
          } else if (sd.status === 'resolved') {
            if (state.messages[idx].planConfirmation) {
              state.messages[idx].planConfirmation!.status = sd.modified ? 'edited' : 'confirmed';
            }
          }
        });
      }

      if (sd.phase === 'explore' && sd.status === 'complete' && sd.has_context) {
        actions.setMessages((state) => {
          const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
          if (idx !== -1) {
            const steps = state.messages[idx].progressSteps;
            if (steps && steps.length > 0) {
              const lastStep = steps[steps.length - 1];
              const chars = typeof sd.context_chars === 'number' ? sd.context_chars : 0;
              lastStep.items = [{ text: `Found ${Math.round(chars / 1000)}k chars of relevant local knowledge` }];
            }
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
              const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
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
            const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
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

      if (sd.phase === 'research' && typeof sd.cycle === 'number') {
        actions.setMessages((state) => {
          const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
          if (idx !== -1) {
            const steps = state.messages[idx].progressSteps;
            if (steps && steps.length > 0) {
              const lastStep = steps[steps.length - 1];
              const cycle = sd.cycle as number;
              const maxCycles = typeof sd.max_cycles === 'number' ? (sd.max_cycles as number) : 0;
              const costUsd = typeof sd.current_cost_usd === 'number' ? (sd.current_cost_usd as number) : 0;
              const cycleLabel = maxCycles > 0 ? `Cycle ${cycle}/${maxCycles}` : `Cycle ${cycle}`;
              if (costUsd > 0) {
                lastStep.items = [{ text: `${cycleLabel} — $${costUsd.toFixed(2)}` }];
              } else {
                lastStep.items = [{ text: cycleLabel }];
              }
            }
          }
        });
      }

      if (sd.phase === 'research' && typeof sd.budget_event === 'string') {
        actions.setMessages((state) => {
          const idx = H.findAssistantMessageIndex(state.messages, data.messageId);
          if (idx !== -1) {
            const steps = state.messages[idx].progressSteps;
            if (steps && steps.length > 0) {
              const lastStep = steps[steps.length - 1];
              const costUsd = typeof sd.current_cost_usd === 'number' ? (sd.current_cost_usd as number) : 0;
              const budgetUsd = typeof sd.budget_usd === 'number' ? (sd.budget_usd as number) : 0;
              const percentUsed = typeof sd.percent_used === 'number' ? (sd.percent_used as number) : 0;
              const isExceeded = sd.budget_event === 'exceeded';
              const costText = budgetUsd > 0 ? ` ($${costUsd.toFixed(2)}/$${budgetUsd.toFixed(2)})` : '';
              const warningText = isExceeded
                ? `Budget exceeded${costText}`
                : `Budget ${Math.round(percentUsed)}% used${costText}`;
              if (!lastStep.items || !Array.isArray(lastStep.items)) {
                lastStep.items = [];
              }
              (lastStep.items as { text: string }[]).push({ text: warningText });
              lastStep.status = isExceeded ? 'warning' : undefined;
            }
          }
        });
      }
    }

    return done(ctx);
  }


  return null;
}
