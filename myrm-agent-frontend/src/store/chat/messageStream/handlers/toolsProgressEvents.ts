/**
 * [POS]
 * Chat SSE event handler slice (toolsProgressEvents).
 */

import type { ToolApprovalRequest } from '@/store/chat/types';
import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import { buildToolApprovalRequest } from '@/lib/approval/buildToolApprovalRequest';
import { notifyIdleApproval } from '@/lib/approval/approvalAlertService';
import { getClarificationNotificationTitle, resolveClarificationFormFromEventData } from '../streamHelpers';
import * as H from './handlerDeps';

export async function toolsProgressEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, added, actions } = ctx;
  if (data.type === H.AgentEventType.TOOL_HEARTBEAT) {
    if (added) {
      actions.setMessages((state) => {
        const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
        if (messageIndex !== -1 && state.messages[messageIndex].progressSteps) {
          const steps = state.messages[messageIndex].progressSteps;
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
      fault_side: data.fault_side,
      progress_percent: data.progress_percent,
      skill_mutation_batch_id:
        typeof data.skill_mutation_batch_id === 'string' ? data.skill_mutation_batch_id : undefined,
    };

    if (data.error_category) {
      H.useChatStore.getState().addEnvironmentAlert(data.error_category);
    }

    if (data.step_key === 'swarm_fission') {
      const total = typeof data.count === 'number' ? data.count : 0;
      const status = data.status;
      const failedCount = typeof data.failed_count === 'number' ? data.failed_count : status === 'error' ? total : 0;
      const completedCount =
        typeof data.completed_count === 'number' ? data.completed_count : Math.max(0, total - failedCount);
      const partial =
        Boolean(data.partial_success) || status === 'partial_success' || (failedCount > 0 && completedCount > 0);

      if (status === 'running') {
        H.writeSubagentStore(ctx.state, (store) =>
          store.setFissionBatch({ active: true, total, completed: 0, failed: 0, partial: false }),
        );
      } else if (status === 'completed' || status === 'error' || status === 'partial_success') {
        H.writeSubagentStore(ctx.state, (store) =>
          store.setFissionBatch({ active: false, total, completed: completedCount, failed: failedCount, partial }),
        );

        // The strip belongs to the open chat, but failed workers are worth a warning wherever the stream runs.
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
    }

    if (!added) {
      actions.setMessages((state) => {
        state.messages.push({
          content: '',
          messageId: data.messageId,
          chatId: H.resolveStreamChatId(ctx.state),
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
          const toolCallId = stepItem.tool_call_id;
          const existing = toolCallId
            ? msg.progressSteps.find((s) => s.tool_call_id === toolCallId)
            : stepKey !== undefined && stepKey !== null
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
    const payload = data.data as {
      type?: string;
      message?: string;
      action_type?: string;
      reason?: string;
      url?: string;
      screenshot_base64?: string;
      is_managed?: boolean;
      actionRequests?: unknown[];
      reviewConfigs?: unknown[];
      extensions?: Record<string, unknown>;
    };

    // LangGraph tool HITL via stream_dispatcher emits approval_required-shaped payloads
    // with actionRequests — route them to the ToolApproval queue + dialog.
    if (Array.isArray(payload?.actionRequests) && payload.actionRequests.length > 0) {
      const rerouted = {
        ...data,
        type: H.AgentEventType.TOOL_APPROVAL_REQUEST,
        data: payload,
      } as unknown as typeof data;
      return toolsProgressEvents({ ...ctx, data: rerouted });
    }

    if (payload?.action_type === 'browser_takeover') {
      const { activateBrowserTakeover } = await import('@/store/useApprovalStore');
      activateBrowserTakeover({
        reason: String(payload.reason ?? ''),
        url: payload.url ? String(payload.url) : undefined,
        screenshot_base64: payload.screenshot_base64 ? String(payload.screenshot_base64) : undefined,
        messageId: typeof data.messageId === 'string' ? data.messageId : undefined,
        is_managed: payload.is_managed,
        auto_detect_completion: false,
      });
    }

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
        state.messages[messageIndex].progressSteps.push(cancelStep);
      }
    });
    actions.setLoading(false);
    return done(ctx);
  }

  if (data.type === H.AgentEventType.CLARIFICATION_REQUIRED) {
    const form = resolveClarificationFormFromEventData(data.data);
    const payload =
      data.data && typeof data.data === 'object' ? (data.data as unknown as Record<string, unknown>) : undefined;
    const actionMode = H.useChatStore.getState().actionMode;
    const source = typeof payload?.source === 'string' ? payload.source : undefined;
    const isResumeMode = source === 'deep_research' ? false : actionMode !== 'deep_research';
    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        state.messages[messageIndex].clarification = {
          answered: false,
          isResumeMode,
          title: form?.title ?? undefined,
          form,
        };
      } else {
        state.messages.push({
          content: '',
          messageId: data.messageId,
          chatId: H.resolveStreamChatId(ctx.state),
          role: 'assistant',
          createdAt: new Date(),
          clarification: {
            answered: false,
            isResumeMode,
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

    return done(ctx);
  }

  // 处理 tool_approval_request 事件：弹出审批对话框
  if (data.type === H.AgentEventType.TOOL_APPROVAL_REQUEST) {
    const payload = data.data as {
      actionRequests?: unknown[];
      reviewConfigs?: unknown[];
      extensions?: {
        approval?: { requestId?: string };
        timeout?: { seconds?: number; expiresAt?: number; behavior?: 'deny' | 'allow' };
        displayMode?: ToolApprovalRequest['displayMode'];
        workspaceRoot?: string;
      };
    };

    const actionRequests = Array.isArray(payload?.actionRequests) ? payload.actionRequests : [];
    if (actionRequests.length === 0) {
      console.warn('[TOOL_APPROVAL_REQUEST] missing actionRequests', payload);
      return done(ctx);
    }

    const { chatId: currentChatId, actionMode: currentActionMode } = H.useChatStore.getState();

    const extensions = payload.extensions ?? {};
    const approvalMeta = extensions.approval ?? {};
    const requestIdFallback = String(approvalMeta.requestId || data.messageId || `approval-${Date.now()}`);
    const normalizedExtensions = {
      timeout: {
        seconds: extensions.timeout?.seconds ?? 600,
        expiresAt: extensions.timeout?.expiresAt ?? Date.now() + 600_000,
        behavior: extensions.timeout?.behavior ?? 'deny',
      },
      displayMode: extensions.displayMode ?? 'approval',
      workspaceRoot: extensions.workspaceRoot,
      approval: { requestId: requestIdFallback },
    };

    const { reviewConfigs } = payload;
    const isBatch = actionRequests.length > 1;
    const batchId = isBatch ? requestIdFallback : null;

    for (let i = 0; i < actionRequests.length; i++) {
      const action = actionRequests[i] as {
        action: string;
        args: Record<string, unknown>;
        description: string;
        domains?: string[];
        ptc_annotations?: Record<string, boolean>;
        command_spans?: unknown;
        command_span_risks?: unknown;
        command_span_reasons?: unknown;
        plain_explanation?: unknown;
        execution_intent?: unknown;
        reviewerReason?: string;
      };
      const reviewConfig = reviewConfigs?.[i] as
        { domainApproval?: boolean; smartDenied?: boolean; hideAllowAlways?: boolean } | undefined;
      const requestId = isBatch ? `${batchId}_${i}` : requestIdFallback;

      const approvalRequest = buildToolApprovalRequest({
        action,
        reviewConfig,
        requestId,
        messageId: data.messageId,
        chatId: currentChatId ?? '',
        actionMode: currentActionMode,
        extensions: normalizedExtensions,
        batchId: batchId || undefined,
        batchIndex: isBatch ? i : undefined,
        batchSize: isBatch ? actionRequests.length : undefined,
        interruptId: data.interruptId,
      });
      H.useToolApprovalStore.getState().addRequest(approvalRequest);
    }

    // Idle approval notification: alert user if window is not active
    const allRequests = H.useToolApprovalStore.getState().queue;
    notifyIdleApproval(allRequests.slice(-actionRequests.length));

    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOLS_SNAPSHOT) {
    H.useToolsSnapshotStore.getState().setTools(data.data);
    return done(ctx);
  }

  return null;
}
