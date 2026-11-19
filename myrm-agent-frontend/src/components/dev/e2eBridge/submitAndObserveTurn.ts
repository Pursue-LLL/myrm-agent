/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/components/dev/e2eBridge/e2eTurnTrace::createTurnTrace, TurnTrace (POS: E2E bridge diagnostics.)
 * - @/components/dev/e2eBridge/e2eStoreTimelineWatcher::StoreTimelineWatch, watchChatStoreTimeline (POS: Store-bound half of the E2E store timeline (the record itself is pure and unit-tested).)
 * - @/components/dev/e2eBridge/turnProgress::readE2eSendGeneration (POS: 发送回合的进度读数)
 * - @/components/dev/e2eBridge/sendTurnResult::E2eSubmitResult, SendTurnProfile (POS: 一次发送的结果词汇)
 * - @/components/dev/e2eBridge/turnPreparation::prepareTurn (POS: 发送流水线的发送前阶段)
 * - @/components/dev/e2eBridge/turnObservation::observeTurn, trackSettlement (POS: 发送流水线的观察阶段)
 *
 * [OUTPUT]
 * - submitAndObserveTurn(...): sends one message through the product pipeline and seals once the UI shows progress and the API holds the user row; results carry `turnTrace`, `storeTimeline` and `apiPoll`
 * - recordActiveTurnEvent(type): feeds the latest send's trace with an SSE event type
 *
 * [POS]
 * 发送并观察一个聊天回合的流水线编排：发送前准备、把消息交给产品的发送流程（不等流结束）、观察到封口或失败；无论怎样结束都停止 store 订阅。
 */
import useChatStore from '@/store/useChatStore';
import { createTurnTrace, type TurnTrace } from '@/components/dev/e2eBridge/e2eTurnTrace';
import { type StoreTimelineWatch, watchChatStoreTimeline } from '@/components/dev/e2eBridge/e2eStoreTimelineWatcher';
import { readE2eSendGeneration } from '@/components/dev/e2eBridge/turnProgress';
import type { E2eSubmitResult, SendTurnProfile } from '@/components/dev/e2eBridge/sendTurnResult';
import { prepareTurn } from '@/components/dev/e2eBridge/turnPreparation';
import { observeTurn, trackSettlement } from '@/components/dev/e2eBridge/turnObservation';

/** Trace of the latest send: the SSE recorder feeds it, the send's own results report it. */
let activeTurnTrace: TurnTrace | null = null;

export async function submitAndObserveTurn(
  message: string,
  baselineUsers: number,
  profile: SendTurnProfile,
  preserveActionMode = false,
  ephemeralSubagents?: Record<string, unknown>,
): Promise<E2eSubmitResult> {
  const text = message.trim();
  const startGen = readE2eSendGeneration();
  let storeWatch: StoreTimelineWatch | null = null;
  try {
    const prepared = await prepareTurn({ text, baselineUsers, preserveActionMode, ephemeralSubagents });
    if (!prepared.ok) {
      return prepared.result;
    }
    const { chatIdBeforeSend, agentConfigOverride } = prepared;
    const kickoffAt = Date.now();
    const trace = createTurnTrace(Date.now);
    activeTurnTrace = trace;
    const watch = watchChatStoreTimeline();
    storeWatch = watch;
    const sendPromise = useChatStore
      .getState()
      .sendMessage(text, undefined, undefined, undefined, undefined, agentConfigOverride);
    await Promise.resolve();
    const settlement = trackSettlement(sendPromise, trace, { chatIdBeforeSend, baselineUsers });
    return await observeTurn({
      profile,
      baselineUsers,
      startGen,
      chatIdBeforeSend,
      kickoffAt,
      settlement,
      trace,
      watch,
    });
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
