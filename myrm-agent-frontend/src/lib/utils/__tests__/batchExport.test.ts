/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { batchExportAsZip, downloadBlob, type BatchExportProgress } from '../batchExport';
import { downloadBlob as chatExportDownloadBlob, type ExportData } from '../chatExport';

vi.mock('@/services/chat', () => ({
  exportChat: vi.fn(),
}));

vi.mock('../chatExport', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../chatExport')>();
  return {
    ...actual,
    formatChatAsMarkdown: vi.fn((data: ExportData) => `# ${data.chat.title}\n\ncontent`),
  };
});

function mockExportData(chatId: string, title: string, date: string, msgCount = 1): ExportData {
  return {
    chat: { id: chatId, title, source: 'myrm', createdAt: date },
    messages: Array.from({ length: msgCount }, (_, i) => ({
      role: i % 2 === 0 ? 'user' : 'assistant',
      content: `msg-${i}`,
      createdAt: date,
      metadata: {},
    })),
  };
}

const { exportChat } = await import('@/services/chat');
const mockExportChat = exportChat as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
});

const defaultOpts = { theme: 'light' as const, lang: 'en' as const };

describe('batchExportAsZip', () => {
  it('exports multiple chats into a ZIP', async () => {
    mockExportChat
      .mockResolvedValueOnce(mockExportData('c1', 'Chat A', '2026-07-10T00:00:00Z'))
      .mockResolvedValueOnce(mockExportData('c2', 'Chat B', '2026-07-11T00:00:00Z'));

    const { result } = await batchExportAsZip(['c1', 'c2'], 'markdown', defaultOpts);

    expect(result.exported).toBe(2);
    expect(result.skipped).toBe(0);
    expect(result.failed).toBe(0);
    expect(mockExportChat).toHaveBeenCalledTimes(2);
  });

  it('returns empty result for empty chatIds', async () => {
    const { result } = await batchExportAsZip([], 'markdown', defaultOpts);

    expect(result.exported).toBe(0);
    expect(result.skipped).toBe(0);
    expect(result.failed).toBe(0);
    expect(mockExportChat).not.toHaveBeenCalled();
  });

  it('skips chats with no messages', async () => {
    mockExportChat.mockResolvedValueOnce(
      mockExportData('c1', 'Empty', '2026-07-10T00:00:00Z', 0),
    );

    const { result } = await batchExportAsZip(['c1'], 'markdown', defaultOpts);

    expect(result.exported).toBe(0);
    expect(result.skipped).toBe(1);
    expect(result.failed).toBe(0);
  });

  it('retries once on transient failure', async () => {
    mockExportChat
      .mockRejectedValueOnce(new Error('Network timeout'))
      .mockResolvedValueOnce(mockExportData('c1', 'Retry OK', '2026-07-10T00:00:00Z'));

    const { result } = await batchExportAsZip(['c1'], 'markdown', defaultOpts);

    expect(result.exported).toBe(1);
    expect(result.failed).toBe(0);
    expect(mockExportChat).toHaveBeenCalledTimes(2);
  });

  it('marks as failed after retry also fails', async () => {
    mockExportChat
      .mockRejectedValueOnce(new Error('Fail 1'))
      .mockRejectedValueOnce(new Error('Fail 2'));

    const { result } = await batchExportAsZip(['c1'], 'markdown', defaultOpts);

    expect(result.exported).toBe(0);
    expect(result.failed).toBe(1);
    expect(mockExportChat).toHaveBeenCalledTimes(2);
  });

  it('does not retry on AbortError', async () => {
    mockExportChat.mockRejectedValueOnce(new DOMException('Aborted', 'AbortError'));

    const err = await batchExportAsZip(['c1'], 'markdown', defaultOpts).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(DOMException);
    expect((err as DOMException).name).toBe('AbortError');
    expect(mockExportChat).toHaveBeenCalledTimes(1);
  });

  it('stops on abort signal', async () => {
    const controller = new AbortController();
    controller.abort();

    const err = await batchExportAsZip(['c1'], 'markdown', {
      ...defaultOpts,
      signal: controller.signal,
    }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(DOMException);
    expect((err as DOMException).name).toBe('AbortError');
    expect(mockExportChat).not.toHaveBeenCalled();
  });

  it('reports progress via onProgress', async () => {
    mockExportChat.mockResolvedValue(mockExportData('c1', 'Chat A', '2026-07-10T00:00:00Z'));

    const progress: BatchExportProgress[] = [];
    await batchExportAsZip(['c1'], 'markdown', {
      ...defaultOpts,
      onProgress: (p) => progress.push({ ...p }),
    });

    expect(progress.length).toBeGreaterThanOrEqual(1);
    expect(progress[0].total).toBe(1);
    expect(progress.at(-1)?.current).toBe(1);
  });

  it('deduplicates file paths with same title and date', async () => {
    const data = mockExportData('c1', 'Same Title', '2026-07-10T00:00:00Z');
    mockExportChat
      .mockResolvedValueOnce(data)
      .mockResolvedValueOnce(mockExportData('c2', 'Same Title', '2026-07-10T00:00:00Z'));

    const { result } = await batchExportAsZip(['c1', 'c2'], 'markdown', defaultOpts);

    expect(result.exported).toBe(2);
  });

  it('processes chats concurrently (CONCURRENCY=3)', async () => {
    let maxConcurrent = 0;
    let activeCalls = 0;

    mockExportChat.mockImplementation(async (chatId: string) => {
      activeCalls++;
      maxConcurrent = Math.max(maxConcurrent, activeCalls);
      await new Promise((r) => setTimeout(r, 10));
      activeCalls--;
      return mockExportData(chatId, `Chat-${chatId}`, '2026-07-10T00:00:00Z');
    });

    const ids = ['a', 'b', 'c', 'd', 'e', 'f'];
    const { result } = await batchExportAsZip(ids, 'markdown', defaultOpts);

    expect(result.exported).toBe(6);
    expect(maxConcurrent).toBeLessThanOrEqual(3);
    expect(maxConcurrent).toBeGreaterThanOrEqual(2);
  });

  it('groups files into date-based folders', async () => {
    mockExportChat.mockResolvedValueOnce(
      mockExportData('c1', 'Day Chat', '2026-07-15T08:00:00Z'),
    );

    const { blob, result } = await batchExportAsZip(['c1'], 'markdown', defaultOpts);

    expect(result.exported).toBe(1);
    expect(blob.size).toBeGreaterThan(0);
  });

  it('handles invalid createdAt date gracefully (unknown-date folder)', async () => {
    const data: ExportData = {
      chat: { id: 'c-bad', title: 'Bad Date', source: 'myrm', createdAt: 'not-a-date' },
      messages: [{ role: 'user', content: 'hi', createdAt: 'not-a-date', metadata: {} }],
    };
    mockExportChat.mockResolvedValueOnce(data);

    const { result } = await batchExportAsZip(['c-bad'], 'markdown', defaultOpts);

    expect(result.exported).toBe(1);
    expect(result.failed).toBe(0);
  });
});

describe('downloadBlob re-export', () => {
  it('should be the same function as chatExport.downloadBlob', () => {
    expect(downloadBlob).toBe(chatExportDownloadBlob);
  });
});
