/**
 * [INPUT]
 * ./streamConsumer::executeStreamWithRetry (POS: Agent-stream turn orchestration with retry)
 * ./sendLifecycle (POS: Send lifecycle pure helpers)
 * ./modelSelection::validateChatModelConfig (POS: Model slot resolution)
 * ./searchRequirement::requiresSearchService (POS: Search-service prerequisite of a turn)
 * @/store/config/searchServiceReady::checkSearchServiceReady (POS: The one gate in front of every entry into the Quick Search mode)
 *
 * [OUTPUT]
 * sendMessage: Submit user input into the chat stream lifecycle (sendBlocked toasts for a busy chat, missing chat, kanban board guard, processing lock; the search setup prompt when the turn needs a search service the account lacks); resolves whether the turn was dispatched (false when refused locally, by the server with a non-retryable HTTP error, or because the workspace stream was not ready before the first request; an ordinary send tells the user why, a resume with `resumeValue` does not and its store wrapper throws instead), a server busy refusal retracts the optimistic bubble, a text a risk rule holds retracts it too and resolves false with only the risk notice (no failure notice), a resume that someone else (the timeout or another device) already resolved rejects with `ApprovalAlreadyResolvedError` without a failure notice, queued messages send their own attachments, a turn that ends after a newer one took over leaves the turn state (loading, Stop handle, request id, attachments) to the newer one.
 *
 * [POS]
 * Chat send orchestration: guards, optimistic user bubble, stream lifecycle and failure handling of one turn.
 */

import { resolveKanbanSendBlockReason } from '@/lib/kanban/kanbanChatBoard';
import { peekMigrationBoundProjectId } from '@/lib/migrationChatHandoff';
import { resolveE2eApiBase } from '@/lib/deploy-mode';
import { isArchiveRestoreActionInvalidError } from '@/lib/utils/networkResilience';
import { showI18nToast } from '@/services/i18nToastService';
import type {
  AgentConfig,
  ArchiveRestoreAction,
  QueuedAttachments,
  TurnCapabilityTerminalTelemetry,
} from '@/store/chat/types';
import useCompanionStore from '../useCompanionStore';
import useToolApprovalStore from '../useToolApprovalStore';
import useWorkspaceStore, { type PaneConfig } from '../useWorkspaceStore';
import type { ChatActionsMethods, ChatActionsState } from './chatActions';
import { resolveKanbanProjectScope } from './kanbanProjectScope';
import { validateChatModelConfig } from './modelSelection';
import { requiresSearchService } from './searchRequirement';
import { isHeldByOtherTurn, resolveRequestState, retractUserBubble, sendFailureToast } from './sendLifecycle';
import { createSmartUpdater } from './smartUpdater';
import { executeStreamWithRetry } from './streamConsumer';
import {
  AgentBusyError,
  ApprovalAlreadyResolvedError,
  RequestRefusedError,
  RiskBlockedError,
  isTransientNetworkError,
} from './streamErrors';

/**
 * 发送消息主函数
 */
export const sendMessage = async (
  input: string,
  messageId: string | undefined,
  state: ChatActionsState,
  actions: ChatActionsMethods,
  getCurrentSessionMessageId: () => string,
  allocateNewSessionMessageId: () => string,
  resumeValue?: unknown,
  archiveRestoreActions?: ArchiveRestoreAction[],
  agentConfigOverride?: AgentConfig | null,
  shouldRecordWikiQuerySuccess: boolean = false,
  turnCapabilityTelemetry?: TurnCapabilityTerminalTelemetry,
  queuedAttachments?: QueuedAttachments,
): Promise<boolean> => {
  const isHitlResume = resumeValue !== undefined;

  if (state.loading && !isHitlResume) {
    showI18nToast('chat.sendBlocked.title', undefined, {
      descriptionKey: 'chat.sendBlocked.busyDescription',
      type: 'warning',
      duration: 3000,
    });
    return false;
  }

  if (!state.chatId?.trim()) {
    showI18nToast('chat.sendBlocked.title', undefined, {
      descriptionKey: 'chat.sendBlocked.noChatDescription',
      type: 'warning',
      duration: 5000,
    });
    return false;
  }

  if (state.actionMode === 'agent' && state.currentBuiltinTools.includes('kanban')) {
    const migrationBoundProjectId = peekMigrationBoundProjectId();
    const kanbanProjectScope = resolveKanbanProjectScope(migrationBoundProjectId);
    const kanbanBlockReason = await resolveKanbanSendBlockReason(state.currentBuiltinTools, kanbanProjectScope);
    if (kanbanBlockReason) {
      showI18nToast('chat.sendBlocked.title', undefined, {
        descriptionKey:
          kanbanBlockReason === 'no_boards'
            ? 'chat.sendBlocked.kanbanNoBoardDescription'
            : 'chat.sendBlocked.kanbanNeedBoardDescription',
        type: 'warning',
        duration: 5000,
      });
      return false;
    }
  }

  const requestMessageId = messageId ?? (isHitlResume ? getCurrentSessionMessageId() : allocateNewSessionMessageId());
  const requestState = resolveRequestState(state, agentConfigOverride, queuedAttachments);

  // 防重锁：检查该消息是否正在被处理（通过按钮审批或其他文本审批）
  if (!isHitlResume && useToolApprovalStore.getState().isProcessing(requestMessageId)) {
    showI18nToast('chat.sendBlocked.title', undefined, {
      descriptionKey: 'chat.sendBlocked.processingDescription',
      type: 'warning',
      duration: 4000,
    });
    return false;
  }

  // 标记为正在处理，防止并发
  useToolApprovalStore.getState().markProcessing(requestMessageId);

  let pushedUserBubble = false;
  let dispatched = false;
  // The abort handle identifies this turn: whoever holds it owns the shared turn state until the turn ends.
  const abortController = new AbortController();

  try {
    // 搜索服务检查：快速搜索模式与手选「快速搜索」智能体靠搜索服务作答，服务端不放行无搜索服务的回合，
    // 所以发送前拦截并引导配置；判定交给 checkSearchServiceReady（限时等搜索服务同步，取不到时放行由服务端裁决），
    // 免得把云端刷新后还在后台加载的已配置账号误判为未配置。通用 agent 未配置 web_search 时由
    // stream preflight 的 SSE capability_gap 通知（避免与 client toast 重复）。
    if (requiresSearchService(requestState.actionMode, requestState.agentConfig)) {
      const { checkSearchServiceReady } = await import('@/store/config/searchServiceReady');
      if (!(await checkSearchServiceReady())) {
        return false;
      }
    }

    // 验证配置
    const { valid, modelSelection } = validateChatModelConfig(requestState.actionMode, requestState.agentConfig);
    if (!valid) {
      return false;
    }

    // Auto-reset workflow mode after sending to prevent accidental high-cost subsequent messages
    if (state.isWorkflowMode) {
      actions.setIsWorkflowMode(false);
    }

    // 登记 AbortController 并设置 loading 状态
    // Save the abort controller to the workspace store for the current pane
    if (state.chatId) {
      const paneId = useWorkspaceStore.getState().panes.find((p: PaneConfig) => p.chatId === state.chatId)?.id;
      if (paneId) {
        useWorkspaceStore.getState().setPaneAbortController(paneId, abortController);
      }
    }

    const smartSetMessages = createSmartUpdater(state.chatId, actions.setMessages);
    const smartActions = { ...actions, setMessages: smartSetMessages };

    smartActions.setMessages((innerState) => {
      innerState.loading = true;
      innerState.messageAppeared = false;
      innerState.abortController = abortController;
    });

    const added = false;
    const recievedMessage = '';

    const isRegenerate = !!state.regenerateSiblingGroupId;

    const persistFiles =
      requestState.files.length > 0 ? requestState.files.map(({ contentHash: _, ...rest }) => rest) : undefined;

    if (!isRegenerate && !resumeValue) {
      smartActions.setMessages((innerState) => {
        if (!innerState.chatId) {
          return;
        }
        innerState.messages.push({
          content: input,
          messageId: requestMessageId,
          chatId: innerState.chatId,
          role: 'user',
          createdAt: new Date(),
          files: persistFiles,
        });
      });
      pushedUserBubble = true;
    }

    dispatched = true;
    await executeStreamWithRetry(
      input,
      requestMessageId,
      requestState,
      smartActions,
      modelSelection,
      abortController,
      added,
      recievedMessage,
      resumeValue,
      archiveRestoreActions,
      shouldRecordWikiQuerySuccess,
      turnCapabilityTelemetry,
    );
    useCompanionStore.getState().incrementConversation();
  } catch (error) {
    const smartSetMessages = createSmartUpdater(state.chatId, actions.setMessages);

    if (error instanceof AgentBusyError) {
      // The server refused the turn: retract the optimistic bubble so the caller's requeue
      // does not leave a duplicate of the same message in the transcript.
      if (pushedUserBubble) {
        smartSetMessages(retractUserBubble(requestMessageId));
      }
      throw error;
    }
    if (error instanceof ApprovalAlreadyResolvedError) {
      // Someone else (the timeout or another device) already resolved this interrupt: the caller owns the card and
      // tells the user, no failure notice.
      throw error;
    }
    if (isArchiveRestoreActionInvalidError(error)) {
      smartSetMessages((innerState) => {
        const lastMessageIndex = innerState.messages.length - 1;
        if (lastMessageIndex >= 0 && innerState.messages[lastMessageIndex].messageId === requestMessageId) {
          innerState.messages.pop();
        }
      });
      showI18nToast('chat.archiveRestore.invalidTitle', undefined, {
        descriptionKey: 'chat.archiveRestore.invalidDescription',
        descriptionValues: { error: error.detail || error.message },
        type: 'error',
        duration: 6000,
      });
      throw error;
    }
    if (error instanceof Error && error.name !== 'AbortError') {
      const isNetworkError = isTransientNetworkError(error);
      const refusal = error instanceof RequestRefusedError ? error : null;

      if (isHitlResume) {
        // The answered card already sits in the transcript, so a failed resume leaves it alone. When the server
        // never took the answer (refused, or no request got a reply) it is reported undispatched and the caller
        // that rolls its card back tells the user.
        if (isNetworkError || refusal) {
          dispatched = false;
        }
      } else if (isNetworkError) {
        smartSetMessages((innerState) => {
          const msg = innerState.messages.find((m) => m.messageId === requestMessageId);
          if (msg) {
            msg.sendFailed = true;
          }
        });
      } else {
        smartSetMessages((innerState) => {
          const lastMessageIndex = innerState.messages.length - 1;
          if (lastMessageIndex >= 0 && innerState.messages[lastMessageIndex].messageId === requestMessageId) {
            innerState.messages.pop();
          }
        });
        // The server never took the turn: report it undispatched so a queued message is kept for the user.
        if (refusal) {
          dispatched = false;
        }
      }

      // A text a risk rule holds has its notice already (shown by the risk event) and is no failure to report.
      if (!(error instanceof RiskBlockedError)) {
        console.error('[sendMessage] request failed:', error);
        if (!isHitlResume || dispatched) {
          showI18nToast('chat.messageFailed.title', undefined, sendFailureToast(isNetworkError, refusal?.detail));
        }
        if (resolveE2eApiBase()) {
          throw error;
        }
      }
    }
  } finally {
    const smartSetMessages = createSmartUpdater(state.chatId, actions.setMessages);
    // This turn can end after the next one took over (it was still reconciling with the server, or a stop reached it
    // while it waited for the workspace stream): the turn state then belongs to that turn and stays untouched.
    let heldByOtherTurn = false;
    smartSetMessages((innerState) => {
      heldByOtherTurn = isHeldByOtherTurn(innerState.abortController, abortController);
      if (heldByOtherTurn) {
        return;
      }
      innerState.loading = false;
      innerState.abortController = null;
      innerState.currentSessionMessageId = null;
      // A queued message sends its own attachments; the live ones belong to the message being composed.
      if (!queuedAttachments) {
        innerState.files = [];
        innerState.visionFrames = [];
      }
    });

    if (!heldByOtherTurn) {
      if (state.chatId) {
        const paneId = useWorkspaceStore.getState().panes.find((p: PaneConfig) => p.chatId === state.chatId)?.id;
        if (paneId) {
          useWorkspaceStore.getState().setPaneAbortController(paneId, null);
        }
      }
      actions.setHideAttachList(false);
    }
    actions.scheduleAutoSave();

    // Always release the processing lock on finally
    useToolApprovalStore.getState().unmarkProcessing(requestMessageId);

    if (
      typeof window !== 'undefined' &&
      resolveE2eApiBase() &&
      state.chatId?.trim() &&
      useToolApprovalStore.getState().queue.length === 0
    ) {
      const smartActionsForE2e = { ...actions, setMessages: smartSetMessages };
      const { tryE2eAttachForPendingApproval } = await import('./streamConsumer');
      await tryE2eAttachForPendingApproval(
        { ...state, loading: false, abortController: null },
        smartActionsForE2e,
        new AbortController(),
      );
    }
  }
  return dispatched;
};
