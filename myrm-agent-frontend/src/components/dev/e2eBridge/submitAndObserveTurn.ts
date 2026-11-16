/**
 * [INPUT]
 * - @/store/chat/messageRequest::getModelSelection (POS: Facade of the chat message request layer.)
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/store/useToolApprovalStore::useToolApprovalStore
 * - @/store/useConfigStore::useConfigStore
 * - @/store/config/searchService::guardSearchServiceConfigured
 * - @/store/chat/types::AgentConfig (POS: @/store/chat/types 稳定入口；实现位于 types/。)
 * - @/components/dev/e2eBridge/e2eChatBridgeSendPolicy::shouldPreserveE2eActionMode, shouldRunPrepareAutomationSend (POS: Action-mode policy of an automated send: fast mode reaches the server as it is, agent-mode sends may be prepared.)
 * - @/components/dev/e2eBridge/e2eTurnTrace::createTurnTrace, TurnTrace (POS: E2E bridge diagnostics.)
 * - @/components/dev/e2eBridge/e2eStoreTimelineWatcher::StoreTimelineWatch, watchChatStoreTimeline (POS: Store-bound half of the E2E store timeline (the record itself is pure and unit-tested).)
 * - @/components/dev/e2eBridge/sendTurnContract::resolveSendTurnNoOpMs, SEND_TURN_OBSERVE_MS, SEND_TURN_REV (POS: 发送回合中与 Python 端 dev_gate 契约逐值对应的常量)
 * - @/components/dev/e2eBridge/turnProgress::ApiPollStats, pollApiUserMessages, readE2eSendGeneration, resolveE2eTurnProgress (POS: 发送回合的进度读数)
 * - @/components/dev/e2eBridge/hostEnv::prepareAutomationSend (POS: 开发桥的页面环境探针)
 *
 * [OUTPUT]
 * - submitAndObserveTurn(...): sends one message through the product pipeline and seals once the UI shows progress and the API holds the user row; results carry `turnTrace`, `storeTimeline` and `apiPoll`
 * - recordActiveTurnEvent(type): feeds the latest send's trace with an SSE event type
 * - E2eSubmitResult / SendTurnProfile
 *
 * [POS]
 * 发送并观察一个聊天回合的流水线：把封口判据、store 与 API 的进度读数、诊断记录汇合成一次发送的结果。
 */
import { flushSync } from 'react-dom';
import { getModelSelection } from '@/store/chat/messageRequest';
import useChatStore from '@/store/useChatStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import useConfigStore from '@/store/useConfigStore';
import { guardSearchServiceConfigured } from '@/store/config/searchService';
import type { AgentConfig } from '@/store/chat/types';
import {
  shouldPreserveE2eActionMode,
  shouldRunPrepareAutomationSend,
} from '@/components/dev/e2eBridge/e2eChatBridgeSendPolicy';
import { createTurnTrace, type TurnTrace } from '@/components/dev/e2eBridge/e2eTurnTrace';
import { type StoreTimelineWatch, watchChatStoreTimeline } from '@/components/dev/e2eBridge/e2eStoreTimelineWatcher';
import {
  resolveSendTurnNoOpMs,
  SEND_TURN_OBSERVE_MS,
  SEND_TURN_REV,
} from '@/components/dev/e2eBridge/sendTurnContract';
import {
  type ApiPollStats,
  pollApiUserMessages,
  readE2eSendGeneration,
  resolveE2eTurnProgress,
} from '@/components/dev/e2eBridge/turnProgress';
import { prepareAutomationSend } from '@/components/dev/e2eBridge/hostEnv';

export type E2eSubmitResult = {
  ok: boolean;
  err?: string;
  chatId?: string | null;
  mode?: string;
  debug?: Record<string, unknown>;
};

export type SendTurnProfile = 'live' | 'read';

/** Trace of the latest send: the SSE recorder feeds it, the send's own results report it. */
let activeTurnTrace: TurnTrace | null = null;

function buildSendTurnDiagnostic(chatId: string | null): Record<string, unknown> {
  const processingIds = [...useToolApprovalStore.getState().processingMessageIds];
  return {
    rev: SEND_TURN_REV,
    turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? null,
    provider: window.__MYRM_E2E_CHAT__?.debugProviderState?.() ?? null,
    workspace: window.__MYRM_WORKSPACE_STREAM_STATUS__?.() ?? null,
    chatId,
    processingIds,
    approvalQueueLen: useToolApprovalStore.getState().queue.length,
  };
}

export async function submitAndObserveTurn(
  message: string,
  baselineUsers: number,
  profile: SendTurnProfile,
  preserveActionMode = false,
  ephemeralSubagents?: Record<string, unknown>,
): Promise<E2eSubmitResult> {
  const trimmed = message.trim();
  const hasAttachments = (useChatStore.getState().files?.length ?? 0) > 0;
  const hasSkillActivation = Boolean(useChatStore.getState().pendingExplicitSkillActivation);
  if (!trimmed && !hasAttachments && !hasSkillActivation) {
    return { ok: false, err: 'empty-message', mode: 'sendTurnEmpty' };
  }
  const startGen = readE2eSendGeneration();
  let storeWatch: StoreTimelineWatch | null = null;
  try {
    window.__MYRM_E2E_CHAT__?.abortActiveStream?.();
    window.__MYRM_E2E_CHAT__?.releaseActiveStreamForApiResume?.();
    const { actionMode: sendActionMode } = useChatStore.getState();
    const shouldPreserveActionMode = shouldPreserveE2eActionMode(sendActionMode, preserveActionMode);
    const sessionOpts = shouldPreserveActionMode ? { preserveActionMode: true } : undefined;
    await window.__MYRM_E2E_CHAT__?.ensureChatSession?.(sessionOpts);
    flushSync(() => {
      useChatStore.getState().setInputMessage(trimmed);
    });
    const chatIdBeforeSend = useChatStore.getState().chatId?.trim() || '';
    if (!chatIdBeforeSend) {
      return { ok: false, err: 'no-chat-id', mode: 'sendTurnNoChatId' };
    }
    const { actionMode: currentActionMode } = useChatStore.getState();
    if (currentActionMode === 'fast') {
      const configs = useConfigStore.getState().searchServiceConfigs;
      if (!guardSearchServiceConfigured(configs)) {
        return {
          ok: false,
          err: 'search-not-configured',
          mode: 'sendTurnSearchGuard',
          debug: {
            actionMode: currentActionMode,
            searchCount: configs.length,
            enabledCount: configs.filter((item) => item.enabled).length,
          },
        };
      }
    }
    if (!window.__MYRM_E2E_CHAT__?.isSendReady?.()) {
      return {
        ok: false,
        err: 'send-not-ready',
        mode: 'sendTurnNotReady',
        debug: window.__MYRM_E2E_CHAT__?.debugProviderState?.(),
      };
    }
    const staleRequestId = useChatStore.getState().currentSessionMessageId;
    if (staleRequestId) {
      useToolApprovalStore.getState().unmarkProcessing(staleRequestId);
    }
    useChatStore.getState().clearCurrentSessionMessageId();
    const messagesLoadedDeadline = Date.now() + 30_000;
    while (Date.now() < messagesLoadedDeadline) {
      const loadedState = useChatStore.getState();
      if (loadedState.isMessagesLoaded && !loadedState.loading) {
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    const sendReadyDeadline = Date.now() + 30_000;
    while (Date.now() < sendReadyDeadline) {
      const chatState = useChatStore.getState();
      if (!chatState.loading && !chatState.abortController) {
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    const preSendState = useChatStore.getState();
    if (preSendState.loading || preSendState.abortController) {
      return {
        ok: false,
        err: 'chat-still-busy',
        mode: 'sendTurnBusy',
        debug: {
          turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.(),
          ...window.__MYRM_E2E_CHAT__?.debugProviderState?.(),
        },
      };
    }
    if (shouldRunPrepareAutomationSend(shouldPreserveActionMode)) {
      prepareAutomationSend();
    }
    useToolApprovalStore.getState().clearAll();
    let agentConfigOverride: AgentConfig | undefined;
    if (ephemeralSubagents && Object.keys(ephemeralSubagents).length > 0) {
      // JIT delegation is an agent-mode flow: the backend drops ephemeral_subagents
      // when action_mode=fast (converter.py sets jit_subagents=None for fast search).
      // Chrome E2E profile can persist actionMode=fast in localStorage, so force agent.
      if (!preserveActionMode) {
        useChatStore.getState().setActionMode('agent');
      }
      // 不依赖 store.agentConfig 的稳定性：直接通过 sendMessage 的
      // agentConfigOverride 参数注入，requestState 在入口即固定，payload
      // 一定携带 ephemeral_subagents（store 后续被 attach 重置也不受影响）。
      const currentConfig = useChatStore.getState().agentConfig;
      agentConfigOverride = {
        ...((currentConfig ?? {}) as Partial<AgentConfig>),
        ephemeralSubagents,
      } as AgentConfig;
      window.__MYRM_E2E_EPH_APPLIED__ = {
        keys: Object.keys(ephemeralSubagents),
        at: Date.now(),
        forced: !currentConfig,
      };
    }
    const { actionMode } = useChatStore.getState();
    const agentConfig = agentConfigOverride ?? useChatStore.getState().agentConfig;
    if (!getModelSelection(actionMode, agentConfig)) {
      return {
        ok: false,
        err: 'model-selection-unavailable',
        mode: 'sendTurnValidateFailed',
        chatId: chatIdBeforeSend,
        debug: { phase: 'ARM', ...buildSendTurnDiagnostic(chatIdBeforeSend), baselineUsers },
      };
    }
    let submitError: string | null = null;
    let sendSettledEmpty = false;
    const apiPoll: ApiPollStats = { polls: 0, notFound: 0, failures: 0, lastFailure: null, slowestMs: 0 };
    const countApiUsers = async (id: string): Promise<number> => {
      const startedAt = Date.now();
      const poll = await pollApiUserMessages(id);
      apiPoll.polls += 1;
      apiPoll.slowestMs = Math.max(apiPoll.slowestMs, Date.now() - startedAt);
      if (poll.notFound) {
        apiPoll.notFound += 1;
      }
      if (poll.failure !== null) {
        apiPoll.failures += 1;
        apiPoll.lastFailure = poll.failure;
      }
      return poll.users;
    };
    const kickoffAt = Date.now();
    const trace = createTurnTrace(Date.now);
    activeTurnTrace = trace;
    const watch = watchChatStoreTimeline();
    storeWatch = watch;
    const turnEvidence = () => ({ turnTrace: trace.snapshot(), storeTimeline: watch.snapshot() });
    const sendPromise = useChatStore
      .getState()
      .sendMessage(trimmed, undefined, undefined, undefined, undefined, agentConfigOverride);
    await Promise.resolve();
    void sendPromise
      .then((dispatched) => {
        trace.recordSettle(dispatched ? 'resolved' : 'resolved-undispatched');
        const chatId = useChatStore.getState().chatId?.trim() || chatIdBeforeSend;
        const progress = resolveE2eTurnProgress(chatId, baselineUsers);
        if (!progress.uiProgress) {
          sendSettledEmpty = true;
        }
      })
      .catch((error) => {
        submitError = error instanceof Error ? error.message : String(error);
        trace.recordSettle(`rejected:${submitError}`);
      });
    const observeDeadline = Date.now() + SEND_TURN_OBSERVE_MS;
    while (Date.now() < observeDeadline) {
      if (submitError) {
        return {
          ok: false,
          err: submitError,
          mode: 'sendTurnSubmitError',
          chatId: chatIdBeforeSend,
          debug: {
            phase: 'SUBMIT',
            sendGeneration: startGen,
            ...turnEvidence(),
            ...buildSendTurnDiagnostic(chatIdBeforeSend),
          },
        };
      }
      if (readE2eSendGeneration() !== startGen) {
        return {
          ok: false,
          err: 'session-reset-during-submit',
          mode: 'sendTurnGenerationMismatch',
          chatId: chatIdBeforeSend,
          debug: { phase: 'OBSERVE', sendGeneration: startGen, currentGeneration: readE2eSendGeneration() },
        };
      }
      const chatState = useChatStore.getState();
      const chatId = chatState.chatId?.trim() || '';
      if (!chatId) {
        await new Promise((resolve) => setTimeout(resolve, 250));
        continue;
      }
      const { userCount, streaming, uiProgress } = resolveE2eTurnProgress(chatId, baselineUsers);
      const elapsedMs = Date.now() - kickoffAt;
      if (sendSettledEmpty && elapsedMs >= 1_500) {
        const apiUsersProbe = await countApiUsers(chatId);
        return {
          ok: false,
          err: 'send-message-settled-without-progress',
          mode: 'sendTurnSubmitNoOp',
          chatId,
          debug: {
            phase: 'SUBMIT',
            profile,
            sendGeneration: startGen,
            apiUsers: apiUsersProbe,
            apiPoll: { ...apiPoll },
            ...turnEvidence(),
            userCount,
            streaming,
            baselineUsers,
            elapsedMs,
            ...buildSendTurnDiagnostic(chatId),
          },
        };
      }
      if (elapsedMs >= resolveSendTurnNoOpMs() && !uiProgress) {
        const apiUsersProbe = await countApiUsers(chatId);
        if (apiUsersProbe <= baselineUsers) {
          return {
            ok: false,
            err: 'send-kickoff-no-progress',
            mode: 'sendTurnSubmitNoOp',
            chatId,
            debug: {
              phase: 'OBSERVE',
              profile,
              sendGeneration: startGen,
              apiUsers: apiUsersProbe,
              apiPoll: { ...apiPoll },
              ...turnEvidence(),
              userCount,
              streaming,
              baselineUsers,
              elapsedMs,
              sendSettledEmpty,
              ...buildSendTurnDiagnostic(chatId),
            },
          };
        }
      }
      const apiUsers = await countApiUsers(chatId);
      const apiOk = apiUsers > baselineUsers;
      // A local placeholder/stream can be produced before the private backend
      // accepts the POST. It is not an admission signal: sealing here would
      // let the E2E flow continue while the API still has no user row. Every
      // live turn must therefore have both UI progress and an API-side row.
      const liveOk = apiOk && uiProgress;
      const readOk = apiOk && uiProgress;
      if ((profile === 'live' && liveOk) || (profile === 'read' && readOk)) {
        // store.agentConfig may have been reset by attach after POST; the payload
        // itself is guaranteed by agentConfigOverride, so reflect that in diagnostics.
        const ephKeys = window.__MYRM_E2E_EPH_APPLIED__?.keys ?? [];
        return {
          ok: true,
          chatId,
          mode: 'sendTurnSealed',
          debug: {
            phase: 'SEAL',
            profile,
            rev: SEND_TURN_REV,
            sendGeneration: startGen,
            apiUsers,
            apiPoll: { ...apiPoll },
            ...turnEvidence(),
            userCount,
            streaming,
            baselineUsers,
            chatIdBeforeSend: chatIdBeforeSend !== chatId ? chatIdBeforeSend : undefined,
            ephKeys,
            actionModeAtSeal: useChatStore.getState().actionMode,
          },
        };
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    const finalState = useChatStore.getState();
    const finalChatId = finalState.chatId?.trim() || chatIdBeforeSend;
    const finalProgress = finalChatId
      ? resolveE2eTurnProgress(finalChatId, baselineUsers)
      : { userCount: 0, streaming: false, uiProgress: false };
    const finalApiUsers = finalChatId ? await countApiUsers(finalChatId) : 0;
    return {
      ok: false,
      err: 'send-turn-observe-timeout',
      mode: 'sendTurnObserveTimeout',
      chatId: finalChatId,
      debug: {
        phase: 'OBSERVE',
        profile,
        rev: SEND_TURN_REV,
        sendGeneration: startGen,
        apiUsers: finalApiUsers,
        apiPoll: { ...apiPoll },
        ...turnEvidence(),
        userCount: finalProgress.userCount,
        streaming: finalProgress.streaming,
        baselineUsers,
        sendSettledEmpty,
        ...buildSendTurnDiagnostic(finalChatId || chatIdBeforeSend),
      },
    };
  } catch (error) {
    return {
      ok: false,
      err: error instanceof Error ? error.message : String(error),
      mode: 'sendTurnUnexpected',
      debug: { phase: 'SUBMIT', sendGeneration: startGen },
    };
  } finally {
    storeWatch?.stop();
  }
}

/** Feeds the latest send's trace with one SSE event type; a no-op until the first send. */
export function recordActiveTurnEvent(type: string): void {
  activeTurnTrace?.recordEvent(type);
}
