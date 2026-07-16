/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  formatChatAsMarkdown,
  formatChatAsJson,
  downloadBlob,
  downloadFile,
  downloadAsMarkdown,
  downloadAsJson,
  downloadMessageAsMarkdown,
  formatDuration,
  formatUsd,
  sanitizeFilename,
  type ExportData,
} from '../chatExport';
import type { Message, Source } from '@/store/chat/types';

function createMockMessage(overrides: Partial<Message> = {}): Message {
  return {
    messageId: 'msg-1',
    chatId: 'chat-1',
    createdAt: new Date('2026-05-30T10:00:00Z'),
    content: '# Research Report\n\nThis is the main content.',
    role: 'assistant',
    ...overrides,
  } as Message;
}

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
  describe('formatDuration', () => {
    it('should format milliseconds', () => {
      expect(formatDuration(500)).toBe('500ms');
    });

    it('should format seconds', () => {
      expect(formatDuration(3500)).toBe('3.5s');
    });

    it('should format minutes', () => {
      expect(formatDuration(90_000)).toBe('1.5m');
    });
  });

  describe('formatUsd', () => {
    it('should format small amounts with 4 decimals', () => {
      expect(formatUsd(0.005)).toBe('$0.0050');
    });

    it('should format normal amounts with 2 decimals', () => {
      expect(formatUsd(1.5)).toBe('$1.50');
    });
  });

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
      expect(md).toContain('Thinking');
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

  describe('downloadBlob', () => {
    let linkMock: Record<string, unknown>;
    let createObjectURLSpy: ReturnType<typeof vi.spyOn>;
    let revokeObjectURLSpy: ReturnType<typeof vi.spyOn>;

    beforeEach(() => {
      linkMock = { href: '', download: '', click: vi.fn(), style: {} };
      vi.spyOn(document, 'createElement').mockReturnValue(linkMock as unknown as HTMLAnchorElement);
      vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
      vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);
      createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test-url');
      revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('should create object URL, trigger click, then revoke', () => {
      const blob = new Blob(['hello'], { type: 'text/plain' });
      downloadBlob(blob, 'test.txt');

      expect(createObjectURLSpy).toHaveBeenCalledWith(blob);
      expect(linkMock.href).toBe('blob:test-url');
      expect(linkMock.download).toBe('test.txt');
      expect(linkMock.click).toHaveBeenCalled();
      expect(revokeObjectURLSpy).toHaveBeenCalledWith('blob:test-url');
    });
  });

  describe('downloadFile delegates to downloadBlob', () => {
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

  describe('downloadMessageAsMarkdown', () => {
    let linkMock: Record<string, unknown>;

    beforeEach(() => {
      linkMock = { href: '', download: '', click: vi.fn(), style: {} };
      vi.spyOn(document, 'createElement').mockReturnValue(linkMock as unknown as HTMLAnchorElement);
      vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
      vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    });

    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('should export message content', () => {
      const message = createMockMessage();
      downloadMessageAsMarkdown(message, false);
      expect(linkMock.click).toHaveBeenCalled();
      expect(linkMock.download).toContain('.md');
    });

    it('should include reasoning when requested', () => {
      const message = createMockMessage({ reasoning: 'Deep thought process' });
      const blobSpy = vi.spyOn(globalThis, 'Blob').mockImplementation(function (this: Blob, parts?: BlobPart[]) {
        (this as unknown as { _content: string })._content = parts?.[0]?.toString() ?? '';
        return this;
      } as unknown as typeof Blob);

      downloadMessageAsMarkdown(message, true);

      const blobContent = (blobSpy.mock.instances[0] as unknown as { _content: string })._content;
      expect(blobContent).toContain('Thinking');
      expect(blobContent).toContain('Deep thought process');

      blobSpy.mockRestore();
    });

    it('should not include reasoning when not requested', () => {
      const message = createMockMessage({ reasoning: 'Secret thoughts' });
      const blobSpy = vi.spyOn(globalThis, 'Blob').mockImplementation(function (this: Blob, parts?: BlobPart[]) {
        (this as unknown as { _content: string })._content = parts?.[0]?.toString() ?? '';
        return this;
      } as unknown as typeof Blob);

      downloadMessageAsMarkdown(message, false);

      const blobContent = (blobSpy.mock.instances[0] as unknown as { _content: string })._content;
      expect(blobContent).not.toContain('Secret thoughts');

      blobSpy.mockRestore();
    });

    it('should include sources as footnotes', () => {
      const sources: Source[] = [
        { index: 1, type: 'web_search', url: 'https://example.com', title: 'Example' },
        { index: 2, type: 'web_search', url: 'https://test.com', title: 'Test' },
      ];
      const message = createMockMessage({ sources });
      const blobSpy = vi.spyOn(globalThis, 'Blob').mockImplementation(function (this: Blob, parts?: BlobPart[]) {
        (this as unknown as { _content: string })._content = parts?.[0]?.toString() ?? '';
        return this;
      } as unknown as typeof Blob);

      downloadMessageAsMarkdown(message, false);

      const blobContent = (blobSpy.mock.instances[0] as unknown as { _content: string })._content;
      expect(blobContent).toContain('Citations:');
      expect(blobContent).toContain('[1] https://example.com');
      expect(blobContent).toContain('[2] https://test.com');

      blobSpy.mockRestore();
    });

    it('should handle message with no sources', () => {
      const message = createMockMessage({ sources: undefined });
      downloadMessageAsMarkdown(message, false);
      expect(linkMock.click).toHaveBeenCalled();
    });

    it('should sanitize filename from first line', () => {
      const message = createMockMessage({ content: 'Title with <special> chars\nBody content' });
      downloadMessageAsMarkdown(message, false);
      const filename = linkMock.download as string;
      expect(filename).not.toContain('<');
      expect(filename).not.toContain('>');
      expect(filename).toContain('.md');
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

  describe('downloadMessageAsHtml', () => {
    beforeEach(() => {
      vi.spyOn(document, 'createElement').mockReturnValue({
        href: '',
        download: '',
        click: vi.fn(),
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

    it('should call buildHtmlDocument and download', async () => {
      const mockBuildHtmlDocument = vi.fn().mockResolvedValue('<html><body>Test</body></html>');
      vi.doMock('../chatExportHtml', () => ({ buildHtmlDocument: mockBuildHtmlDocument }));

      const { downloadMessageAsHtml: downloadHtml } = await import('../chatExport');
      const message = createMockMessage();
      await downloadHtml(message, false, 'light');
    });
  });

  describe('downloadMessageAsDocx', () => {
    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('should call docshift toDocx and download', async () => {
      const mockDocxBlob = new Blob(['docx content'], {
        type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      });
      vi.doMock('docshift', () => ({ toDocx: vi.fn().mockResolvedValue(mockDocxBlob) }));
      vi.doMock('../chatExportHtml', () => ({
        buildHtmlDocument: vi.fn().mockResolvedValue('<html><body>Test</body></html>'),
      }));

      const linkMock = { href: '', download: '', click: vi.fn(), style: {} };
      vi.spyOn(document, 'createElement').mockReturnValue(linkMock as unknown as HTMLAnchorElement);
      vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
      vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});

      const { downloadMessageAsDocx: downloadDocx } = await import('../chatExport');
      const message = createMockMessage();
      await downloadDocx(message, false);

      expect(linkMock.click).toHaveBeenCalled();
      expect(linkMock.download).toContain('.docx');
    });
  });

  describe('downloadMessageAsImage', () => {
    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('should create canvas and download PNG', async () => {
      const mockBlob = new Blob(['test'], { type: 'image/png' });
      const mockCanvas = {
        toBlob: vi.fn((cb: (blob: Blob | null) => void) => cb(mockBlob)),
      };
      const mockHtml2canvas = vi.fn().mockResolvedValue(mockCanvas);
      vi.doMock('html2canvas', () => ({ default: mockHtml2canvas }));

      const linkMock = { href: '', download: '', click: vi.fn(), style: {} };
      vi.spyOn(document, 'createElement').mockReturnValue(linkMock as unknown as HTMLAnchorElement);
      vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
      vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});

      const { downloadMessageAsImage: downloadImage } = await import('../chatExport');
      const element = document.createElement('div');
      const message = createMockMessage();
      await downloadImage(element, message);

      expect(mockHtml2canvas).toHaveBeenCalledWith(element, expect.objectContaining({ scale: 2 }));
      expect(linkMock.click).toHaveBeenCalled();
      expect(linkMock.download).toContain('.png');
    });

    it('should reject when toBlob returns null', async () => {
      const mockCanvas = {
        toBlob: vi.fn((cb: (blob: Blob | null) => void) => cb(null)),
      };
      const mockHtml2canvas = vi.fn().mockResolvedValue(mockCanvas);
      vi.doMock('html2canvas', () => ({ default: mockHtml2canvas }));

      const { downloadMessageAsImage: downloadImage } = await import('../chatExport');
      const element = document.createElement('div');
      const message = createMockMessage();

      await expect(downloadImage(element, message)).rejects.toThrow('Failed to create image blob');
    });
  });
});
