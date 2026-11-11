/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { downloadMessageAsMarkdown, type ExportData } from '../chatExport';
import type { MessageLabels } from '../chatExportMessageText';
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

const LABELS: MessageLabels = { reasoning: '思考过程', sources: '来源', untitledSource: '未命名' };

describe('single-message export', () => {
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
      downloadMessageAsMarkdown(message, false, LABELS);
      expect(linkMock.click).toHaveBeenCalled();
      expect(linkMock.download).toContain('.md');
    });

    it('should include reasoning when requested', () => {
      const message = createMockMessage({ reasoning: 'Deep thought process' });
      const blobSpy = vi.spyOn(globalThis, 'Blob').mockImplementation(function (this: Blob, parts?: BlobPart[]) {
        (this as unknown as { _content: string })._content = parts?.[0]?.toString() ?? '';
        return this;
      } as unknown as typeof Blob);

      downloadMessageAsMarkdown(message, true, LABELS);

      const blobContent = (blobSpy.mock.instances[0] as unknown as { _content: string })._content;
      expect(blobContent).toContain('<summary>思考过程</summary>');
      expect(blobContent).toContain('Deep thought process');

      blobSpy.mockRestore();
    });

    it('should not include reasoning when not requested', () => {
      const message = createMockMessage({ reasoning: 'Secret thoughts' });
      const blobSpy = vi.spyOn(globalThis, 'Blob').mockImplementation(function (this: Blob, parts?: BlobPart[]) {
        (this as unknown as { _content: string })._content = parts?.[0]?.toString() ?? '';
        return this;
      } as unknown as typeof Blob);

      downloadMessageAsMarkdown(message, false, LABELS);

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

      downloadMessageAsMarkdown(message, false, LABELS);

      const blobContent = (blobSpy.mock.instances[0] as unknown as { _content: string })._content;
      expect(blobContent).toContain('来源:');
      // A hard break after every line (two spaces) keeps each source on its own line when the Markdown is rendered.
      expect(blobContent).toContain('来源:  \n[1] https://example.com  \n[2] https://test.com');

      blobSpy.mockRestore();
    });

    it('should handle message with no sources', () => {
      const message = createMockMessage({ sources: undefined });
      downloadMessageAsMarkdown(message, false, LABELS);
      expect(linkMock.click).toHaveBeenCalled();
    });

    it('should automatically redact sensitive tokens in message content and reasoning by default', () => {
      const message = createMockMessage({
        content: 'Use this secret token: sk-live1234567890abcdef1234567890 for auth',
        reasoning: 'Calling API with Bearer token: ghp_1234567890abcdefghijklmnopqrstuvwxyzAB',
      });
      const blobSpy = vi.spyOn(globalThis, 'Blob').mockImplementation(function (this: Blob, parts?: BlobPart[]) {
        (this as unknown as { _content: string })._content = parts?.[0]?.toString() ?? '';
        return this;
      } as unknown as typeof Blob);

      downloadMessageAsMarkdown(message, true, LABELS);

      const blobContent = (blobSpy.mock.instances[0] as unknown as { _content: string })._content;
      expect(blobContent).not.toContain('sk-live1234567890abcdef1234567890');
      expect(blobContent).toContain('[REDACTED_API_KEY]');
      expect(blobContent).not.toContain('ghp_1234567890abcdefghijklmnopqrstuvwxyzAB');
      expect(blobContent).toContain('[REDACTED_GH_TOKEN]');

      blobSpy.mockRestore();
    });

    it('should sanitize filename from first line', () => {
      const message = createMockMessage({ content: 'Title with <special> chars\nBody content' });
      downloadMessageAsMarkdown(message, false, LABELS);
      const filename = linkMock.download as string;
      expect(filename).not.toContain('<');
      expect(filename).not.toContain('>');
      expect(filename).toContain('.md');
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
      await downloadHtml(message, false, LABELS, 'light');
    });

    it('should hand the page builder a labelled quote for the reasoning, with the theme and language it is given', async () => {
      const mockBuildHtmlDocument = vi.fn().mockResolvedValue('<html><body>Test</body></html>');
      vi.doMock('../chatExportHtml', () => ({ buildHtmlDocument: mockBuildHtmlDocument }));

      const { downloadMessageAsHtml: downloadHtml } = await import('../chatExport');
      const message = createMockMessage({ reasoning: 'Deep thought process' });
      await downloadHtml(message, true, LABELS, 'dark', 'zh');

      const [data, theme, lang] = mockBuildHtmlDocument.mock.calls[0] as [ExportData, string, string];
      expect(data.messages[0].content).toContain('> **思考过程**\n>\n> Deep thought process');
      expect(data.messages[0].content).not.toContain('<details>');
      expect([theme, lang]).toEqual(['dark', 'zh']);
    });
  });

  describe('downloadMessageAsDocx', () => {
    afterEach(() => {
      vi.restoreAllMocks();
    });

    it('should build a Word file and download it through the page', async () => {
      const linkMock = { href: '', download: '', click: vi.fn(), style: {} };
      vi.spyOn(document, 'createElement').mockReturnValue(linkMock as unknown as HTMLAnchorElement);
      vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
      vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});

      const { downloadMessageAsDocx: downloadDocx } = await import('../chatExport');
      const message = createMockMessage();
      await downloadDocx(message, false, LABELS);

      expect(linkMock.click).toHaveBeenCalled();
      expect(linkMock.download).toContain('.docx');
      const blob = vi.mocked(URL.createObjectURL).mock.calls[0][0] as Blob;
      expect(new Uint8Array(await blob.arrayBuffer()).slice(0, 2)).toEqual(new Uint8Array([0x50, 0x4b]));
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

      const origCreateElement = document.createElement.bind(document);
      const linkMock = { href: '', download: '', click: vi.fn(), style: {} };
      vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
        if (tag === 'a') {
          return linkMock as unknown as HTMLAnchorElement;
        }
        return origCreateElement(tag);
      });
      vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
      vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});

      const { downloadMessageAsImage: downloadImage } = await import('../chatExport');
      const element = origCreateElement('div');
      const message = createMockMessage();
      await downloadImage(element, message, false);

      expect(mockHtml2canvas).toHaveBeenCalledWith(element, expect.objectContaining({ scale: 2 }));
      expect(linkMock.click).toHaveBeenCalled();
      expect(linkMock.download).toContain('.png');
    });

    it('should redact sensitive text in onclone sandbox without mutating original DOM', async () => {
      const mockBlob = new Blob(['test'], { type: 'image/png' });
      let clonedTargetCaptured: HTMLElement | null = null;
      const mockCanvas = {
        toBlob: vi.fn((cb: (blob: Blob | null) => void) => cb(mockBlob)),
      };
      const mockHtml2canvas = vi
        .fn()
        .mockImplementation((target: HTMLElement, options?: { onclone?: (doc: Document, el: HTMLElement) => void }) => {
          if (options?.onclone) {
            const cloned = target.cloneNode(true) as HTMLElement;
            options.onclone(document, cloned);
            clonedTargetCaptured = cloned;
          }
          return Promise.resolve(mockCanvas);
        });
      vi.doMock('html2canvas', () => ({ default: mockHtml2canvas }));

      const origCreateElement = document.createElement.bind(document);
      const linkMock = { href: '', download: '', click: vi.fn(), style: {} };
      vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
        if (tag === 'a') {
          return linkMock as unknown as HTMLAnchorElement;
        }
        return origCreateElement(tag);
      });
      vi.spyOn(document.body, 'appendChild').mockImplementation((node) => node);
      vi.spyOn(document.body, 'removeChild').mockImplementation((node) => node);
      vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:test');
      vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});

      const { downloadMessageAsImage: downloadImage } = await import('../chatExport');
      const element = origCreateElement('div');
      element.textContent = 'API key is sk-proj-123456789012345678901234567890';
      const message = createMockMessage();
      await downloadImage(element, message, true);

      expect(mockHtml2canvas).toHaveBeenCalledWith(element, expect.objectContaining({ scale: 2 }));
      expect(clonedTargetCaptured).not.toBe(element);
      expect((clonedTargetCaptured as HTMLElement | null)?.textContent).toContain('[REDACTED_API_KEY]');
      expect(element.textContent).toContain('sk-proj-');
      expect(linkMock.click).toHaveBeenCalled();
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

      await expect(downloadImage(element, message, false)).rejects.toThrow('Failed to create image blob');
    });
  });
});
