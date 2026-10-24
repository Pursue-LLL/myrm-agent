/**
 * [INPUT]
 * ./schema::parseSseEnvelope (POS: SSE JSON 校验)
 * ./messageStreamHandler::handleMessageStream (POS: SSE 事件 reducer)
 * ./messageStream/streamWatchdog::createStreamWatchdog (POS: 流静默自愈)
 * ./streamErrors (POS: busy / risk-blocked / interrupted 错误分类)
 *
 * [OUTPUT]
 * consumeStream: 读取一个 SSE Response（POST 响应体或 multiplex 桥）→ 解密 e2ee 帧 → 校验 → reducer；busy 帧在 reducer 之前抛 AgentBusyError，reducer 抛出的 RiskBlockedError（服务端风控拦下）原样上抛，首帧之后读取失败抛 StreamInterruptedError；回合被中止时立即以 AbortError 结束（取消 reader 唤醒挂起的读取，不触发 watchdog 自愈）
 *
 * [POS]
 * 单段 SSE 消费循环（跳过心跳帧、喂养 watchdog、流结束清理调度器）；重试与 attach 编排由 streamConsumer 负责。
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

export type ConsumeStreamOptions = {
  /** Stop once tool approval queue is populated (SHPOIB HITL attach recovery). */
  untilApprovalQueued?: boolean;
  /** Wall-clock cap in ms; only used with untilApprovalQueued. */
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

  let lastDataTime = Date.now();
  const DATA_TIMEOUT = 5 * 60 * 1000;
  // 首帧超时必须独立于「有数据后」的空窗预算：reader.read() 在没有数据时会一直挂起，
  // 循环顶部的 DATA_TIMEOUT 检查根本不会执行（桌面 WebView 里出现过流已 200 但永远无首帧，
  // 结果输入框骨架永久转圈）。首帧缺失 60s 即视为链路中断，交由 streamConsumer 的
  // StreamInterruptedError 分支 attach / 拉取最终消息自愈。
  const FIRST_DATA_TIMEOUT = 60 * 1000;
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

  // A stop must wake a read that waits for the next chunk: once the multiplex bridge is disposed it neither closes
  // nor errors by itself, and the watchdog would heal the shared turn state seconds later instead.
  const cancelReaderOnAbort = (): void => {
    reader.cancel().catch(() => undefined);
  };
  abortController.signal.addEventListener('abort', cancelReaderOnAbort, { once: true });

  try {
    while (true) {
      if (Date.now() - lastDataTime > DATA_TIMEOUT) {
        console.warn('Stream timeout: no data received for 5 minutes');
        throw new Error('Service response timeout, please try again');
      }

      abortController.signal.throwIfAborted();

      let readResult;
      // 用原生 AbortSignal.timeout（不经过全局 setTimeout）做空窗预算：reader.read() 在无数据时
      // 会一直挂起，循环顶部的 DATA_TIMEOUT 检查永远轮不到，界面就会永久停在骨架态。
      // 超时先取消 reader 让挂起的读取返回，再按 StreamInterruptedError 交给 attach / 拉取最终消息自愈。
      const idleBudget = firstDataReceived ? DATA_TIMEOUT : FIRST_DATA_TIMEOUT;
      // 老版本浏览器（Safari < 16）没有 AbortSignal.timeout：降级为不设空窗看门狗，
      // 而不是抛 TypeError 把整轮聊天打死；有该能力时才有首帧/空窗自愈。
      const idleSignal = typeof AbortSignal.timeout === 'function' ? AbortSignal.timeout(idleBudget) : undefined;
      const cancelOnIdle = (): void => {
        reader.cancel().catch(() => undefined);
      };
      idleSignal?.addEventListener('abort', cancelOnIdle, { once: true });
      try {
        readResult = await reader.read();
        if (idleSignal?.aborted && !abortController.signal.aborted) {
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
        idleSignal?.removeEventListener('abort', cancelOnIdle);
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

      lastDataTime = Date.now();
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
            // ResilientStreamBuffer emits protocol keepalives with a null body.
            // They must not enter the business-event schema or warning path.
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
              watchdog.feed(event.type);
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
              if (options?.untilApprovalQueued && useToolApprovalStore.getState().queue.length > 0) {
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
