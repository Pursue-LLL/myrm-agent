/** @vitest-environment jsdom */
import { afterEach, describe, expect, it, vi } from 'vitest';

import type { SessionAnalytics } from '@/services/statistics';

import { buildAuditCsv, buildAuditMarkdown, copyTextToClipboard, downloadCsvFile } from '../sessionAuditExport';

const ANALYTICS: SessionAnalytics = {
  session_id: 's-1',
  title: 'He said "hi"',
  action_mode: 'agent',
  created_at: null,
  duration_ms: 125_000,
  message_count: 4,
  user_messages: 2,
  assistant_messages: 2,
  calls: 3,
  inputTokens: 1000,
  outputTokens: 500,
  cachedTokens: 250,
  reasoningTokens: 0,
  citationTokens: 0,
  totalTokens: 1500,
  costUsd: 0.0123,
  cacheHitRate: 0.25,
  modelBreakdown: {},
  tool_breakdown: [],
  llm_breakdown: [{ model_name: 'gpt "x"', call_count: 2, total_duration_ms: 3000 }],
  events_timeline: [],
  task_metrics: {},
  context_health: {} as SessionAnalytics['context_health'],
};

function stubClipboard(writeText: ((text: string) => Promise<void>) | undefined): void {
  Object.defineProperty(navigator, 'clipboard', {
    value: writeText ? { writeText } : undefined,
    configurable: true,
  });
}

function stubExecCommand(impl: () => boolean): ReturnType<typeof vi.fn> {
  const spy = vi.fn(impl);
  Object.defineProperty(document, 'execCommand', { value: spy, configurable: true });
  return spy;
}

afterEach(() => {
  stubClipboard(undefined);
  Reflect.deleteProperty(document, 'execCommand');
  vi.restoreAllMocks();
});

describe('buildAuditCsv', () => {
  it('starts with a BOM header and escapes quotes in text fields', () => {
    const lines = buildAuditCsv(ANALYTICS).split('\n');

    expect(lines[0]).toBe('\uFEFFSection,Metric,Value');
    expect(lines).toContain('Session,Title,"He said ""hi"""');
    expect(lines).toContain('Session,DurationSeconds,125');
    expect(lines).toContain('Economics,CacheHitRatio,25.00%');
    expect(lines).toContain('Economics,CostUSD,0.0123');
    expect(lines).toContain('LLM,"gpt ""x""",2,3000');
  });
});

describe('buildAuditMarkdown', () => {
  it('keeps list and table lines flush left so Markdown renders them as written', () => {
    const lines = buildAuditMarkdown(ANALYTICS).split('\n');

    expect(lines[0]).toContain('Audit Ledger');
    expect(lines).toContain('- **Total Duration**: 2m 5s');
    expect(lines).toContain('| gpt "x" | 2 | 3000 ms | 1500 ms |');
    expect(lines.filter((line) => /^\s/.test(line))).toEqual([]);
  });

  it('writes a placeholder row for empty breakdowns', () => {
    const lines = buildAuditMarkdown({ ...ANALYTICS, llm_breakdown: undefined }).split('\n');

    expect(lines.filter((line) => line === '| N/A | 0 | 0 ms | 0 ms |')).toHaveLength(2);
  });
});

describe('copyTextToClipboard', () => {
  it('uses the async clipboard API when it is available', async () => {
    const writeText = vi.fn(() => Promise.resolve());
    stubClipboard(writeText);
    const execCommand = stubExecCommand(() => true);

    await expect(copyTextToClipboard('hello')).resolves.toBe(true);

    expect(writeText).toHaveBeenCalledWith('hello');
    expect(execCommand).not.toHaveBeenCalled();
  });

  it('falls back to execCommand when the async API rejects', async () => {
    stubClipboard(() => Promise.reject(new Error('denied')));
    const execCommand = stubExecCommand(() => true);

    await expect(copyTextToClipboard('hello')).resolves.toBe(true);

    expect(execCommand).toHaveBeenCalledWith('copy');
    expect(document.querySelector('textarea')).toBeNull();
  });

  it('falls back to execCommand when the async API is missing', async () => {
    stubClipboard(undefined);
    const execCommand = stubExecCommand(() => true);

    await expect(copyTextToClipboard('hello')).resolves.toBe(true);

    expect(execCommand).toHaveBeenCalledOnce();
  });

  it('reports failure when the fallback is refused or throws', async () => {
    stubClipboard(undefined);
    stubExecCommand(() => false);
    await expect(copyTextToClipboard('hello')).resolves.toBe(false);

    stubExecCommand(() => {
      throw new Error('blocked');
    });
    await expect(copyTextToClipboard('hello')).resolves.toBe(false);
  });
});

describe('downloadCsvFile', () => {
  it('triggers a named download from a CSV blob and releases the object URL', () => {
    const createObjectURL = vi.fn((blob: Blob) => `blob:${blob.type}`);
    const revokeObjectURL = vi.fn();
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    const append = vi.spyOn(document.body, 'appendChild');

    downloadCsvFile('audit-ledger-s-1.csv', 'a,b');

    const link = append.mock.calls[0][0] as HTMLAnchorElement;
    expect(link.getAttribute('download')).toBe('audit-ledger-s-1.csv');
    expect(link.href).toBe('blob:text/csv;charset=utf-8;');
    expect(click).toHaveBeenCalledOnce();
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:text/csv;charset=utf-8;');
    expect(document.body.contains(link)).toBe(false);
  });
});
