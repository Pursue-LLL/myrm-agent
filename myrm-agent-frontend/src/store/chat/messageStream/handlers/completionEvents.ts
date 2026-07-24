/**
 * [POS]
 * Chat SSE event handler slice (completionEvents).
 */

import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import * as H from "./handlerDeps";

export async function completionEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, recievedMessage, state, actions } = ctx;
  if (data.type === H.AgentEventType.GOAL_STATUS) {
    const { useGoalStore } = await import('@/store/chat/goals/useGoalStore');
    const goalState = H.normalizeGoalState(data.data);
    useGoalStore.getState().setActiveGoal(goalState);
    return done(ctx);
  }

  if (data.type === H.AgentEventType.FILE_MUTATION_FAILED) {
    const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex !== -1 && data.data?.files) {
      actions.setMessages((s) => {
        s.messages[messageIndex].fileMutationFailures = data.data.files;
      });
    }
    return done(ctx);
  }

  if (data.type === H.AgentEventType.MESSAGE_END) {
    if (data.goal_status) {
      const { useGoalStore } = await import('@/store/chat/goals/useGoalStore');
      useGoalStore.getState().setActiveGoal(H.normalizeGoalState(data.goal_status));
    }
    setTimeout(() => {
      actions.setMessages((state) => {
        let messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
        if (
          messageIndex === -1 &&
          (data.completion_status === 'budget_blocked' || Boolean(data.memory_brief_status))
        ) {
          state.messages.push({
            content: '',
            messageId: data.messageId,
            chatId: state.messages[0]?.chatId || '',
            role: 'assistant',
            createdAt: new Date(),
            completionStatus: data.completion_status === 'budget_blocked' ? 'budget_blocked' : undefined,
            memoryBriefStatus: data.memory_brief_status,
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

          if (data.stream_ttft_ms !== undefined) {
            state.messages[messageIndex].streamTtftMs = data.stream_ttft_ms;
          }

          if (data.wu_consumed !== undefined) {
            state.messages[messageIndex].wuConsumed = data.wu_consumed;
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

          if (data.memory_brief_snapshot_id) {
            state.messages[messageIndex].memoryBriefSnapshotId = data.memory_brief_snapshot_id;
          }

          if (data.memory_brief_status) {
            state.messages[messageIndex].memoryBriefStatus = data.memory_brief_status;
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

      void import('@/store/chat/pendingGapRetry').then(({ scheduleFlushPendingGapRetry }) => {
        scheduleFlushPendingGapRetry();
      });

      // Refresh per-chat workspace from API so Active Working Memory chips can open file
      // previews when FILE_DIFF is absent but the session workspace exists (silent=true).
      void import('@/services/chat').then(({ getChatDetail }) => {
        const chatId = H.useChatStore.getState().chatId;
        if (!chatId) return;
        void getChatDetail(chatId, true)
          .then((detail) => {
            const dir = detail.chat.workspace_dir;
            if (typeof dir === 'string' && dir.trim().length > 0) {
              H.useChatStore.getState().setWorkspaceDir(dir.trim());
            }
          })
          .catch(() => undefined);
      });
    }, 50);

    if (H.useConfigStore.getState().enableCompletionSound) {
      H.playCompletionSound();
    }

    if (H.useConfigStore.getState().enableWebNotifications) {
      const lang = typeof document !== 'undefined' ? document.documentElement.lang : 'en';
      const title = lang.startsWith('zh') ? 'Agent 回复已完成' : 'Agent response completed';
      import('@/services/notification').then(({ notificationService }) => {
        notificationService.notify(title, { fallbackToToast: false });
      });
    }

    // Release the processing lock when message ends successfully
    H.useToolApprovalStore.getState().unmarkProcessing(data.messageId);

    // Clear stale plan steps that are still pending/in_progress after turn ends
    void import('@/store/chat/goals/usePlanStore').then(({ usePlanStore }) => {
      usePlanStore.getState().clearActivePlan();
    });

    // Passive progression milestone detection
    void import('@/lib/progression/tryMarkMilestone').then(({ tryMarkMilestone }) => {
      tryMarkMilestone('first_chat');
      const msg = state.messages[state.messages.length - 1];
      if (msg?.toolCalls && msg.toolCalls.length > 0) {
        tryMarkMilestone('first_tool_use');
        if (msg.toolCalls.some((tc) => tc.toolName === 'delegate_to_agent')) {
          tryMarkMilestone('first_remote_takeover');
        }
      }
    });
  }

  return null;
}
