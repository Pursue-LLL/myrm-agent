/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SessionExportModal, type SessionExportModalProps } from '../SessionExportModal';

const {
  toastMock,
  exportChatMock,
  exportSessionZipPackMock,
  downloadAsHtmlMock,
  downloadAsMarkdownMock,
  downloadAsJsonMock,
  copyAsMarkdownMock,
  getExportLangMock,
} = vi.hoisted(() => ({
  toastMock: vi.fn(),
  exportChatMock: vi.fn(),
  exportSessionZipPackMock: vi.fn(),
  downloadAsHtmlMock: vi.fn(),
  downloadAsMarkdownMock: vi.fn(),
  downloadAsJsonMock: vi.fn(),
  copyAsMarkdownMock: vi.fn(),
  getExportLangMock: vi.fn(),
}));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'zh'));

vi.mock('next-themes', () => ({
  useTheme: () => ({ resolvedTheme: 'light' }),
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: toastMock,
}));

vi.mock('@/services/chat', () => ({
  exportChat: (...args: unknown[]) => exportChatMock(...args),
}));

vi.mock('@/services/chatExportPack', () => ({
  exportSessionZipPack: (...args: unknown[]) => exportSessionZipPackMock(...args),
}));

vi.mock('@/lib/utils/chat-export', () => ({
  downloadAsHtml: (...args: unknown[]) => downloadAsHtmlMock(...args),
  downloadAsMarkdown: (...args: unknown[]) => downloadAsMarkdownMock(...args),
  downloadAsJson: (...args: unknown[]) => downloadAsJsonMock(...args),
  copyAsMarkdown: (...args: unknown[]) => copyAsMarkdownMock(...args),
  getExportLang: () => getExportLangMock(),
}));

const mockExportData = {
  chatId: 'c123',
  title: 'Test Session',
  messages: [
    {
      id: 'm1',
      role: 'user',
      content: 'hello',
      createdAt: '2026-10-01T00:00:00Z',
    },
    {
      id: 'm2',
      role: 'assistant',
      content: 'world',
      createdAt: '2026-10-01T00:00:01Z',
    },
  ],
};

describe('SessionExportModal', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    exportChatMock.mockResolvedValue(mockExportData);
    exportSessionZipPackMock.mockResolvedValue(undefined);
    downloadAsHtmlMock.mockResolvedValue(undefined);
    downloadAsMarkdownMock.mockReturnValue(undefined);
    downloadAsJsonMock.mockReturnValue(undefined);
    copyAsMarkdownMock.mockResolvedValue(true);
    getExportLangMock.mockReturnValue('zh');
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders modal with all 4 formats and default options', () => {
    const onOpenChange = vi.fn();
    render(<SessionExportModal open onOpenChange={onOpenChange} chatId="c123" chatTitle="Test Session" />);

    expect(screen.getByText('导出会话与知识分享')).toBeInTheDocument();
    expect(screen.getByText('Test Session')).toBeInTheDocument();

    expect(screen.getByText('HTML')).toBeInTheDocument();
    expect(screen.getByText('Markdown')).toBeInTheDocument();
    expect(screen.getByText('JSON')).toBeInTheDocument();
    expect(screen.getByText('ZIP Pack')).toBeInTheDocument();

    expect(screen.getByText('自动脱敏敏感凭据')).toBeInTheDocument();
    expect(screen.getByText('包含模型思考过程 (Thinking)')).toBeInTheDocument();
    expect(screen.getByText('包含工具调用与耗时分析')).toBeInTheDocument();

    expect(screen.getByText('复制为 Markdown')).toBeInTheDocument();
    expect(screen.getByText('下载所选格式')).toBeInTheDocument();
  });

  it('exports HTML by default with redaction and options enabled', async () => {
    const onOpenChange = vi.fn();
    render(<SessionExportModal open onOpenChange={onOpenChange} chatId="c123" chatTitle="Test Session" />);

    const downloadBtn = screen.getByText('下载所选格式');
    fireEvent.click(downloadBtn);

    await waitFor(() => {
      expect(exportChatMock).toHaveBeenCalledWith('c123', { redactSecrets: true });
      expect(downloadAsHtmlMock).toHaveBeenCalledWith(mockExportData, 'light', 'zh', {
        includeReasoning: true,
        includeToolCalls: true,
      });
      expect(onOpenChange).toHaveBeenCalledWith(false);
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ title: '导出成功（已自动脱敏敏感凭据）', variant: 'default' }),
      );
    });
  });

  it('switches to Markdown format and triggers downloadAsMarkdown', async () => {
    const onOpenChange = vi.fn();
    render(<SessionExportModal open onOpenChange={onOpenChange} chatId="c123" chatTitle="Test Session" />);

    fireEvent.click(screen.getByText('Markdown'));
    fireEvent.click(screen.getByText('下载所选格式'));

    await waitFor(() => {
      expect(downloadAsMarkdownMock).toHaveBeenCalledWith(mockExportData, {
        includeReasoning: true,
        includeToolCalls: true,
      });
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('switches to JSON format and triggers downloadAsJson', async () => {
    const onOpenChange = vi.fn();
    render(<SessionExportModal open onOpenChange={onOpenChange} chatId="c123" chatTitle="Test Session" />);

    fireEvent.click(screen.getByText('JSON'));
    fireEvent.click(screen.getByText('下载所选格式'));

    await waitFor(() => {
      expect(downloadAsJsonMock).toHaveBeenCalledWith(mockExportData, {
        includeReasoning: true,
        includeToolCalls: true,
      });
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  it('switches to ZIP pack, hides fine-grained checkboxes, and triggers exportSessionZipPack', async () => {
    const onOpenChange = vi.fn();
    render(<SessionExportModal open onOpenChange={onOpenChange} chatId="c123" chatTitle="Test Session" />);

    fireEvent.click(screen.getByText('ZIP Pack'));

    // Fine-grained checkboxes are hidden for ZIP pack
    expect(screen.queryByText('包含模型思考过程 (Thinking)')).not.toBeInTheDocument();
    expect(screen.queryByText('包含工具调用与耗时分析')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('下载所选格式'));

    await waitFor(() => {
      expect(exportSessionZipPackMock).toHaveBeenCalledWith('c123', {
        redactSecrets: true,
        includeArtifacts: true,
        includeSubagents: true,
      });
      expect(onOpenChange).toHaveBeenCalledWith(false);
      expect(toastMock).toHaveBeenCalledWith(expect.objectContaining({ title: '导出成功', variant: 'default' }));
    });
  });

  it('copies Markdown with fine-grained options when clicking copy button', async () => {
    const onOpenChange = vi.fn();
    render(<SessionExportModal open onOpenChange={onOpenChange} chatId="c123" chatTitle="Test Session" />);

    const copyBtn = screen.getByText('复制为 Markdown');
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(exportChatMock).toHaveBeenCalledWith('c123', { redactSecrets: true });
      expect(copyAsMarkdownMock).toHaveBeenCalledWith(mockExportData, {
        includeReasoning: true,
        includeToolCalls: true,
      });
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ title: '已复制到剪贴板（已自动脱敏敏感凭据）', variant: 'default' }),
      );
    });
  });

  it('handles empty messages gracefully with warning toast', async () => {
    exportChatMock.mockResolvedValueOnce({ chatId: 'c123', messages: [] });
    const onOpenChange = vi.fn();
    render(<SessionExportModal open onOpenChange={onOpenChange} chatId="c123" chatTitle="Test Session" />);

    fireEvent.click(screen.getByText('下载所选格式'));

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith(expect.objectContaining({ title: '无消息可导出' }));
      expect(downloadAsHtmlMock).not.toHaveBeenCalled();
      expect(onOpenChange).not.toHaveBeenCalled();
    });
  });

  it('shows error toast when export service fails', async () => {
    exportChatMock.mockRejectedValueOnce(new Error('Network disconnected'));
    const onOpenChange = vi.fn();
    render(<SessionExportModal open onOpenChange={onOpenChange} chatId="c123" chatTitle="Test Session" />);

    fireEvent.click(screen.getByText('下载所选格式'));

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({
          title: '导出失败',
          description: 'Network disconnected',
          variant: 'destructive',
        }),
      );
    });
  });

  it('honors initialFormat prop and automatically selects designated format', async () => {
    const onOpenChange = vi.fn();
    render(
      <SessionExportModal
        open
        onOpenChange={onOpenChange}
        chatId="c123"
        chatTitle="Test Session"
        initialFormat="zip"
      />,
    );

    fireEvent.click(screen.getByText('下载所选格式'));

    await waitFor(() => {
      expect(exportSessionZipPackMock).toHaveBeenCalledWith('c123', {
        redactSecrets: true,
        includeArtifacts: true,
        includeSubagents: true,
      });
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  describe('which format is selected', () => {
    type Request = Pick<SessionExportModalProps, 'open' | 'initialFormat'>;
    const EXPORTERS = {
      html: downloadAsHtmlMock,
      markdown: downloadAsMarkdownMock,
      json: downloadAsJsonMock,
      zip: exportSessionZipPackMock,
    };

    /** Renders the dialog and returns a way to change what the caller asks of it, as the parent does. */
    function renderDialog(first: Request) {
      const dialog = (request: Request) => (
        <SessionExportModal chatId="c123" chatTitle="Test Session" onOpenChange={vi.fn()} {...request} />
      );
      const view = render(dialog(first));
      return (next: Request) => view.rerender(dialog(next));
    }

    /** Downloads with whatever is selected and names the format that was exported. */
    async function formatDownloaded(): Promise<string> {
      const exported = () =>
        Object.entries(EXPORTERS)
          .filter(([, exporter]) => exporter.mock.calls.length > 0)
          .map(([format]) => format);
      fireEvent.click(screen.getByText('下载所选格式'));
      await waitFor(() => expect(exported()).not.toHaveLength(0));
      return exported().join();
    }

    it('keeps the format the user picked for as long as the dialog stays open', async () => {
      const ask = renderDialog({ open: true, initialFormat: 'zip' });
      fireEvent.click(screen.getByText('Markdown'));

      ask({ open: true, initialFormat: 'zip' });

      expect(await formatDownloaded()).toBe('markdown');
    });

    it('applies the asked-for format again each time the dialog opens', async () => {
      const ask = renderDialog({ open: true, initialFormat: 'zip' });
      fireEvent.click(screen.getByText('Markdown'));

      ask({ open: false, initialFormat: 'zip' });
      ask({ open: true, initialFormat: 'zip' });

      expect(await formatDownloaded()).toBe('zip');
    });

    it('keeps the earlier pick when the dialog opens again without an asked-for format', async () => {
      const ask = renderDialog({ open: true });
      fireEvent.click(screen.getByText('JSON'));

      ask({ open: false });
      ask({ open: true });

      expect(await formatDownloaded()).toBe('json');
    });

    it('follows a different format asked for while the dialog is open', async () => {
      const ask = renderDialog({ open: true, initialFormat: 'zip' });

      ask({ open: true, initialFormat: 'json' });

      expect(await formatDownloaded()).toBe('json');
    });

    it('applies a format asked for while the dialog was closed once it opens', async () => {
      const ask = renderDialog({ open: false });

      ask({ open: false, initialFormat: 'json' });
      ask({ open: true, initialFormat: 'json' });

      expect(await formatDownloaded()).toBe('json');
    });

    it('leaves the selection alone when the ask is withdrawn while the dialog is open', async () => {
      const ask = renderDialog({ open: true, initialFormat: 'zip' });

      ask({ open: true });

      expect(await formatDownloaded()).toBe('zip');
    });
  });
});
