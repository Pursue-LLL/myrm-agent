/**
 * [INPUT]
 * - @/lib/api::apiRequest (POS: 带鉴权与错误归一的 API 请求)
 * - @/lib/constants/compact-focus-topic::COMPACT_FOCUS_TOPIC_MAX_LENGTH (POS: 服务端接受的聚焦主题最大长度)
 * - @/lib/utils/firstChars::firstChars (POS: 按字符数截断文本，不拆开一个字符)
 * - @/store/useChatStore::refreshCompactionState (POS: 会话状态 store，压缩落库后的吸收入口；首次压缩时才加载)
 *
 * [OUTPUT]
 * - CompactResult: 一次手动压缩上下文的结果
 * - compactChat: 压缩会话上下文，可带聚焦主题
 * - runManualCompaction: 手动压缩，并把省下 token 的结果交给 store；输入框、`/compact`、策略面板三个入口共用
 * - CompactNotice / describeCompactSkip / COMPACT_FAILED_NOTICE: 服务端没有压缩时展示给用户的提示（文案键 + 严重度）
 * - DONT_REMIND_COMPACT_STORAGE_KEY: 「手动压缩前不再提醒」偏好的 localStorage 键
 *
 * [POS]
 * 上下文压缩的前端服务。聚焦主题发出前按服务端上限截断，所以输入框与 `/compact <主题>` 两条路径都不会被服务端拒收；
 * 压缩后的 store 同步与「没压缩」的措辞各只有一处，三个入口因此对同一次压缩给出同一个结果。
 */

import { apiRequest } from '@/lib/api';
import { COMPACT_FOCUS_TOPIC_MAX_LENGTH } from '@/lib/constants/compact-focus-topic';
import { firstChars } from '@/lib/utils/firstChars';

export interface CompactResult {
  compacted: boolean;
  message_count: number;
  tokens_saved: number;
  reason: string | null;
  focus_topic?: string;
  backup_path?: string | null;
}

/** Set once the user ticks "don't remind me" in the input box dialog; `/compact` reads it to skip its prompt-cache note. */
export const DONT_REMIND_COMPACT_STORAGE_KEY = 'dontRemindCompact';

export const compactChat = async (chatId: string, focusTopic?: string): Promise<CompactResult> => {
  // The server refuses a longer topic (HTTP 422); a topic typed after `/compact` has no box to stop it, so it is cut here.
  const body = focusTopic
    ? JSON.stringify({ focus_topic: firstChars(focusTopic, COMPACT_FOCUS_TOPIC_MAX_LENGTH) })
    : undefined;
  return (await apiRequest(`/chats/${chatId}/compact`, {
    method: 'POST',
    ...(body ? { body, headers: { 'Content-Type': 'application/json' } } : {}),
  })) as CompactResult;
};

export interface CompactNotice {
  /** Absolute locale key of the line the user reads. */
  messageKey: string;
  severity: 'info' | 'warning' | 'error';
}

const NOTHING_TO_COMPACT: CompactNotice = { messageKey: 'chat.compact.skip.nothing', severity: 'info' };
const ALREADY_RUNNING: CompactNotice = { messageKey: 'chat.compact.skip.busy', severity: 'info' };
const TEMPORARILY_PAUSED: CompactNotice = { messageKey: 'chat.compact.skip.paused', severity: 'warning' };
export const COMPACT_FAILED_NOTICE: CompactNotice = { messageKey: 'chat.compact.failed', severity: 'error' };

/** The server's reasons that are not failures. A reason is a bare code, so it is matched whole. */
const NOTICE_BY_REASON = new Map<string, CompactNotice>([
  ['no_compactable_messages', NOTHING_TO_COMPACT],
  ['too_few_messages', NOTHING_TO_COMPACT],
  ['concurrent_compaction_in_progress', ALREADY_RUNNING],
  ['summarize_circuit_open', TEMPORARILY_PAUSED],
]);

/**
 * What to tell the user about a request the server answered with `compacted: false`. Only reasons known to be benign
 * are worded as such: an unknown one (a timeout, a failed save, a code added later) must not read as "nothing to do".
 */
export function describeCompactSkip(reason: string | null): CompactNotice {
  return NOTICE_BY_REASON.get(reason ?? '') ?? COMPACT_FAILED_NOTICE;
}

/**
 * Compacts a chat on the user's request and hands a compaction that freed tokens to the store, so the summary banner,
 * the strategy panel and the usage ring catch up the same way whichever entry point asked. Messages are not rewritten
 * by a compaction, so none is reloaded.
 */
export async function runManualCompaction(chatId: string, focusTopic?: string): Promise<CompactResult> {
  const result = await compactChat(chatId, focusTopic);
  if (!result.compacted) {
    if (describeCompactSkip(result.reason).severity === 'error') {
      // The user reads a generic line; the server's reason is what a bug report needs.
      console.error('[Compaction] failed:', result.reason);
    }
    return result;
  }
  try {
    const { default: useChatStore } = await import('@/store/useChatStore');
    await useChatStore.getState().refreshCompactionState(chatId, {
      tokensSaved: result.tokens_saved,
      snapshotPath: result.backup_path ?? undefined,
    });
  } catch (error) {
    // The compaction happened; a store that could not take it must not turn it into a failure.
    console.error('[Compaction] store sync failed:', error);
  }
  return result;
}
