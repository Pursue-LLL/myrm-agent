/**
 * [POS]
 * Chat SSE event handler slice (toolsProgressEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import { buildToolApprovalRequest } from "@/lib/approval/buildToolApprovalRequest";
import { notifyIdleApproval, clearAllNotifications } from "@/lib/approval/approvalAlertService";
import {
  getClarificationNotificationTitle,
  resolveClarificationFormFromEventData,
} from "../streamHelpers";
import * as H from "./handlerDeps";

export async function toolsProgressEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, added, actions } = ctx;
  if (data.type === H.AgentEventType.TOOL_PROGRESS) {
    const { tool, progress } = data as { tool: string; progress: { done: number; total: number; failed: number } };
    if (progress && added) {
      const stepKey = `tool_progress:${tool}`;
      const pct = progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0;
      actions.setMessages((state) => {
        const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex === -1) return;
        const msg = state.messages[messageIndex];
        if (!msg.progressSteps) {
          msg.progressSteps = [];
        }
        const existing = msg.progressSteps.find((s) => s.step_key === stepKey);
        const status: H.ProgressItem['status'] = progress.failed > 0 ? 'warning' : 'success';
        const patch: Partial<H.ProgressItem> = {
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
          msg.progressSteps.push(patch as H.ProgressItem);
        }
      });
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOL_HEARTBEAT) {
    if (added) {
      actions.setMessages((state) => {
        const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
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

  if (data.type === H.AgentEventType.TASKS_STEPS) {
    // 构建步骤对象（使用新的 step_key 结构）
    const stepStatus = H.mapTaskStepStatus(data.status);
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
      H.useChatStore.getState().addEnvironmentAlert(data.error_category);
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
      ctx.added = true;
    } else {
      actions.setMessages((state) => {
        const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex !== -1) {
          const msg = state.messages[messageIndex];
          if (!msg.progressSteps) {
            msg.progressSteps = [];
          }
          const stepKey = stepItem.step_key;
          const existing =
            stepKey !== undefined && stepKey !== null
              ? msg.progressSteps.find((s) => s.step_key === stepKey)
              : undefined;
          if (existing) {
            Object.assign(existing, stepItem);
          } else {
            msg.progressSteps.push(stepItem);
          }
        } else {
          console.warn('Could not find assistant message with messageId:', data.messageId);
        }
      });
    }
  }

  if (data.type === H.AgentEventType.SOURCES) {
    const newSources = data.data;

    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex === -1) {
        return;
      }

      const existingSources = state.messages[messageIndex].sources || [];
      state.messages[messageIndex].sources = H.mergeMessageSources(existingSources, newSources);

      if (!state.messageAppeared) {
        state.messageAppeared = true;
      }
    });
  }

  if (data.type === H.AgentEventType.APPROVAL_REQUIRED) {
    const payload = data.data as { type: string; message?: string };
    const cancelText = payload?.message || '任务已暂停：需要人工介入 (Task paused for human intervention)';

    actions.setMessages((state) => {
      const cancelStep = {
        step_key: 'approval_required',
        items: [{ text: cancelText }],
        status: 'error' as const,
      };
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        state.messages[messageIndex].progressSteps!.push(cancelStep);
      }
    });
    actions.setLoading(false);
    // Override the CELEBRATING animation from setLoading(false) with approval waiting.
    // setTimeout ensures this runs after React processes the loading state change.
    if (typeof window !== 'undefined') {
      setTimeout(() => window.dispatchEvent(new CustomEvent('pet-status-event', { detail: { step_key: 'approval_waiting' } })), 0);
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.CLARIFICATION_REQUIRED) {
    const form = resolveClarificationFormFromEventData(data.data);
    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        state.messages[messageIndex].clarification = {
          answered: false,
          isResumeMode: true,
          title: form?.title ?? undefined,
          form,
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
            form,
          },
        });
        ctx.added = true;
      }
    });
    actions.setLoading(false);

    if (H.useConfigStore.getState().enableWebNotifications) {
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const title = getClarificationNotificationTitle(lang);
      const body = form?.title ?? undefined;
      import('@/services/notification').then(({ notificationService }) => {
        notificationService.notify(title, { body, fallbackToToast: false });
      });
    }

    if (typeof window !== 'undefined') {
      setTimeout(() => window.dispatchEvent(new CustomEvent('pet-status-event', { detail: { step_key: 'approval_waiting' } })), 0);
    }
    return done(ctx);
  }

  // 处理 tool_approval_request 事件：弹出审批对话框
  if (data.type === H.AgentEventType.TOOL_APPROVAL_REQUEST) {
    const payload = data.data;

    const { chatId: currentChatId, actionMode: currentActionMode } = H.useChatStore.getState();

    // Parse standard LangChain HITL payload structure (supports batch approval)
    const { actionRequests, reviewConfigs, extensions } = payload;
    const isBatch = actionRequests.length > 1;
    const batchId = isBatch ? extensions.approval.requestId : null;

    // Create approval requests for all actions in the batch
    for (let i = 0; i < actionRequests.length; i++) {
      const action = actionRequests[i];
      const reviewConfig = reviewConfigs?.[i];
      const requestId = isBatch ? `${batchId}_${i}` : extensions.approval.requestId;

      const approvalRequest = buildToolApprovalRequest({
        action,
        reviewConfig,
        requestId,
        messageId: data.messageId,
        chatId: currentChatId!,
        actionMode: currentActionMode,
        extensions,
        batchId: batchId || undefined,
        batchIndex: isBatch ? i : undefined,
        batchSize: isBatch ? actionRequests.length : undefined,
      });
      H.useToolApprovalStore.getState().addRequest(approvalRequest);
    }

    // Idle approval notification: alert user if window is not active
    const allRequests = H.useToolApprovalStore.getState().queue;
    notifyIdleApproval(allRequests.slice(-actionRequests.length));

    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('pet-status-event', { detail: { step_key: 'approval_waiting' } }));
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.APPROVAL_PROCESSED) {
    H.useToolApprovalStore.getState().removeRequestsByMessageId(data.messageId);
    const remaining = H.useToolApprovalStore.getState().queue;
    if (remaining.length === 0) clearAllNotifications();
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('pet-status-event', { detail: { step_key: 'approval_released' } }));
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOLS_SNAPSHOT) {
    H.useToolsSnapshotStore.getState().setTools(data.data);
    return done(ctx);
  }

  if (data.type === H.AgentEventType.CORRECTION_LEARNED) {
    const payload = data as { summaries?: string[]; data?: { summaries?: string[] } };
    const summaries = payload.summaries ?? payload.data?.summaries;
    if (summaries && summaries.length > 0) {
      import('@/lib/utils/toast').then(({ toast }) => {
        toast.success(summaries.join('; '), {
          duration: 6_000,
          dismissible: true,
        });
      });
      if (typeof window !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('pet-status-event', {
            detail: { step_key: 'correction_learned', message: summaries.join('; ') },
          }),
        );
      }
    }
    return done(ctx);
  }

  return null;
}
