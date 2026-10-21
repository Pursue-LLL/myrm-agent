/**
 * [INPUT]
 * @/store/chat/types::ProgressItem (POS: Task Steps entry of a message)
 *
 * [OUTPUT]
 * attachEvictedRef: files a tool_evicted_ref payload onto the step that produced the evicted output
 *
 * [POS]
 * TOOL_EVICTED_REF reducer body of toolLifecycleEvents. `steps` are the draft steps handed out by
 * `actions.setMessages`.
 */

import type { ProgressItem } from '@/store/chat/types';

type EvictedRefPayload = {
  ref: string;
  toolCallId?: string;
  previewStdout?: string;
  toolName?: string;
  storedChars?: number;
  totalLines?: number;
  storageTruncated?: boolean;
  isStderr: boolean;
};

/** A bare string is the legacy payload (the ref alone); the object payload names the step and the stream. */
function parseEvictedRefPayload(rawPayload: unknown): EvictedRefPayload | null {
  if (typeof rawPayload === 'string') {
    return rawPayload ? { ref: rawPayload, isStderr: false } : null;
  }
  if (!rawPayload || typeof rawPayload !== 'object') {
    return null;
  }
  const payload = rawPayload as Record<string, unknown>;
  if (typeof payload.evicted_ref !== 'string' || !payload.evicted_ref) {
    return null;
  }
  return {
    ref: payload.evicted_ref,
    toolCallId: typeof payload.tool_call_id === 'string' ? payload.tool_call_id : undefined,
    previewStdout: typeof payload.preview_stdout === 'string' ? payload.preview_stdout : undefined,
    toolName: typeof payload.tool_name === 'string' ? payload.tool_name : undefined,
    storedChars:
      typeof payload.stored_chars === 'number' && payload.stored_chars > 0 ? payload.stored_chars : undefined,
    totalLines: typeof payload.total_lines === 'number' && payload.total_lines > 0 ? payload.total_lines : undefined,
    storageTruncated: payload.storage_truncated === true ? true : undefined,
    isStderr: payload.stream === 'stderr',
  };
}

/** The step the payload names; else the newest step of the same tool that has not claimed this stream; else the last. */
function findEvictedRefTarget(steps: ProgressItem[], payload: EvictedRefPayload): ProgressItem {
  const byCallId =
    payload.toolCallId !== undefined ? steps.find((step) => step.tool_call_id === payload.toolCallId) : undefined;
  if (byCallId) {
    return byCallId;
  }
  if (payload.toolName) {
    for (let index = steps.length - 1; index >= 0; index -= 1) {
      const step = steps[index];
      const alreadyClaimed = payload.isStderr ? step.evicted_stderr_file_ref : step.evicted_file_ref;
      if (step.tool_name === payload.toolName && !alreadyClaimed) {
        return step;
      }
    }
  }
  return steps[steps.length - 1];
}

export function attachEvictedRef(steps: ProgressItem[], rawPayload: unknown): void {
  const payload = parseEvictedRefPayload(rawPayload);
  if (!payload) {
    return;
  }
  const target = findEvictedRefTarget(steps, payload);

  if (payload.isStderr) {
    target.evicted_stderr_file_ref = payload.ref;
    if (payload.storedChars !== undefined) {
      target.evicted_stderr_stored_chars = payload.storedChars;
    }
    if (payload.totalLines !== undefined) {
      target.evicted_stderr_total_lines = payload.totalLines;
    }
    if (payload.storageTruncated === true) {
      target.evicted_stderr_storage_truncated = true;
    }
    return;
  }

  target.evicted_file_ref = payload.ref;
  if (payload.previewStdout) {
    target.stdout = payload.previewStdout;
  }
  if (payload.storedChars !== undefined) {
    target.evicted_stored_chars = payload.storedChars;
  }
  if (payload.totalLines !== undefined) {
    target.evicted_total_lines = payload.totalLines;
  }
  if (payload.storageTruncated === true) {
    target.evicted_storage_truncated = true;
  }
}
