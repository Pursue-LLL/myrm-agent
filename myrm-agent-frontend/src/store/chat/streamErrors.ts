/**
 * [INPUT]
 * @/lib/utils/networkResilience::FatalNetworkError (POS: 不可重试网络错误基类)
 *
 * [OUTPUT]
 * AgentBusyError / RequestRefusedError / StreamInterruptedError: agent-stream 回合失败的分类错误
 * isAgentBusySseEvent: SSE error 帧是否为 busy 拒绝
 * isTransientNetworkError: 重试环路使用的瞬时网络错误判定
 *
 * [POS]
 * Chat agent-stream 错误分类 SSOT（叶子模块），供 streamConsumer / consumeStream 与 HITL resume 共用。
 */
import { FatalNetworkError } from '@/lib/utils/networkResilience';

export class AgentBusyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'AgentBusyError';
  }
}

/**
 * The agent-stream POST was answered with a non-retryable HTTP error: the server never took the turn.
 * Failures after the turn started (for example a refused re-attach) stay plain `FatalNetworkError`s.
 */
export class RequestRefusedError extends FatalNetworkError {}

/** Backend agent-stream busy uses HTTP 200 + SSE error (status_code 409 in payload). */
export function isAgentBusySseEvent(event: { type: string } & Record<string, unknown>): boolean {
  if (!event || event.type !== 'error') {
    return false;
  }
  if (event.error_type === 'AgentBusyError') {
    return true;
  }
  return event.status_code === 409;
}

export class StreamInterruptedError extends Error {
  originalError?: Error;
  constructor(message: string, originalError?: Error) {
    super(message);
    this.name = 'StreamInterruptedError';
    this.originalError = originalError;
  }
}

export function isTransientNetworkError(error: Error): boolean {
  if (error instanceof FatalNetworkError) {
    return false;
  }
  return (
    error instanceof TypeError ||
    error.message.includes('Failed to fetch') ||
    error.message.includes('NetworkError') ||
    error.message.includes('ERR_CONNECTION') ||
    error.message.includes('[TransientHTTP]')
  );
}
