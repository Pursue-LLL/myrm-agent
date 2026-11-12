/**
 * [INPUT]
 * ./schema::parseSseEnvelope (POS: SSE JSON 校验)
 * ./messageStreamHandler::handleMessageStream (POS: SSE 事件 reducer)
 * ./messageStream/streamWatchdog::createStreamWatchdog (POS: 终止事件缺失自愈)
 * ./streamErrors (POS: busy / risk-blocked / interrupted 错误分类)
 *
 * [OUTPUT]
 * consumeStream: 读取一个 SSE Response（agent-stream POST 响应体或 attach 响应）→ 解密 e2ee 帧 → 校验 → reducer；busy 帧在 reducer 之前抛 AgentBusyError，reducer 抛出的 RiskBlockedError（服务端风控拦下）原样上抛，连接静默超过存活预算（含首帧前）或首帧之后读取失败抛 StreamInterruptedError；回合被中止时立即以 AbortError 结束（取消 reader 唤醒挂起的读取，不触发 watchdog 自愈）
 * STREAM_LIVENESS_BUDGET_MS: 一次读取允许无任何数据块的时长
 *
 * [POS]
 * 单段 SSE 消费循环：本循环拥有传输存活判定（每次读取一个预算，任何数据块——心跳帧也算——都续上；心跳帧本身不进 reducer）；流结束清理调度器；终止事件缺失的 UI 自愈交给 watchdog；重试与 attach 编排由 streamConsumer 负责。
 */
import { parseSseEnvelope } from './schema';
import { handleMessageStream, StreamHandlerState, StreamHandlerActions } from './messageStreamHandler';
import type { TurnMeta } from './messageStream/handleMessageStream';
import type { ChatActionsState, ChatActionsMethods } from './messageRequest';
import type { AgentStreamEvent } from './types';
import { AdaptiveScheduler } from './adaptiveScheduler';
import { decryptSseFrame, loadStoredE2EESession } from '@/lib/e2ee/client';
import { recoverPendingApprovals } from '@/hooks/approval/usePendingApprovalsRecovery';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import { createStreamWatchdog } from './messageStream/streamWatchdog';
import { AgentBusyError, RiskBlockedError, StreamInterruptedError, isAgentBusySseEvent } from './streamErrors';

/**
 * How long one read may deliver nothing before the connection counts as dead. The server sends a heartbeat on its run stream
 * and on its attach stream after every 15 s without events, so three intervals tolerate late heartbeats, while a turn the
 * model works on silently keeps its connection alive on heartbeats alone.
 */
export const STREAM_LIVENESS_BUDGET_MS = 45_000;

export type ConsumeStreamOptions = {
  /** Stop once the approval queue holds a card of this chat (HITL attach recovery); the cards of other chats do not count. */
  untilApprovalQueuedFor?: string;
  /** Wall-clock cap in ms; only used with untilApprovalQueuedFor. */
  maxWaitMs?: number;
  /** Called for every validated SSE envelope before reducer handling. */
  onBusinessEvent?: (event: AgentStreamEvent) => void;
};

export type ConsumeStreamResult = {
  added: boolean;
  recievedMessage: string;
  queueLen: number;
  stoppedEarly: boolean;
};

export async function consumeStream(
  res: Response,
  input: string,
  state: ChatActionsState,
  actions: ChatActionsMethods,
  abortController: AbortController,
  added: boolean,
  recievedMessage: string,
  options?: ConsumeStreamOptions,
): Promise<ConsumeStreamResult> {
  if (!res.body) {
    throw new Error('Streaming response body missing');
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  const dataPrefix = 'data: ';
  let currentSseEvent = '';

  let firstDataReceived = false;
  let stoppedEarly = false;
  const recoveryDeadline = options?.maxWaitMs !== undefined ? Date.now() + Math.max(0, options.maxWaitMs) : null;

  const scheduler = new AdaptiveScheduler();

  const streamState: StreamHandlerState = {
    chatId: state.chatId,
    actionMode: state.actionMode,
    messages: state.messages,
    messageAppeared: state.messageAppeared,
    loading: state.loading,
    scheduler,
  };

  let turnMeta: TurnMeta = {};
  let meta: TurnMeta | undefined;

  const streamActions: StreamHandlerActions = {
    setMessages: (updater) => {
      actions.setMessages((state) => updater(state));
    },
    setMessageAppeared: actions.setMessageAppeared,
    setLoading: actions.setLoading,
    clearActiveStream: actions.clearActiveStream,
    _processSuggestions: actions._processSuggestions,
    scheduleAutoSave: actions.scheduleAutoSave,
  };

  const watchdog = createStreamWatchdog({
    actions: {
      setLoading: actions.setLoading,
      clearActiveStream: actions.clearActiveStream,
      setMessageAppeared: actions.setMessageAppeared,
      scheduleAutoSave: actions.scheduleAutoSave,
    },
  });

  // A stop must wake a read that waits for the next chunk; otherwise it would take effect only once the liveness
  // budget ends that read.
  const cancelReaderOnAbort = (): void => {
    reader.cancel().catch(() => undefined);
  };
  abortController.signal.addEventListener('abort', cancelReaderOnAbort, { once: true });

  try {
    while (true) {
      abortController.signal.throwIfAborted();

      let readResult;
      // reader.read() waits for ever on a connection that stopped delivering, and any chunk (a heartbeat included) proves the
      // connection alive, so every read gets its own budget. A read that outlasts it cancels the reader, which ends the read,
      // and the turn goes to streamConsumer as an interrupted stream: it attaches to the turn again or fetches the final
      // messages. The budget is the native AbortSignal.timeout, independent of the global setTimeout.
      const idleSignal = AbortSignal.timeout(STREAM_LIVENESS_BUDGET_MS);
      const cancelOnIdle = (): void => {
        reader.cancel().catch(() => undefined);
      };
      idleSignal.addEventListener('abort', cancelOnIdle, { once: true });
      try {
        readResult = await reader.read();
        if (idleSignal.aborted && !abortController.signal.aborted) {
          throw new StreamInterruptedError(
            firstDataReceived
              ? 'Stream stalled after data started'
              : 'Stream produced no data before the first-frame timeout',
          );
        }
      } catch (e) {
        // A read torn down by the stop is the stop itself, not an interruption to re-attach to.
        abortController.signal.throwIfAborted();
        if (firstDataReceived) {
          throw new StreamInterruptedError('Stream interrupted during reading', e as Error);
        }
        throw e;
      } finally {
        idleSignal.removeEventListener('abort', cancelOnIdle);
      }
      // Cancelling the reader on stop ends a pending read as a clean end of stream, which must not heal the turn.
      abortController.signal.throwIfAborted();
      const { value, done } = readResult;

      if (done) {
        watchdog.onReaderDone();
        break;
      }

      if (!firstDataReceived) {
        firstDataReceived = true;
        actions.setInputMessage('');
      }

      buffer += decoder.decode(value, { stream: true });

      let startIndex = 0;
      let newlineIndex;
      while ((newlineIndex = buffer.indexOf('\n', startIndex)) !== -1) {
        const line = buffer.substring(startIndex, newlineIndex).trim();

        if (line.startsWith('event:')) {
          currentSseEvent = line.slice('event:'.length).trim();
          startIndex = newlineIndex + 1;
          continue;
        }

        if (line.startsWith(dataPrefix)) {
          const jsonStr = line.substring(dataPrefix.length).trim();
          if (currentSseEvent === 'heartbeat') {
            // The server emits protocol keepalives with a null body. The read that carried one has already renewed the
            // liveness budget; the frame itself must not enter the business-event schema or warning path.
            currentSseEvent = '';
            startIndex = newlineIndex + 1;
            continue;
          }
          if (jsonStr && currentSseEvent === 'e2ee_frame') {
            const session = loadStoredE2EESession();
            if (session) {
              try {
                const plainChunk = decryptSseFrame(session, jsonStr);
                buffer = plainChunk + buffer.substring(newlineIndex + 1);
                startIndex = 0;
                currentSseEvent = '';
                continue;
              } catch (err) {
                console.warn('E2EE SSE decrypt failed:', err);
                startIndex = newlineIndex + 1;
                currentSseEvent = '';
                continue;
              }
            }
          }
          if (jsonStr) {
            try {
              const rawJson = JSON.parse(jsonStr) as unknown;
              const event = parseSseEnvelope(rawJson);
              if (!event) {
                console.warn('Unknown or malformed SSE payload dropped');
                startIndex = newlineIndex + 1;
                continue;
              }
              if (isAgentBusySseEvent(event as { type: string } & Record<string, unknown>)) {
                throw new AgentBusyError('Agent is busy processing another request for this session.');
              }
              if (
                event.type === 'message_end' ||
                event.type === 'agent_cancelled' ||
                event.type === 'error' ||
                event.type === 'risk_blocked'
              ) {
                watchdog.markTerminalReceived();
              } else if (
                ('usage' in event && Boolean(event.usage)) ||
                ('token_economics' in event && Boolean(event.token_economics))
              ) {
                watchdog.notifyUsageReceived();
              }

              try {
                options?.onBusinessEvent?.(event);
              } catch (eventError) {
                console.warn('onBusinessEvent callback failed:', eventError);
              }
              ({ added, recievedMessage, meta } = await handleMessageStream(
                event,
                input,
                undefined,
                added,
                recievedMessage,
                streamState,
                streamActions,
                state.files,
                turnMeta,
              ));
              if (meta) {
                turnMeta = meta;
              }
              if (
                options?.untilApprovalQueuedFor !== undefined &&
                useToolApprovalStore
                  .getState()
                  .queue.some((request) => request.chatId === options.untilApprovalQueuedFor)
              ) {
                stoppedEarly = true;
                break;
              }
            } catch (err) {
              if (err instanceof AgentBusyError || err instanceof RiskBlockedError) {
                throw err;
              }
              console.warn('Invalid JSON skipped:', err);
            }
          }
          currentSseEvent = '';
        } else if (line === '') {
          currentSseEvent = '';
        }

        startIndex = newlineIndex + 1;
      }

      buffer = buffer.substring(startIndex);

      if (stoppedEarly) {
        break;
      }
      if (recoveryDeadline !== null && Date.now() >= recoveryDeadline) {
        stoppedEarly = true;
        break;
      }
    }
  } finally {
    abortController.signal.removeEventListener('abort', cancelReaderOnAbort);
    watchdog.dispose();
    if (stoppedEarly) {
      try {
        await reader.cancel();
      } catch {
        // ignore cancel errors during recovery detach
      }
    }
    // 确保在流结束或异常中断时清理定时器并立即执行最后一次渲染
    scheduler.flush();
    scheduler.cancel();
    void recoverPendingApprovals();
  }

  return {
    added,
    recievedMessage,
    queueLen: useToolApprovalStore.getState().queue.length,
    stoppedEarly,
  };
}
