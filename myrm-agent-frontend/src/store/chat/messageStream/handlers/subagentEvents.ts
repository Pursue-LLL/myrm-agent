/**
 * [POS]
 * Chat SSE event handler slice (subagentEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import * as H from "./handlerDeps";

export async function subagentEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;
  if (data.type === H.AgentEventType.SUBAGENT_START) {
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
        effective_model: data.data.effective_model,
        startedAt: Date.now(),
      });
    });

    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
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
    return done(ctx);
  }

  if (data.type === H.AgentEventType.SUBAGENT_PROGRESS) {
    // Dispatch to dedicated subagent store for Dashboard
    import('@/store/chat/useSubagentStore').then(({ useSubagentStore }) => {
      const pd = data.data;
      const progressPercent = Math.round((pd.progress ?? 0) * 100);
      const taskId = pd.task_id || pd.agent_instance || '';
      if (taskId) {
        const store = useSubagentStore.getState();
        store.updateProgress(taskId, progressPercent, pd.current_step);
        const tokenUsage =
          (pd.token_usage as Record<string, unknown> | undefined) ??
          (typeof pd.current_tokens === 'number' && pd.current_tokens > 0
            ? { total_tokens: pd.current_tokens }
            : undefined);
        if (tokenUsage && typeof tokenUsage.total_tokens === 'number' && tokenUsage.total_tokens > 0) {
          store.upsertNode({
            task_id: taskId,
            token_usage: tokenUsage as Record<string, number | string | boolean | null>,
          });
        }
        if (typeof pd.eta_seconds === 'number' && pd.eta_seconds > 0) {
          store.updateEstimate(taskId, pd.eta_seconds);
        }
        if (pd.current_step) {
          store.appendStream(taskId, {
            kind: 'progress',
            text: pd.current_step,
            timestamp: Date.now(),
          });
        }
      }
    });

    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
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
    return done(ctx);
  }

  if (data.type === H.AgentEventType.SUBAGENT_LOG) {
    import('@/store/chat/useSubagentStore').then(({ useSubagentStore }) => {
      const logData = data.data;
      const taskId = logData.task_id || logData.agent_instance || '';
      if (taskId) {
        const level = logData.level || 'INFO';
        const kind = level === 'ERROR' ? 'error' as const
          : logData.tool_name ? 'tool' as const
          : level === 'DEBUG' ? 'thinking' as const
          : 'progress' as const;
        useSubagentStore.getState().appendStream(taskId, {
          kind,
          text: logData.tool_name
            ? `${logData.tool_name}${logData.message ? `: ${logData.message}` : ''}`
            : logData.message || '',
          isError: level === 'ERROR',
          timestamp: Date.now(),
          durationMs: logData.duration_ms,
        });
      }
    });

    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
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
    return done(ctx);
  }

  if (data.type === H.AgentEventType.SUBAGENT_COMPLETION) {
    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
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
      H.useChatStore.getState().triggerSubagentPrompt(data.messageId);
    }

    return done(ctx);
  }

  if (data.type === H.AgentEventType.SUBAGENT_STALE) {
    import('@/store/chat/useSubagentStore').then(({ useSubagentStore }) => {
      const payload = data.data;
      const taskId = payload?.task_id;
      if (taskId) {
        useSubagentStore.getState().markStale(
          taskId,
          payload.stale_duration_seconds ?? 0,
          payload.wasted_tokens ?? 0,
        );
      }
    });

    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }
        const durationMin = Math.round((data.data?.stale_duration_seconds ?? 0) / 60);
        state.messages[messageIndex].progressSteps!.push({
          step_key: 'subagent_stale',
          tool_name: data.data?.agent_type,
          items: [{ text: `Subagent stalled (no progress for ${durationMin}min)` }],
        });
      }
    });
    return done(ctx);
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
          effective_model: payload.effective_model,
          token_usage: payload.token_usage,
        });
        store.completeNode(taskId, H.normalizeSubagentStatus(payload.status), payload.error);
      }
    });
    return done(ctx);
  }

  if (data.type === H.AgentEventType.FISSION_TOPOLOGY) {
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
    return done(ctx);
  }

  if (data.type === H.AgentEventType.VERIFICATION_VERDICT) {
    const vd = data.data as {
      passed: boolean;
      summary: string;
      confidence: string;
      round: number;
      max_rounds: number;
      worker_type: string;
      has_workspace_diff: boolean;
      findings: Array<{ severity: string; description: string }>;
    };

    actions.setMessages((state) => {
      const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
      if (messageIndex !== -1) {
        if (!state.messages[messageIndex].progressSteps) {
          state.messages[messageIndex].progressSteps = [];
        }

        const statusLabel = vd.passed ? '[PASS]' : '[FAIL]';
        const confidenceLabel = vd.confidence === 'HIGH' ? '' : ` [${vd.confidence}]`;
        const diffLabel = vd.has_workspace_diff ? ' (with diff)' : '';
        const headerText = `Verification ${statusLabel} (${vd.round}/${vd.max_rounds})${confidenceLabel}${diffLabel}`;

        const items: Array<{ text: string }> = [{ text: headerText }];
        if (vd.summary) {
          items.push({ text: vd.summary });
        }
        for (const f of (vd.findings || []).slice(0, 3)) {
          items.push({ text: `[${f.severity}] ${f.description}` });
        }

        state.messages[messageIndex].progressSteps!.push({
          step_key: 'verification_verdict',
          tool_name: vd.worker_type,
          items,
        });
      }
    });
    return done(ctx);
  }

  if (data.type === H.AgentEventType.TEAMMATE_MESSAGE) {
    const chatId = H.useChatStore.getState().chatId;
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
    return done(ctx);
  }

  return null;
}
