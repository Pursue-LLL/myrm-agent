/**
 * [INPUT]
 * ./consumeStream::consumeStream (POS: 单段 SSE 消费循环)
 * ./streamErrors (POS: busy / refused / interrupted 错误分类)
 * ./messageRequest::createMessageRequest (POS: agent-stream POST)
 * @/lib/utils/networkResilience::abortableDelay (POS: 网络韧性策略层，统一重试与 fail-fast 决策)
 *
 * [OUTPUT]
 * executeStreamWithRetry: 网络重试、AgentBusyError / ApprovalAlreadyResolvedError（resume 命中已被他人处理的中断，HTTP 409：超时或另一设备，服务端不区分）fail-fast、中断后 attach 恢复；两类退避等待均可被用户 Stop 立即中止（AbortError 直接抛出）；回合正文只从 POST 响应体（SSE）读取；turn 成功后 finalizeAgentStreamTurn
 *
 * [POS]
 * Chat agent-stream 前端回合编排 SSOT。busy 检测：SSE error_type=AgentBusyError（HTTP 200）；resume 收到 HTTP 409 表示该中断已被他人处理（`ApprovalAlreadyResolvedError`，可能是超时也可能是另一设备），非 resume 的 409 按普通拒绝处理；pinned workflow template 仅在 agent-stream POST 成功（res.ok）后清除；回合正文一律从 POST 响应体读取（multiplex 传输已移除），非 SSE 响应按协议错误拒绝。
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
import { resolveChatWikiEvidenceContext } from '@/services/wiki/evidenceContextCore';
import { recordWikiQuerySubmitted } from '@/services/wiki/evidenceMetrics';
import { consumePendingChatWikiQuerySuccess } from '@/services/wiki/evidenceQuerySuccessPendingCore';
import { resolveE2eApiBase } from '@/lib/deploy-mode';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import { finalizeAgentStreamTurn } from '@/store/chat/chatAgentSessionRestore';
import { consumeStream } from './consumeStream';
import {
  AgentBusyError,
  ApprovalAlreadyResolvedError,
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
  const expectedQuerySuccessMessageId = normalizeMessageId(requestMessageId);
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
        // whose interrupt someone else (the timeout or another device) has already resolved.
        if (res.status === 409 && resumeValue !== undefined) {
          throw new ApprovalAlreadyResolvedError();
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
        // 非流式 JSON 只可能来自未开启 SSE 的旧协议或代理改写：回合正文无处可读，明确拒绝而不是空等。
        const accepted = (await res.text()).slice(0, 200);
        throw new RequestRefusedError(`agent-stream returned JSON instead of SSE: ${accepted}`);
      }

      await consumeStream(res, input, state, actions, abortController, added, recievedMessage, { onBusinessEvent });
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
      if (error instanceof AgentBusyError || error instanceof ApprovalAlreadyResolvedError) {
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
