/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: Active chat state manager.)
 * - @/components/dev/e2eBridge/submitAndObserveTurn::recordActiveTurnEvent (POS: 发送并观察一个聊天回合的流水线编排)
 * - @/components/dev/e2eBridge/members/types::E2eBridgeMembers (POS: 桥成员分组的类型)
 *
 * [OUTPUT]
 * - createSseCapture(): `record` (the `window.__MYRM_E2E_RECORD_SSE__` recorder) and the bridge members that read, clear and scope the captured SSE events
 * - SseEventRecorder
 *
 * [POS]
 * 页面侧 SSE 事件捕获：保留最近 64 条事件（可按消息 id 圈定），并向桥暴露读取与清空入口。
 */
import useChatStore from '@/store/useChatStore';
import { recordActiveTurnEvent } from '@/components/dev/e2eBridge/submitAndObserveTurn';
import type { E2eBridgeMembers } from '@/components/dev/e2eBridge/members/types';

export type SseEventRecorder = (type: string, messageId?: string | null, data?: unknown) => void;

/** Per-mount SSE capture: the recorder the stream handlers call, and the bridge members that read, clear and scope what it kept. */
export function createSseCapture(): { record: SseEventRecorder; members: E2eBridgeMembers } {
  const sseEvents: Array<{ type: string; messageId: string | null; data?: unknown }> = [];
  let sseCaptureMessageId: string | null = null;
  let sseCaptureLocked = false;
  const record: SseEventRecorder = (type: string, messageId?: string | null, data?: unknown) => {
    recordActiveTurnEvent(type);
    if (sseCaptureLocked) {
      const normalizedId = typeof messageId === 'string' && messageId.trim() ? messageId.trim() : null;
      if (type !== 'capability_gap' || !normalizedId) {
        return;
      }
      sseCaptureMessageId = normalizedId;
      sseCaptureLocked = false;
    }
    const normalizedId = typeof messageId === 'string' && messageId.trim() ? messageId.trim() : null;
    if (sseCaptureMessageId && normalizedId !== sseCaptureMessageId) {
      return;
    }
    sseEvents.push({
      type,
      messageId: normalizedId,
      data,
    });
    if (sseEvents.length > 64) {
      sseEvents.splice(0, sseEvents.length - 64);
    }
  };

  const members = {
    sseSnapshot: (messageId?: string | null) => {
      const filterId = typeof messageId === 'string' ? messageId.trim() : '';
      if (!filterId) {
        return sseEvents.map((entry) => entry.type);
      }
      return sseEvents.filter((entry) => entry.messageId === filterId).map((entry) => entry.type);
    },
    // Event types alone cannot tell a web_search call from a web_fetch call; signoffs that need to know
    // which tool actually ran read the captured payloads instead.
    ssePayloadSnapshot: (messageId?: string | null) => {
      const filterId = typeof messageId === 'string' ? messageId.trim() : '';
      const scoped = filterId ? sseEvents.filter((entry) => entry.messageId === filterId) : sseEvents;
      return scoped.map((entry) => ({ type: entry.type, data: entry.data }));
    },
    clearSseSnapshot: () => {
      sseEvents.length = 0;
      sseCaptureMessageId = null;
      sseCaptureLocked = true;
    },
    allocateStreamMessageId: () => useChatStore.getState().allocateNewSessionMessageId(),
    setSseCaptureMessageId: (messageId: string | null | undefined) => {
      sseCaptureMessageId = typeof messageId === 'string' && messageId.trim() ? messageId.trim() : null;
      sseCaptureLocked = false;
    },
  } as E2eBridgeMembers;

  return { record, members };
}
