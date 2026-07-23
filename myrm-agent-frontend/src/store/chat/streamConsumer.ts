import { parseSseEnvelope } from './schema';
import { handleMessageStream, StreamHandlerState, StreamHandlerActions } from './messageStreamHandler';
import { ChatActionsState, ChatActionsMethods, createMessageRequest } from './messageRequest';
import { type ArchiveRestoreAction, ModelSelection } from './types';
import { AdaptiveScheduler } from './adaptiveScheduler';
import { isRetryableHttpStatus, FatalNetworkError } from '@/lib/utils/networkResilience';
import { decryptSseFrame, loadStoredE2EESession } from '@/lib/e2ee/client';
import { createMultiplexReadableStream } from './multiplexChunkBridge';
import { recoverPendingApprovals } from '@/hooks/usePendingApprovalsRecovery';
import { connectionManager } from '@/services/ConnectionManager';
import { resolveE2eApiBase } from '@/lib/deploy-mode';
import useToolApprovalStore from '@/store/useToolApprovalStore';

function shouldUseMultiplexedAgentStream(): boolean {
  if (typeof window === 'undefined') {
    return true;
  }
  if (window.__MYRM_E2E_DIRECT_SSE__) {
    return false;
  }
  return !resolveE2eApiBase();
}

async function tryE2eAttachForPendingApproval(
  state: ChatActionsState,
  actions: ChatActionsMethods,
  _abortController: AbortController,
): Promise<{ attached: boolean; queueLen: number }> {
  if (typeof window === 'undefined') {
    return { attached: false, queueLen: 0 };
  }
  if (!window.__MYRM_E2E_DIRECT_SSE__ && !resolveE2eApiBase()) {
    return { attached: false, queueLen: 0 };
  }
  const chatId = state.chatId?.trim();
  if (!chatId || useToolApprovalStore.getState().queue.length > 0) {
    return { attached: false, queueLen: useToolApprovalStore.getState().queue.length };
  }
  const { default: useChatStore } = await import('../useChatStore');
  for (let attempt = 0; attempt < 5; attempt += 1) {
    if (useToolApprovalStore.getState().queue.length > 0) {
      const queueLen = useToolApprovalStore.getState().queue.length;
      if (typeof window !== 'undefined') {
        window.__MYRM_E2E_ATTACH_DIAG__ = { attached: true, queueLen, attempt };
      }
      return { attached: true, queueLen, attempt };
    }
    try {
      const { attachForHitlRecovery } = await import('./messageRequest');
      const recovery = await attachForHitlRecovery(chatId, actions, useChatStore.getState);
      if (recovery.attached || recovery.queueLen > 0) {
        const queueLen = recovery.queueLen;
        if (typeof window !== 'undefined') {
          window.__MYRM_E2E_ATTACH_DIAG__ = {
            attached: recovery.attached,
            queueLen,
            attempt,
            source: recovery.source,
          };
        }
        return { attached: recovery.attached, queueLen, attempt };
      }
    } catch (error) {
      console.warn('SHPOIB E2E attach fallback failed:', error);
      if (typeof window !== 'undefined') {
        window.__MYRM_E2E_ATTACH_DIAG__ = {
          attached: false,
          queueLen: 0,
          attempt,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    }
    if (attempt < 4) {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
  }
  return { attached: false, queueLen: useToolApprovalStore.getState().queue.length, attempt: 4 };
}

export { tryE2eAttachForPendingApproval };

const RETRY_INITIAL_DELAY_MS = 2000;
const RETRY_BACKOFF_FACTOR = 1.5;
const RETRY_MAX_ATTEMPTS = 10; // 增加重试次数，以应对后端重启较慢的情况（总等待时间约 1 分钟）

interface StructuredHttpErrorPayload {
  detail?: string;
  errorCode?: string;
}

export class AgentBusyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AgentBusyError';
  }
}

export class StreamInterruptedError extends Error {
  originalError?: Error;
  constructor(message: string, originalError?: Error) {
    super(message);
    this.name = 'StreamInterruptedError';
    this.originalError = originalError;
  }
}

export { FatalNetworkError }; // Re-export for messageRequest.ts

export function isTransientNetworkError(error: Error): boolean {
  if (error instanceof FatalNetworkError) return false;
  return (
    error instanceof TypeError ||
    error.message.includes('Failed to fetch') ||
    error.message.includes('NetworkError') ||
    error.message.includes('ERR_CONNECTION') ||
    error.message.includes('[TransientHTTP]')
  );
}

function retryDelay(attempt: number): number {
  const baseDelay = RETRY_INITIAL_DELAY_MS * Math.pow(RETRY_BACKOFF_FACTOR, attempt);
  const jitter = 0.8 + Math.random() * 0.4;
  return Math.floor(baseDelay * jitter);
}

function parseStructuredHttpErrorPayload(rawBody: string): StructuredHttpErrorPayload {
  if (!rawBody) {
    return {};
  }
  try {
    const parsed: unknown = JSON.parse(rawBody);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return {};
    }
    const record = parsed as Record<string, unknown>;
    const detail = typeof record.detail === 'string' ? record.detail : undefined;
    const errorCode = typeof record.error_code === 'string' ? record.error_code : undefined;
    return { detail, errorCode };
  } catch {
    return {};
  }
}

export async function executeStreamWithRetry(
  input: string,
  requestMessageId: string,
  state: ChatActionsState,
  actions: ChatActionsMethods,
  modelSelection: ModelSelection | null,
  abortController: AbortController,
  added: boolean,
  recievedMessage: string,
  resumeValue?: unknown,
  archiveRestoreActions?: ArchiveRestoreAction[],
): Promise<void> {
  let lastError: Error | null = null;

  for (let attempt = 0; attempt <= RETRY_MAX_ATTEMPTS; attempt++) {
    if (attempt > 0 && lastError) {
      const delay = retryDelay(attempt - 1);
      console.warn(`Stream request retry ${attempt}/${RETRY_MAX_ATTEMPTS} after ${delay}ms: ${lastError.message}`);
      await new Promise((resolve) => setTimeout(resolve, delay));

      if (abortController.signal.aborted) throw lastError;
    }

    try {
      const useMultiplexedStream = shouldUseMultiplexedAgentStream();
      const multiplexBridge = useMultiplexedStream
        ? createMultiplexReadableStream(requestMessageId, abortController.signal)
        : null;

      if (multiplexBridge) {
        const workspaceReady = await connectionManager.waitUntilReady(30_000);
        if (!workspaceReady.ok) {
          throw new Error(
            workspaceReady.err ?? 'Workspace multiplex stream not ready before agent-stream POST',
          );
        }
      }

      const res = await createMessageRequest(
        input,
        requestMessageId,
        { ...state, abortController },
        modelSelection,
        resumeValue,
        archiveRestoreActions,
      );

      if (!res.ok) {
        if (res.status === 409) {
          throw new AgentBusyError('Agent is busy processing another request for this session.');
        }

        const errorText = await res.text();
        const structuredError = parseStructuredHttpErrorPayload(errorText);
        if (!isRetryableHttpStatus(res.status)) {
          throw new FatalNetworkError(
            structuredError.detail || errorText || `Request failed with status ${res.status}`,
            {
              status: res.status,
              errorCode: structuredError.errorCode,
              detail: structuredError.detail,
              responseBody: errorText,
            },
          );
        }

        throw new Error(`[TransientHTTP] ${res.status}: ${errorText}`);
      }

      if (!res.body) throw new Error('No response body');

      const contentType = res.headers.get('content-type') || '';
      if (contentType.includes('application/json')) {
        if (!multiplexBridge) {
          throw new Error('Multiplexed agent-stream requires a browser environment');
        }
        let streamMessageId = requestMessageId;
        try {
          const accepted = (await res.clone().json()) as { message_id?: string };
          if (typeof accepted.message_id === 'string' && accepted.message_id.trim()) {
            streamMessageId = accepted.message_id.trim();
          }
        } catch {
          // fall back to request-scoped id
        }
        const effectiveBridge =
          streamMessageId === requestMessageId
            ? multiplexBridge
            : createMultiplexReadableStream(streamMessageId, abortController.signal);
        const mockResponse = new Response(effectiveBridge, {
          headers: { 'Content-Type': 'text/event-stream' },
        });

        await consumeStream(mockResponse, input, state, actions, abortController, added, recievedMessage);
      } else {
        await consumeStream(res, input, state, actions, abortController, added, recievedMessage);
      }
      await tryE2eAttachForPendingApproval(state, actions, abortController);
      return;
    } catch (error) {
      if (!(error instanceof Error)) throw error;
      if (error.name === 'AbortError') throw error;
      if (error instanceof AgentBusyError) throw error; // Don't retry busy errors
      if (error instanceof FatalNetworkError) throw error; // Fail-fast on 401/403 etc.

      if (error instanceof StreamInterruptedError) {
        if (state.chatId && (state.actionMode === 'agent' || state.actionMode === 'deep_research')) {
          console.warn('Stream interrupted, attempting to attach to chat in background...');
          const { attachToChat } = await import('./messageRequest');
          const { default: useChatStore } = await import('../useChatStore');

          let attachSuccess = false;
          for (let attachAttempt = 0; attachAttempt <= RETRY_MAX_ATTEMPTS; attachAttempt++) {
            if (attachAttempt > 0) {
              const delay = retryDelay(attachAttempt - 1);
              console.warn(`Attach retry ${attachAttempt}/${RETRY_MAX_ATTEMPTS} after ${delay}ms`);
              await new Promise((resolve) => setTimeout(resolve, delay));
              if (abortController.signal.aborted) throw error;
            }
            try {
              const attached = await attachToChat(state.chatId, actions, useChatStore.getState, {
                allowWhileLoading: true,
              });
              if (attached) {
                attachSuccess = true;
                break;
              } else {
                // If attach returns false (e.g. 404), it means the task is no longer running.
                // We must fetch the final state from the server to avoid UI getting stuck.
                console.log('Task finished during disconnect, fetching final messages...');
                await useChatStore.getState().loadMessages(state.chatId);
                attachSuccess = true;
                break;
              }
            } catch (attachError) {
              if (attachError instanceof FatalNetworkError) {
                console.error('Fatal attach error, breaking loop:', attachError);
                throw attachError; // Break the attach loop and bubble up
              }
              console.error('Attach failed:', attachError);
            }
          }
          if (attachSuccess) return;
        }
        throw error;
      }

      if (isTransientNetworkError(error) && attempt < RETRY_MAX_ATTEMPTS) {
        lastError = error;
        continue;
      }

      throw error;
    }
  }
}

export type ConsumeStreamOptions = {
  /** Stop once tool approval queue is populated (SHPOIB HITL attach recovery). */
  untilApprovalQueued?: boolean;
  /** Wall-clock cap in ms; only used with untilApprovalQueued. */
  maxWaitMs?: number;
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
  const reader = res.body!.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';
  const dataPrefix = 'data: ';
  let currentSseEvent = '';

  let lastDataTime = Date.now();
  const DATA_TIMEOUT = 5 * 60 * 1000;
  let firstDataReceived = false;
  let stoppedEarly = false;
  const recoveryDeadline =
    options?.maxWaitMs !== undefined ? Date.now() + Math.max(0, options.maxWaitMs) : null;

  const scheduler = new AdaptiveScheduler();

  const streamState: StreamHandlerState = {
    messages: state.messages,
    messageAppeared: state.messageAppeared,
    loading: state.loading,
    scheduler,
  };

  const streamActions: StreamHandlerActions = {
    setMessages: (updater) => {
      actions.setMessages((state) => updater(state));
    },
    setMessageAppeared: actions.setMessageAppeared,
    setLoading: actions.setLoading,
    _processSuggestions: actions._processSuggestions,
    scheduleAutoSave: actions.scheduleAutoSave,
  };

  try {
    while (true) {
      if (Date.now() - lastDataTime > DATA_TIMEOUT) {
        console.warn('Stream timeout: no data received for 5 minutes');
        throw new Error('Service response timeout, please try again');
      }

      if (abortController.signal.aborted) {
        throw new Error('AbortError');
      }

      let readResult;
      try {
        readResult = await reader.read();
      } catch (e) {
        if (firstDataReceived) {
          throw new StreamInterruptedError('Stream interrupted during reading', e as Error);
        }
        throw e;
      }
      const { value, done } = readResult;

      if (done) break;

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
              ({ added, recievedMessage } = await handleMessageStream(
                event,
                input,
                undefined,
                added,
                recievedMessage,
                streamState,
                streamActions,
                state.files,
              ));
              if (
                options?.untilApprovalQueued &&
                useToolApprovalStore.getState().queue.length > 0
              ) {
                stoppedEarly = true;
                break;
              }
            } catch (err) {
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
