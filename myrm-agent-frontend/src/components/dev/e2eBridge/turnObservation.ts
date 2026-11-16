/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/components/dev/e2eBridge/e2eTurnTrace::TurnTrace (POS: E2E bridge diagnostics.)
 * - @/components/dev/e2eBridge/e2eStoreTimelineWatcher::StoreTimelineWatch (POS: Store-bound half of the E2E store timeline (the record itself is pure and unit-tested).)
 * - @/components/dev/e2eBridge/sendTurnContract::resolveSendTurnNoOpMs, SEND_TURN_OBSERVE_MS, SEND_TURN_REV (POS: 发送回合中与 Python 端 dev_gate 契约逐值对应的常量)
 * - @/components/dev/e2eBridge/turnProgress::ApiPollStats, pollApiUserMessages, readE2eSendGeneration, resolveE2eTurnProgress (POS: 发送回合的进度读数)
 * - @/components/dev/e2eBridge/sendTurnResult::E2eSubmitResult, SendTurnProfile, buildSendTurnDiagnostic (POS: 一次发送的结果词汇)
 *
 * [OUTPUT]
 * - trackSettlement(sendPromise, trace, ...): hooks the send promise without awaiting it; the returned settlement tells the observer whether it was rejected or ended without any progress
 * - observeTurn(turn): polls the UI and the API until the send seals or fails; results carry `turnTrace`, `storeTimeline` and `apiPoll`
 * - SendSettlement / ObservedTurn
 *
 * [POS]
 * 发送流水线的观察阶段：不等发送 promise 结束，按 UI 进度与 API 落库的用户行判定封口，或在拒绝、无进展、会话重置、超时时给出带证据的失败结果。
 */
import useChatStore from '@/store/useChatStore';
import type { TurnTrace } from '@/components/dev/e2eBridge/e2eTurnTrace';
import type { StoreTimelineWatch } from '@/components/dev/e2eBridge/e2eStoreTimelineWatcher';
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
import {
  buildSendTurnDiagnostic,
  type E2eSubmitResult,
  type SendTurnProfile,
} from '@/components/dev/e2eBridge/sendTurnResult';

/** Pause between two rounds of the observe loop. */
const OBSERVE_POLL_MS = 250;
/** Time since kickoff after which a send promise that ended without UI progress is reported as a no-op. */
const SETTLED_EMPTY_NO_OP_MS = 1_500;

/** What the send promise has reported so far: written by its settle handlers, read by the observe loop. */
export interface SendSettlement {
  /** Message of the rejection; null while the promise has not been rejected. */
  submitError: string | null;
  /** The promise ended and the page showed no progress at that moment. */
  settledEmpty: boolean;
}

export interface ObservedTurn {
  profile: SendTurnProfile;
  baselineUsers: number;
  /** Send generation when the send began: a different value later means the page session was reset. */
  startGen: number;
  chatIdBeforeSend: string;
  /** When the message was handed to the product (ms epoch); the no-progress budgets count from here. */
  kickoffAt: number;
  settlement: SendSettlement;
  trace: TurnTrace;
  watch: StoreTimelineWatch;
}

/** Hooks the send promise without awaiting it: a send ends when its stream ends, a turn seals long before that. */
export function trackSettlement(
  sendPromise: Promise<boolean>,
  trace: TurnTrace,
  { chatIdBeforeSend, baselineUsers }: Pick<ObservedTurn, 'chatIdBeforeSend' | 'baselineUsers'>,
): SendSettlement {
  const settlement: SendSettlement = { submitError: null, settledEmpty: false };
  void sendPromise
    .then((dispatched) => {
      trace.recordSettle(dispatched ? 'resolved' : 'resolved-undispatched');
      const chatId = useChatStore.getState().chatId?.trim() || chatIdBeforeSend;
      const progress = resolveE2eTurnProgress(chatId, baselineUsers);
      if (!progress.uiProgress) {
        settlement.settledEmpty = true;
      }
    })
    .catch((error) => {
      settlement.submitError = error instanceof Error ? error.message : String(error);
      trace.recordSettle(`rejected:${settlement.submitError}`);
    });
  return settlement;
}

export async function observeTurn({
  profile,
  baselineUsers,
  startGen,
  chatIdBeforeSend,
  kickoffAt,
  settlement,
  trace,
  watch,
}: ObservedTurn): Promise<E2eSubmitResult> {
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
  const turnEvidence = () => ({ turnTrace: trace.snapshot(), storeTimeline: watch.snapshot() });
  /** The readings every result that polled the API reports, next to the identity of the send. */
  const observation = (
    phase: 'SUBMIT' | 'OBSERVE' | 'SEAL',
    apiUsers: number,
    { userCount, streaming }: { userCount: number; streaming: boolean },
  ) => ({
    phase,
    profile,
    sendGeneration: startGen,
    apiUsers,
    apiPoll: { ...apiPoll },
    ...turnEvidence(),
    userCount,
    streaming,
    baselineUsers,
  });
  const observeDeadline = Date.now() + SEND_TURN_OBSERVE_MS;
  while (Date.now() < observeDeadline) {
    if (settlement.submitError) {
      return {
        ok: false,
        err: settlement.submitError,
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
      await new Promise((resolve) => setTimeout(resolve, OBSERVE_POLL_MS));
      continue;
    }
    const progress = resolveE2eTurnProgress(chatId, baselineUsers);
    const elapsedMs = Date.now() - kickoffAt;
    if (settlement.settledEmpty && elapsedMs >= SETTLED_EMPTY_NO_OP_MS) {
      const apiUsersProbe = await countApiUsers(chatId);
      return {
        ok: false,
        err: 'send-message-settled-without-progress',
        mode: 'sendTurnSubmitNoOp',
        chatId,
        debug: {
          ...observation('SUBMIT', apiUsersProbe, progress),
          elapsedMs,
          ...buildSendTurnDiagnostic(chatId),
        },
      };
    }
    if (elapsedMs >= resolveSendTurnNoOpMs() && !progress.uiProgress) {
      const apiUsersProbe = await countApiUsers(chatId);
      if (apiUsersProbe <= baselineUsers) {
        return {
          ok: false,
          err: 'send-kickoff-no-progress',
          mode: 'sendTurnSubmitNoOp',
          chatId,
          debug: {
            ...observation('OBSERVE', apiUsersProbe, progress),
            elapsedMs,
            sendSettledEmpty: settlement.settledEmpty,
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
    // turn, whichever its profile, must therefore have both UI progress and an
    // API-side row; the profile only labels the result.
    if (apiOk && progress.uiProgress) {
      // store.agentConfig may have been reset by attach after POST; the payload
      // itself is guaranteed by agentConfigOverride, so reflect that in diagnostics.
      const ephKeys = window.__MYRM_E2E_EPH_APPLIED__?.keys ?? [];
      return {
        ok: true,
        chatId,
        mode: 'sendTurnSealed',
        debug: {
          ...observation('SEAL', apiUsers, progress),
          rev: SEND_TURN_REV,
          chatIdBeforeSend: chatIdBeforeSend !== chatId ? chatIdBeforeSend : undefined,
          ephKeys,
          actionModeAtSeal: useChatStore.getState().actionMode,
        },
      };
    }
    await new Promise((resolve) => setTimeout(resolve, OBSERVE_POLL_MS));
  }
  const finalChatId = useChatStore.getState().chatId?.trim() || chatIdBeforeSend;
  const finalProgress = resolveE2eTurnProgress(finalChatId, baselineUsers);
  const finalApiUsers = await countApiUsers(finalChatId);
  return {
    ok: false,
    err: 'send-turn-observe-timeout',
    mode: 'sendTurnObserveTimeout',
    chatId: finalChatId,
    debug: {
      ...observation('OBSERVE', finalApiUsers, finalProgress),
      sendSettledEmpty: settlement.settledEmpty,
      ...buildSendTurnDiagnostic(finalChatId),
    },
  };
}
