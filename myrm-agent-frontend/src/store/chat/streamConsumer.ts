/**
 * [INPUT]
 * ./consumeStream::consumeStream (POS: 单段 SSE 消费循环)
 * ./streamErrors (POS: busy / refused / interrupted 错误分类)
 * ./messageRequest::createMessageRequest (POS: agent-stream POST)
 * ./multiplexChunkBridge::createMultiplexReadableStream (POS: workspace multiplex 桥)
 * @/lib/utils/networkResilience::abortableDelay (POS: 网络韧性策略层，统一重试与 fail-fast 决策)
 *
 * [OUTPUT]
 * executeStreamWithRetry: 网络重试、AgentBusyError / ApprovalExpiredError（resume 命中已被超时处理的中断，HTTP 409）fail-fast、multiplex 分流、中断后 attach 恢复；两类退避等待均可被用户 Stop 立即中止（AbortError 直接抛出），Stop 发生在 multiplex 就绪门等待期间时门返回后同样以 AbortError 结束且不构造请求；turn 成功后 finalizeAgentStreamTurn
 * shouldUseMultiplexedAgentStream: 本轮 chunk 走 workspace multiplex 还是 POST 响应体（请求体 multiplexed 字段与消费端共用此判定）
 *
 * [POS]
 * Chat agent-stream 前端回合编排 SSOT。busy 检测：SSE error_type=AgentBusyError（HTTP 200）；resume 收到 HTTP 409 表示该中断已被超时处理（`ApprovalExpiredError`），非 resume 的 409 按普通拒绝处理；pinned workflow template 仅在 agent-stream POST 成功（res.ok）后清除；multiplex 下 early-terminal SSE 直读 POST。
 */
import { consumeMigrationBoundProjectId, syncChatSidebarProjectId } from '@/lib/migrationChatHandoff';
import { releaseTurnInspectorControls } from '@/lib/inspector/releaseTurnInspectorControls';
import type { ChatActionsState, ChatActionsMethods } from './messageRequest';
import {
  type AgentStreamEvent,
  type ArchiveRestoreAction,
  type TurnCapabilityTerminalTelemetry,
  ModelSelection,
} from './types';
import { abortableDelay, isRetryableHttpStatus, FatalNetworkError } from '@/lib/utils/networkResilience';
import { createMultiplexReadableStream } from './multiplexChunkBridge';
import { connectionManager } from '@/services/ConnectionManager';
import { resolveChatWikiEvidenceContext } from '@/services/wiki/evidenceContextCore';
import { recordWikiQuerySubmitted } from '@/services/wiki/evidenceMetrics';
import { consumePendingChatWikiQuerySuccess } from '@/services/wiki/evidenceQuerySuccessPendingCore';
import { resolveE2eApiBase } from '@/lib/deploy-mode';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import { finalizeAgentStreamTurn } from '@/store/chat/chatAgentSessionRestore';
import { consumeStream } from './consumeStream';
import {
  AgentBusyError,
  ApprovalExpiredError,
  RequestRefusedError,
  StreamInterruptedError,
  isTransientNetworkError,
} from './streamErrors';

function finalizeMigrationBoundProjectHandoff(chatId: string | undefined): void {
  const boundProjectId = consumeMigrationBoundProjectId();
  if (boundProjectId && chatId?.trim()) {
    syncChatSidebarProjectId(chatId.trim(), boundProjectId);
  }
}

/**
 * Whether this turn's chunks arrive over the workspace multiplex stream instead of the POST response body.
 * The request body (`multiplexed`) and the consumer must read the same answer. Private-backend Chrome E2E tees
 * agent-stream chunks on /workspace/stream, so it keeps multiplex on and only the direct-SSE flag opts out.
 */
export function shouldUseMultiplexedAgentStream(): boolean {
  return typeof window === 'undefined' || !window.__MYRM_E2E_DIRECT_SSE__;
}

async function drainResponseBodyInBackground(res: Response): Promise<void> {
  const body = res.body;
  if (!body) {
    return;
  }
  try {
    const reader = body.getReader();
    while (true) {
      const { done } = await reader.read();
      if (done) {
        break;
      }
    }
  } catch {
    // Multiplex workspace path owns event delivery for this turn.
  }
}

export async function tryE2eAttachForPendingApproval(
  state: ChatActionsState,
  actions: ChatActionsMethods,
  _abortController: AbortController,
): Promise<{ attached: boolean; queueLen: number; attempt: number }> {
  if (typeof window === 'undefined') {
    return { attached: false, queueLen: 0, attempt: 0 };
  }
  if (!window.__MYRM_E2E_DIRECT_SSE__ && !resolveE2eApiBase()) {
    return { attached: false, queueLen: 0, attempt: 0 };
  }
  const chatId = state.chatId?.trim();
  if (!chatId || useToolApprovalStore.getState().queue.length > 0) {
    return {
      attached: false,
      queueLen: useToolApprovalStore.getState().queue.length,
      attempt: 0,
    };
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

const RETRY_INITIAL_DELAY_MS = 2000;
const RETRY_BACKOFF_FACTOR = 1.5;
const RETRY_MAX_ATTEMPTS = 10; // Covers a slow backend restart: exponential backoff waits about 3.8 minutes in total.

interface StructuredHttpErrorPayload {
  detail?: string;
  errorCode?: string;
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

function normalizeMessageId(value: string | undefined): string | undefined {
  const normalized = value?.trim();
  return normalized && normalized.length > 0 ? normalized : undefined;
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
  shouldRecordWikiQuerySuccess: boolean = false,
  turnCapabilityTelemetry?: TurnCapabilityTerminalTelemetry,
): Promise<void> {
  let lastError: Error | null = null;
  let querySuccessRecorded = false;
  let expectedQuerySuccessMessageId = normalizeMessageId(requestMessageId);
  const onBusinessEvent = (event: AgentStreamEvent): void => {
    const eventMessageId = normalizeMessageId(event.messageId);
    const pendingSteerSuccess = consumePendingChatWikiQuerySuccess(state.chatId, eventMessageId);
    if (pendingSteerSuccess) {
      recordWikiQuerySubmitted('chat', pendingSteerSuccess.contextKey, pendingSteerSuccess.turnDistance);
    }

    if (!shouldRecordWikiQuerySuccess || resumeValue !== undefined || querySuccessRecorded) {
      return;
    }
    if (expectedQuerySuccessMessageId && eventMessageId && eventMessageId !== expectedQuerySuccessMessageId) {
      return;
    }
    if (expectedQuerySuccessMessageId && !eventMessageId) {
      return;
    }

    const context = resolveChatWikiEvidenceContext(state.messages, state.chatId);
    recordWikiQuerySubmitted('chat', context.contextKey, context.turnDistance);
    querySuccessRecorded = true;
  };

  for (let attempt = 0; attempt <= RETRY_MAX_ATTEMPTS; attempt++) {
    if (attempt > 0 && lastError) {
      const delay = retryDelay(attempt - 1);
      console.warn(`Stream request retry ${attempt}/${RETRY_MAX_ATTEMPTS} after ${delay}ms: ${lastError.message}`);
      // A stop ends the wait with an AbortError, so the turn ends quietly.
      await abortableDelay(delay, abortController.signal);
    }

    try {
      const useMultiplexedStream = shouldUseMultiplexedAgentStream();
      const multiplexBridge = useMultiplexedStream
        ? createMultiplexReadableStream(requestMessageId, abortController.signal)
        : null;

      if (multiplexBridge) {
        const workspaceReady = await connectionManager.waitUntilReady(30_000);
        // The gate cannot be interrupted: a stop that arrived while it waited ends the turn here, before any
        // request is built and without reporting the gate's verdict for a turn nobody is waiting for anymore.
        abortController.signal.throwIfAborted();
        if (!workspaceReady.ok) {
          const gateError = new Error(
            workspaceReady.err ?? 'Workspace multiplex stream not ready before agent-stream POST',
          );
          // Nothing was posted before the first attempt, so a failure the loop would not retry means the turn
          // never started. After a failed POST the server may already hold the turn, which stays an ordinary failure.
          if (attempt === 0 && !isTransientNetworkError(gateError)) {
            throw new RequestRefusedError(gateError.message);
          }
          throw gateError;
        }
      }

      // Lazy: messageRequest imports this module, so a static import would form a cycle.
      const { createMessageRequest } = await import('./messageRequest');
      const res = await createMessageRequest(
        input,
        requestMessageId,
        { ...state, abortController },
        modelSelection,
        resumeValue,
        archiveRestoreActions,
        turnCapabilityTelemetry,
      );
      if (!res.ok) {
        // A busy chat answers HTTP 200 with an SSE error frame; the server answers a bare 409 only to a resume
        // whose interrupt the timeout has already resolved.
        if (res.status === 409 && resumeValue !== undefined) {
          throw new ApprovalExpiredError();
        }

        const errorText = await res.text();
        const structuredError = parseStructuredHttpErrorPayload(errorText);
        if (!isRetryableHttpStatus(res.status)) {
          throw new RequestRefusedError(
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

      actions.clearPendingWorkflowTemplate();

      finalizeMigrationBoundProjectHandoff(state.chatId);

      if (!res.body) {
        throw new Error('No response body');
      }

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
            expectedQuerySuccessMessageId = streamMessageId;
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

        await consumeStream(mockResponse, input, state, actions, abortController, added, recievedMessage, {
          onBusinessEvent,
        });
      } else if (multiplexBridge) {
        // Multiplex success returns JSON accepted; text/event-stream on POST is an early
        // terminal response (AgentBusyError, risk_blocked, etc.) — must not drain it.
        if (contentType.includes('text/event-stream')) {
          await consumeStream(res, input, state, actions, abortController, added, recievedMessage, { onBusinessEvent });
        } else {
          void drainResponseBodyInBackground(res);
          const mockResponse = new Response(multiplexBridge, {
            headers: { 'Content-Type': 'text/event-stream' },
          });
          await consumeStream(mockResponse, input, state, actions, abortController, added, recievedMessage, {
            onBusinessEvent,
          });
        }
      } else {
        await consumeStream(res, input, state, actions, abortController, added, recievedMessage, { onBusinessEvent });
      }
      await tryE2eAttachForPendingApproval(state, actions, abortController);
      await finalizeAgentStreamTurn(state.chatId);
      return;
    } catch (error) {
      if (!(error instanceof Error)) {
        throw error;
      }
      if (error.name === 'AbortError') {
        throw error;
      }
      if (error instanceof AgentBusyError || error instanceof ApprovalExpiredError) {
        throw error;
      } // Don't retry busy or already-resolved resumes
      if (error instanceof FatalNetworkError) {
        throw error;
      } // Fail-fast on 401/403 etc.

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
              await abortableDelay(delay, abortController.signal);
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
                // Attach false is the deterministic "task finished" signal; release any
                // desktop/browser inspector control this turn engaged, even when the
                // final state fetch below fails, so the UI never stays "controlling".
                void releaseTurnInspectorControls(state.chatId);
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
          if (attachSuccess) {
            return;
          }
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
