/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  formatChatAsMarkdown,
  formatChatAsJson,
  downloadFile,
  downloadAsMarkdown,
  downloadAsJson,
  getExportLang,
  type ExportData,
} from '../chatExport';
import { sanitizeFilename } from '../../fileUtils';

function createMockExportData(overrides: Partial<ExportData> = {}): ExportData {
  return {
    chat: { id: 'chat-1', title: 'Test Chat', source: 'myrm', createdAt: '2026-05-30T10:00:00Z' },
    messages: [
      { role: 'user', content: 'Hello', createdAt: '2026-05-30T09:59:00Z', metadata: {} },
      { role: 'assistant', content: 'Hi there!', createdAt: '2026-05-30T10:00:00Z', metadata: {} },
    ],
    ...overrides,
  };
}

describe('chatExport', () => {
  describe('formatChatAsMarkdown', () => {
    it('should include title and messages', () => {
      const data = createMockExportData();
      const md = formatChatAsMarkdown(data);
      expect(md).toContain('# Test Chat');
      expect(md).toContain('**User**');
      expect(md).toContain('Hello');
      expect(md).toContain('**Assistant**');
      expect(md).toContain('Hi there!');
    });

    it('should include redacted notice when redacted is true', () => {
      const data = createMockExportData({ redacted: true });
      const md = formatChatAsMarkdown(data);
      expect(md).toContain('[Security] Sensitive secrets and credentials have been automatically redacted');
      expect(md).not.toContain('\u{1F512}');
    });

    it('should filter non-visible roles', () => {
      const data = createMockExportData({
        messages: [
          { role: 'system', content: 'System prompt', createdAt: '2026-05-30T09:58:00Z', metadata: {} },
          { role: 'assistant', content: 'Response', createdAt: '2026-05-30T10:00:00Z', metadata: {} },
        ],
      });
      const md = formatChatAsMarkdown(data);
      expect(md).not.toContain('System prompt');
      expect(md).toContain('Response');
    });

    it('should include reasoning from metadata', () => {
      const data = createMockExportData({
        messages: [
          {
            role: 'assistant',
            content: 'Answer',
            createdAt: '2026-05-30T10:00:00Z',
            metadata: { reasoning_content: 'Let me think step by step...' },
          },
        ],
      });
      const md = formatChatAsMarkdown(data);
      expect(md).toContain('<details>');
      expect(md).toContain('<summary>Reasoning</summary>');
      expect(md).toContain('Let me think step by step...');
    });

    it('should fall back to reasoning field', () => {
      const data = createMockExportData({
        messages: [
          {
            role: 'assistant',
            content: 'Answer',
            createdAt: '2026-05-30T10:00:00Z',
            metadata: { reasoning: 'Fallback reasoning' },
          },
        ],
      });
      const md = formatChatAsMarkdown(data);
      expect(md).toContain('Fallback reasoning');
    });

    it('should include usage summary when present', () => {
      const data = createMockExportData({
        usageSummary: { totalCalls: 3, totalTokens: 5000, totalUsd: 0.05 },
      });
      const md = formatChatAsMarkdown(data);
      expect(md).toContain('Session Summary');
      expect(md).toContain('API Calls');
      expect(md).toContain('5.0k');
      expect(md).toContain('$0.05');
    });

    it('should include tool summary when present', () => {
      const data = createMockExportData({
        toolSummary: {
          totalToolCalls: 2,
          totalDurationMs: 3000,
          toolsUsed: [{ name: 'web_search', count: 2, totalMs: 3000 }],
        },
      });
      const md = formatChatAsMarkdown(data);
      expect(md).toContain('Tool Activity');
      expect(md).toContain('web_search');
      expect(md).toContain('3.0s');
    });

    it('should handle null title', () => {
      const data = createMockExportData();
      data.chat.title = null;
      const md = formatChatAsMarkdown(data);
      expect(md).toContain('# Untitled');
    });
  });

  describe('formatChatAsJson', () => {
    it('should produce valid JSON', () => {
      const data = createMockExportData();
      const json = formatChatAsJson(data);
      const parsed = JSON.parse(json);
      expect(parsed.title).toBe('Test Chat');
      expect(parsed.messages).toHaveLength(2);
      expect(parsed.exportedAt).toBeDefined();
    });

    it('should include usage when present', () => {
      const data = createMockExportData({
        usageSummary: { totalCalls: 1, totalTokens: 100, totalUsd: 0.001 },
      });
      const json = formatChatAsJson(data);
      const parsed = JSON.parse(json);
      expect(parsed.usageSummary).toBeDefined();
      expect(parsed.usageSummary.totalCalls).toBe(1);
    });

    it('should omit usage when not present', () => {
      const data = createMockExportData();
      const json = formatChatAsJson(data);
      const parsed = JSON.parse(json);
      expect(parsed.usageSummary).toBeUndefined();
    });

    it('should respect includeReasoning: false and includeToolCalls: false in formatChatAsMarkdown', () => {
      const data = createMockExportData({
        messages: [
          {
            role: 'assistant',
            content: 'Hello with thinking',
            createdAt: '2026-05-30T10:00:00Z',
            metadata: { reasoning: 'Secret reasoning chain' },
          },
        ],
        toolSummary: { totalToolCalls: 1, totalDurationMs: 100, toolsUsed: [{ name: 'bash', count: 1, totalMs: 100 }] },
      });
      const mdWithout = formatChatAsMarkdown(data, { includeReasoning: false, includeToolCalls: false });
      expect(mdWithout).not.toContain('<summary>Reasoning</summary>');
      expect(mdWithout).not.toContain('## Tool Activity');

      const mdWith = formatChatAsMarkdown(data, { includeReasoning: true, includeToolCalls: true });
      expect(mdWith).toContain('<summary>Reasoning</summary>');
      expect(mdWith).toContain('## Tool Activity');
    });

    it('should respect includeReasoning: false and includeToolCalls: false in formatChatAsJson', () => {
      const data = createMockExportData({
        messages: [
          {
            role: 'assistant',
            content: 'Hello with thinking',
            createdAt: '2026-05-30T10:00:00Z',
            metadata: { reasoning: 'Secret reasoning chain' },
          },
        ],
        toolSummary: { totalToolCalls: 1, totalDurationMs: 100, toolsUsed: [{ name: 'bash', count: 1, totalMs: 100 }] },
      });
      const jsonWithout = formatChatAsJson(data, { includeReasoning: false, includeToolCalls: false });
      const parsed = JSON.parse(jsonWithout);
      expect(parsed.messages[0].metadata.reasoning).toBeUndefined();
      expect(parsed.toolSummary).toBeUndefined();
    });
  });

  describe('downloadFile', () => {
    let clickSpy: ReturnType<typeof vi.fn>;
    let createObjectURLSpy: ReturnType<typeof vi.spyOn>;
    let revokeObjectURLSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      clickSpy = vi.fn();
      vi.spyOn(document, 'createElement').mockReturnValue({
        href: '',
        download: '',
        click: clickSpy,
        style: {},
      } as unknown as HTMLAnchorElement);
      vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
      vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);
      createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
      revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('should create and trigger download link', () => {
      downloadFile('test content', 'test.md', 'text/markdown');
      expect(createObjectURLSpy).toHaveBeenCalled();
      expect(clickSpy).toHaveBeenCalled();
      expect(revokeObjectURLSpy).toHaveBeenCalled();
    });
  });

  describe('downloadFile delegates to triggerDownload', () => {
    let createObjectURLSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      vi.spyOn(document, 'createElement').mockReturnValue({
        href: '',
        download: '',
        click: vi.fn(),
        style: {},
      } as unknown as HTMLAnchorElement);
      vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
      vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);
      createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('should pass a Blob with correct type to the download pipeline', () => {
      downloadFile('content', 'file.md', 'text/markdown');
      const passedBlob = createObjectURLSpy.mock.calls[0][0] as Blob;
      expect(passedBlob).toBeInstanceOf(Blob);
      expect(passedBlob.type).toBe('text/markdown');
    });
  });

  describe('sanitizeFilename', () => {
    it('should replace special characters', () => {
      expect(sanitizeFilename('file<>:"/\\|?*name')).toBe('file_________name');
    });

    it('should return Untitled for empty string', () => {
      expect(sanitizeFilename('')).toBe('Untitled');
    });

    it('should trim whitespace', () => {
      expect(sanitizeFilename('  hello  ')).toBe('hello');
    });
  });

  describe('downloadAsMarkdown', () => {
    let clickSpy: ReturnType<typeof vi.fn>;

    beforeEach(() => {
      clickSpy = vi.fn();
      vi.spyOn(document, 'createElement').mockReturnValue({
        href: '',
        download: '',
        click: clickSpy,
        style: {},
      } as unknown as HTMLAnchorElement);
      vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
      vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('should trigger download with .md extension', () => {
      const data = createMockExportData();
      downloadAsMarkdown(data);
      expect(clickSpy).toHaveBeenCalled();
    });
  });

  describe('downloadAsJson', () => {
    let clickSpy: ReturnType<typeof vi.fn>;

    beforeEach(() => {
      clickSpy = vi.fn();
      vi.spyOn(document, 'createElement').mockReturnValue({
        href: '',
        download: '',
        click: clickSpy,
        style: {},
      } as unknown as HTMLAnchorElement);
      vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
      vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('should trigger download with .json extension', () => {
      const data = createMockExportData();
      downloadAsJson(data);
      expect(clickSpy).toHaveBeenCalled();
    });
  });

  describe('formatChatAsMarkdown edge cases', () => {
    it('should handle formatTokenCount boundary at 10k', () => {
      const data = createMockExportData({
        usageSummary: { totalCalls: 1, totalTokens: 15000, totalUsd: 0.1 },
      });
      const md = formatChatAsMarkdown(data);
      expect(md).toContain('15k');
    });

    it('should handle formatTokenCount under 1000', () => {
      const data = createMockExportData({
        usageSummary: { totalCalls: 1, totalTokens: 500, totalUsd: 0.001 },
      });
      const md = formatChatAsMarkdown(data);
      expect(md).toContain('500');
    });
  });

  describe('getExportLang', () => {
    const setLocaleCookie = (value: string) => {
      document.cookie = `NEXT_LOCALE=${value}; path=/`;
    };

    afterEach(() => {
      document.cookie = 'NEXT_LOCALE=; path=/; max-age=0';
      vi.restoreAllMocks();
    });

    it.each([
      ['zh', 'zh'],
      ['zh-TW', 'zh'],
      ['en', 'en'],
      ['ja', 'en'],
      ['ko', 'en'],
      ['de', 'en'],
    ] as const)('maps the app language %s to the %s page wording', (locale, expected) => {
      setLocaleCookie(locale);
      expect(getExportLang()).toBe(expected);
    });

    it('follows the app language, not the browser language', () => {
      vi.spyOn(navigator, 'language', 'get').mockReturnValue('zh-CN');
      setLocaleCookie('en');
      expect(getExportLang()).toBe('en');
    });

    it('falls back to the default language the interface falls back to when the cookie is absent or unsupported', () => {
      vi.spyOn(navigator, 'language', 'get').mockReturnValue('en-US');
      expect(getExportLang()).toBe('zh');

      setLocaleCookie('fr');
      expect(getExportLang()).toBe('zh');
    });
  });
});
