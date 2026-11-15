/**
 * [INPUT]
 * - @/services/chat::ChatItem (type only; POS: one row of the sidebar chat list)
 * - @/lib/utils/typeUtils::isRecord (POS: guard for parsed JSON)
 *
 * [OUTPUT]
 * - chatHistoryFilterKey: which list a stored page belongs to.
 * - encodeChatHistory / decodeChatHistory: the `chatHistory` section, one page of the sidebar list.
 * - CHAT_HISTORY_SNAPSHOT_LIMIT / CHAT_PREVIEW_MAX_CHARS: how many rows and how much of each preview are kept.
 *
 * [POS]
 * Codec of the `chatHistory` section. Only the fields a sidebar row draws are stored: title, flags, times and the one-line
 * preview of the last message, cut to what the widest sidebar can show. The preview is stored so a restored row has the
 * height of the row the server's data produces; without it every row with a preview would grow when the server answers
 * and the list would jump under the pointer. Nothing else of a message is stored. Decoding trusts nothing: a row that is
 * not shaped like a chat is dropped.
 */
import type { ChatItem } from '@/services/chat';
import { isRecord } from '@/lib/utils/typeUtils';

/** One page of the sidebar list: what a restore shows until the server's first page arrives. */
export const CHAT_HISTORY_SNAPSHOT_LIMIT = 20;
/** A row shows one truncated line of the last message: about 60 characters at the widest sidebar (450px). */
export const CHAT_PREVIEW_MAX_CHARS = 80;

export interface ChatHistorySnapshot {
  /** The list this page belongs to: the project filter decides what the sidebar lists. */
  filterKey: string;
  items: ChatItem[];
}

interface StoredChat {
  id: string;
  title: string;
  lastMessage: string;
  actionMode: string;
  source: string;
  isCompacted: boolean;
  isPinned: boolean;
  pinOrder: number;
  projectId: string | null;
  tags: string[];
  updatedAt: number;
  createdAt: number;
}

interface StoredChatHistory {
  filterKey: string;
  items: StoredChat[];
}

export function chatHistoryFilterKey(projectFilter: string | null | undefined): string {
  if (projectFilter === undefined) {
    return 'all';
  }
  return projectFilter === null ? 'unassigned' : `project:${projectFilter}`;
}

/** The first CHAT_PREVIEW_MAX_CHARS UTF-16 units, without the lone half of an emoji the cut may leave at the end. */
function cutPreview(text: string): string {
  const cut = text.slice(0, CHAT_PREVIEW_MAX_CHARS);
  const last = cut.charCodeAt(cut.length - 1);
  const endsInHighSurrogate = last >= 0xd800 && last <= 0xdbff;
  return endsInHighSurrogate ? cut.slice(0, -1) : cut;
}

function encodeChat(chat: ChatItem): StoredChat {
  return {
    id: chat.id,
    title: chat.title,
    lastMessage: cutPreview(chat.lastMessage),
    actionMode: chat.actionMode,
    source: chat.source,
    isCompacted: chat.isCompacted === true,
    isPinned: chat.isPinned === true,
    pinOrder: chat.pinOrder ?? 0,
    projectId: chat.projectId ?? null,
    tags: chat.tags ?? [],
    updatedAt: chat.updatedAt.getTime(),
    createdAt: chat.createdAt.getTime(),
  };
}

export function encodeChatHistory(filterKey: string, items: readonly ChatItem[]): StoredChatHistory {
  return { filterKey, items: items.slice(0, CHAT_HISTORY_SNAPSHOT_LIMIT).map(encodeChat) };
}

function isTimestamp(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function decodeChat(raw: unknown): ChatItem | null {
  if (!isRecord(raw) || typeof raw.id !== 'string' || raw.id === '' || typeof raw.title !== 'string') {
    return null;
  }
  if (!isTimestamp(raw.updatedAt) || !isTimestamp(raw.createdAt)) {
    return null;
  }
  return {
    id: raw.id,
    title: raw.title,
    firstMessage: '',
    lastMessage: typeof raw.lastMessage === 'string' ? raw.lastMessage : '',
    actionMode: typeof raw.actionMode === 'string' ? raw.actionMode : 'fast',
    source: typeof raw.source === 'string' ? raw.source : 'web',
    isCompacted: raw.isCompacted === true,
    isPinned: raw.isPinned === true,
    pinOrder: isTimestamp(raw.pinOrder) ? raw.pinOrder : 0,
    projectId: typeof raw.projectId === 'string' ? raw.projectId : null,
    tags: Array.isArray(raw.tags) ? raw.tags.filter((tag): tag is string => typeof tag === 'string') : [],
    updatedAt: new Date(raw.updatedAt),
    createdAt: new Date(raw.createdAt),
  };
}

export function decodeChatHistory(raw: unknown): ChatHistorySnapshot | null {
  if (!isRecord(raw) || typeof raw.filterKey !== 'string' || !Array.isArray(raw.items)) {
    return null;
  }
  const items = raw.items.map(decodeChat).filter((chat): chat is ChatItem => chat !== null);
  return { filterKey: raw.filterKey, items: items.slice(0, CHAT_HISTORY_SNAPSHOT_LIMIT) };
}
