/**
 * [POS]
 * Chat SSE event handler slice (memoryBriefEvents).
 */

import type { MemoryBriefData } from '@/store/chat/types';
import type { StreamCtx, StreamTurn } from "../streamContext";
import { done } from "../streamContext";
import * as H from "./handlerDeps";

function _asStringArray(raw: unknown): string[] {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.filter((item): item is string => typeof item === 'string' && item.trim().length > 0);
}

function normalizeMemoryBrief(raw: unknown): MemoryBriefData | null {
  if (!raw || typeof raw !== 'object') {
    return null;
  }
  const obj = raw as Record<string, unknown>;
  const snapshotId = typeof obj.snapshot_id === 'string' ? obj.snapshot_id.trim() : '';
  if (!snapshotId) {
    return null;
  }
  const stableRaw = obj.stable && typeof obj.stable === 'object' ? (obj.stable as Record<string, unknown>) : {};
  const learnedRaw = obj.learned && typeof obj.learned === 'object' ? (obj.learned as Record<string, unknown>) : {};
  return {
    snapshot_id: snapshotId,
    generated_at_ms: typeof obj.generated_at_ms === 'number' ? obj.generated_at_ms : Date.now(),
    namespaces: _asStringArray(obj.namespaces),
    is_cold_start: Boolean(obj.is_cold_start),
    stable: {
      working_state: Boolean(stableRaw.working_state),
      profile_keys: _asStringArray(stableRaw.profile_keys),
      instruction_count: typeof stableRaw.instruction_count === 'number' ? stableRaw.instruction_count : 0,
      rule_count: typeof stableRaw.rule_count === 'number' ? stableRaw.rule_count : 0,
    },
    learned: {
      preference_count: typeof learnedRaw.preference_count === 'number' ? learnedRaw.preference_count : 0,
      rule_count: typeof learnedRaw.rule_count === 'number' ? learnedRaw.rule_count : 0,
      correction_count: typeof learnedRaw.correction_count === 'number' ? learnedRaw.correction_count : 0,
      preference_ids: _asStringArray(learnedRaw.preference_ids),
      rule_ids: _asStringArray(learnedRaw.rule_ids),
    },
  };
}

export async function memoryBriefEvents(ctx: StreamCtx): Promise<StreamTurn | null> {
  const { data, actions } = ctx;
  if (data.type !== H.AgentEventType.MEMORY_BRIEF) {
    return null;
  }

  const brief = normalizeMemoryBrief(data.data);
  if (!brief) {
    return done(ctx);
  }

  actions.setMessages((state) => {
    const messageIndex = H.findAssistantMessageIndex(state.messages, data.messageId);
    if (messageIndex === -1) {
      state.messages.push({
        content: '',
        messageId: data.messageId,
        chatId: state.messages[0]?.chatId || '',
        role: 'assistant',
        createdAt: new Date(),
        memoryBrief: brief,
        memoryBriefSnapshotId: brief.snapshot_id,
      });
      ctx.added = true;
    } else {
      state.messages[messageIndex].memoryBrief = brief;
      state.messages[messageIndex].memoryBriefSnapshotId = brief.snapshot_id;
    }
    if (!state.messageAppeared) {
      state.messageAppeared = true;
    }
  });

  return done(ctx);
}

