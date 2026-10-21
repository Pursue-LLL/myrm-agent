/**
 * [INPUT]
 * ./toolEndMessage::applyToolEndToMessage (POS: TOOL_END reducer body)
 * ./toolEvictedRef::attachEvictedRef (POS: TOOL_EVICTED_REF reducer body)
 *
 * [OUTPUT]
 * toolLifecycleEvents: tool_start / tool_end / tool_failure / tool_stdout_chunk / tool_evicted_ref / tool_cancelled
 *
 * [POS]
 * Chat SSE event handler slice (toolLifecycleEvents). Message state is read and written only inside
 * `actions.setMessages` callbacks: `ctx.state.messages` is the snapshot taken when the stream opened, so it never
 * holds the assistant message of the running turn.
 */

import type { ProgressItem } from '@/store/chat/types';
import type { StreamCtx, StreamTurn } from '../streamContext';
import { done } from '../streamContext';
import { applyToolEndToMessage } from './toolEndMessage';
import { attachEvictedRef } from './toolEvictedRef';
import * as H from './handlerDeps';

const MAX_STEP_STDOUT_CHARS = 30000;

/** Runs `update` on the Task Steps of assistant message `messageId`; nothing happens while it has none. */
function updateProgressSteps(ctx: StreamCtx, messageId: string, update: (steps: ProgressItem[]) => void): void {
  ctx.actions.setMessages((draft) => {
    const messageIndex = H.findAssistantMessageIndex(draft.messages, messageId);
    const steps = messageIndex === -1 ? undefined : draft.messages[messageIndex].progressSteps;
    if (steps && steps.length > 0) {
      update(steps);
    }
  });
}

function appendStdout(step: ProgressItem, chunk: string): void {
  const stdout = (step.stdout || '') + chunk;
  if (stdout.length <= MAX_STEP_STDOUT_CHARS) {
    step.stdout = stdout;
    return;
  }
  const tail = stdout.slice(-MAX_STEP_STDOUT_CHARS);
  const newlineIndex = tail.indexOf('\n');
  step.stdout =
    '...[Terminal output truncated to preserve memory]...\n' +
    (newlineIndex !== -1 ? tail.substring(newlineIndex + 1) : tail);
}

function describeCancellation(cancelReason: string | undefined, error: string | undefined): string {
  if (cancelReason === 'user_cancelled') {
    return 'Cancelled by user';
  }
  if (cancelReason === 'timeout') {
    return 'Cancelled (timeout)';
  }
  if (cancelReason === 'session_ended') {
    return 'Cancelled (session ended)';
  }
  return error || 'Tool execution was cancelled';
}

export async function toolLifecycleEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, state } = ctx;
  if (data.type === H.AgentEventType.TOOL_START) {
    ctx.recievedMessage = '';

    const toolName = data.tool_name ?? '';
    const streamChatId = H.resolveStreamChatId(state);
    if (toolName.startsWith('browser_')) {
      const { default: inspectorStore } = await import('@/store/useBrowserInspectorStore');
      inspectorStore.getState().setBrowserActive(true);
      inspectorStore.getState().markTurnEngaged(streamChatId);
      if (H.isStreamForOpenChat(state)) {
        inspectorStore.getState().openPanel();
      }
    }
    if (toolName.startsWith('desktop_')) {
      const { default: desktopStore } = await import('@/store/useDesktopInspectorStore');
      desktopStore.getState().setDesktopActive(true);
      desktopStore.getState().markTurnEngaged(streamChatId);
    }

    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOL_END) {
    ctx.actions.setMessages((draft) => {
      const messageIndex = H.findAssistantMessageIndex(draft.messages, data.messageId);
      if (messageIndex !== -1) {
        applyToolEndToMessage(draft.messages[messageIndex], data);
      }
    });

    if (data.tool_name?.startsWith('desktop_') && data.tool_name !== 'desktop_snapshot_tool') {
      // desktop_snapshot_tool already pushed refs via DESKTOP_VIEW_UPDATE SSE;
      // re-fetch here would re-capture the wrong foreground window (e.g. Chrome).
      const { default: desktopStore } = await import('@/store/useDesktopInspectorStore');
      if (H.isStreamForOpenChat(state)) {
        void desktopStore.getState().fetchSnapshot(true);
      }
    }

    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOL_FAILURE) {
    updateProgressSteps(ctx, data.messageId, (steps) => {
      const lastStep = steps[steps.length - 1];
      if (data.duration_ms != null) {
        lastStep.duration_ms = data.duration_ms;
      }
      lastStep.status = 'error';
      lastStep.error = data.error;
      lastStep.fault_side = data.fault_side;
    });
    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOL_STDOUT_CHUNK) {
    updateProgressSteps(ctx, data.messageId, (steps) => appendStdout(steps[steps.length - 1], data.data));
    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOL_EVICTED_REF) {
    updateProgressSteps(ctx, data.messageId, (steps) => attachEvictedRef(steps, data.data));
    return done(ctx);
  }

  if (data.type === H.AgentEventType.TOOL_CANCELLED) {
    updateProgressSteps(ctx, data.messageId, (steps) => {
      const lastStep = steps[steps.length - 1];
      if (data.duration_ms != null) {
        lastStep.duration_ms = data.duration_ms;
      }
      lastStep.status = 'warning';
      lastStep.error = describeCancellation(data.cancel_reason, data.error);
    });
    return done(ctx);
  }

  return null;
}
