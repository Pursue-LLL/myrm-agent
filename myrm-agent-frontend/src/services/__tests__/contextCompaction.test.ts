import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '@/lib/api';
import { COMPACT_FOCUS_TOPIC_MAX_LENGTH } from '@/lib/constants/compact-focus-topic';
import { compactChat, describeCompactSkip, runManualCompaction } from '@/services/contextCompaction';
import en from '../../../locales/en.json';
import zh from '../../../locales/zh.json';

const refreshCompactionState = vi.hoisted(() => vi.fn());

vi.mock('@/lib/api', () => ({
  API_BASE_URL: '',
  apiRequest: vi.fn(),
  fetchWithTimeout: vi.fn(),
}));

vi.mock('@/store/useChatStore', () => ({ default: { getState: () => ({ refreshCompactionState }) } }));

const apiRequestMock = vi.mocked(apiRequest);
const RARE_HAN = String.fromCodePoint(0x20bb7);

/** The focus topic the request carried, or undefined when it carried no body. */
function sentTopic(): string | undefined {
  const [, init] = apiRequestMock.mock.calls[0];
  return init?.body === undefined ? undefined : (JSON.parse(String(init.body)) as { focus_topic: string }).focus_topic;
}

describe('compactChat', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
    apiRequestMock.mockResolvedValue({ compacted: true, message_count: 4, tokens_saved: 900, reason: null });
  });

  it('sends a topic within the limit as it is', async () => {
    await compactChat('chat-1', 'billing decisions');

    expect(apiRequestMock).toHaveBeenCalledWith('/chats/chat-1/compact', {
      method: 'POST',
      body: JSON.stringify({ focus_topic: 'billing decisions' }),
      headers: { 'Content-Type': 'application/json' },
    });
  });

  it.each([undefined, ''])('sends no body when the topic is %j', async (topic) => {
    await compactChat('chat-1', topic);

    expect(apiRequestMock).toHaveBeenCalledWith('/chats/chat-1/compact', { method: 'POST' });
  });

  it('cuts a longer topic to the limit the server accepts, so the request is not refused', async () => {
    await compactChat('chat-1', 'x'.repeat(COMPACT_FOCUS_TOPIC_MAX_LENGTH + 60));

    expect(sentTopic()).toBe('x'.repeat(COMPACT_FOCUS_TOPIC_MAX_LENGTH));
  });

  it('cuts by character, so a rare han character on the limit is not split in half', async () => {
    await compactChat('chat-1', `a${RARE_HAN.repeat(COMPACT_FOCUS_TOPIC_MAX_LENGTH + 10)}`);

    expect(sentTopic()).toBe(`a${RARE_HAN.repeat(COMPACT_FOCUS_TOPIC_MAX_LENGTH - 1)}`);
  });
});

describe('runManualCompaction', () => {
  const compacted = { compacted: true, message_count: 4, tokens_saved: 900, reason: null, backup_path: '/tmp/b.json' };

  beforeEach(() => {
    apiRequestMock.mockReset();
    apiRequestMock.mockResolvedValue(compacted);
    refreshCompactionState.mockReset();
    refreshCompactionState.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('hands a compaction that freed tokens to the store, so every view of the chat catches up', async () => {
    await expect(runManualCompaction('chat-1', 'billing')).resolves.toEqual(compacted);

    expect(sentTopic()).toBe('billing');
    expect(refreshCompactionState).toHaveBeenCalledWith('chat-1', { tokensSaved: 900, snapshotPath: '/tmp/b.json' });
  });

  it('records no snapshot path when the server kept no backup', async () => {
    apiRequestMock.mockResolvedValue({ ...compacted, backup_path: null });

    await runManualCompaction('chat-1');

    expect(refreshCompactionState).toHaveBeenCalledWith('chat-1', { tokensSaved: 900, snapshotPath: undefined });
  });

  it('leaves the store alone when nothing was compacted', async () => {
    const skipped = { ...compacted, compacted: false, tokens_saved: 0, reason: 'no_compactable_messages' };
    apiRequestMock.mockResolvedValue(skipped);

    await expect(runManualCompaction('chat-1')).resolves.toEqual(skipped);

    expect(refreshCompactionState).not.toHaveBeenCalled();
  });

  it('passes a failed request on and leaves the store alone', async () => {
    apiRequestMock.mockRejectedValue(new Error('offline'));

    await expect(runManualCompaction('chat-1')).rejects.toThrow('offline');

    expect(refreshCompactionState).not.toHaveBeenCalled();
  });

  it('still reports a compaction that happened when the store could not take it', async () => {
    const logged = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    refreshCompactionState.mockRejectedValue(new Error('sync failed'));

    await expect(runManualCompaction('chat-1')).resolves.toEqual(compacted);

    expect(logged).toHaveBeenCalledOnce();
  });

  it.each([
    { reason: 'timeout: summarizer exceeded 60s', logged: true },
    { reason: 'persist_failed: database is locked', logged: true },
    { reason: 'no_compactable_messages', logged: false },
    { reason: 'concurrent_compaction_in_progress', logged: false },
  ])('keeps the raw reason of a failure for the console only ($reason)', async ({ reason, logged }) => {
    const errorLog = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    apiRequestMock.mockResolvedValue({ ...compacted, compacted: false, tokens_saved: 0, reason });

    await runManualCompaction('chat-1');

    expect(errorLog.mock.calls).toEqual(logged ? [['[Compaction] failed:', reason]] : []);
  });
});

/** Every reason the compaction service reports for a request it did not run. */
const SKIP_CASES = [
  { reason: 'no_compactable_messages', messageKey: 'chat.compact.skip.nothing', severity: 'info' },
  { reason: 'too_few_messages (2 < 4)', messageKey: 'chat.compact.skip.nothing', severity: 'info' },
  { reason: 'concurrent_compaction_in_progress', messageKey: 'chat.compact.skip.busy', severity: 'info' },
  { reason: 'summarize_circuit_open', messageKey: 'chat.compact.skip.paused', severity: 'warning' },
  { reason: 'compression_anti_thrash_active', messageKey: 'chat.compact.skip.ineffective', severity: 'warning' },
  { reason: 'chat_not_found', messageKey: 'chat.compact.failed', severity: 'error' },
  { reason: 'timeout: summarizer exceeded 60s', messageKey: 'chat.compact.failed', severity: 'error' },
  { reason: 'persist_failed: database is locked', messageKey: 'chat.compact.failed', severity: 'error' },
  { reason: 'a_reason_added_later', messageKey: 'chat.compact.failed', severity: 'error' },
  { reason: 'constructor', messageKey: 'chat.compact.failed', severity: 'error' },
  { reason: '__proto__', messageKey: 'chat.compact.failed', severity: 'error' },
  { reason: '', messageKey: 'chat.compact.failed', severity: 'error' },
  { reason: null, messageKey: 'chat.compact.failed', severity: 'error' },
] as const;

/** The text a dotted key resolves to in a locale bundle, or undefined when the bundle has none. */
function copyOf(bundle: unknown, key: string): unknown {
  return key
    .split('.')
    .reduce<unknown>(
      (node, part) => (typeof node === 'object' && node !== null ? (node as Record<string, unknown>)[part] : undefined),
      bundle,
    );
}

describe('describeCompactSkip', () => {
  it.each(SKIP_CASES)('words $reason as $messageKey ($severity)', ({ reason, messageKey, severity }) => {
    expect(describeCompactSkip(reason)).toEqual({ messageKey, severity });
  });

  it.each([
    { locale: 'English', bundle: en },
    { locale: 'Chinese', bundle: zh },
  ])('has $locale copy for every notice', ({ bundle }) => {
    const keys = new Set(SKIP_CASES.map(({ reason }) => describeCompactSkip(reason).messageKey));

    expect([...keys].filter((key) => typeof copyOf(bundle, key) !== 'string')).toEqual([]);
  });
});
