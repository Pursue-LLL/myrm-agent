/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SessionExportModal } from '../SessionExportModal';

const {
  toastMock,
  exportChatMock,
  exportSessionZipPackMock,
  downloadAsHtmlMock,
  downloadAsMarkdownMock,
  downloadAsJsonMock,
  copyAsMarkdownMock,
} = vi.hoisted(() => ({
  toastMock: vi.fn(),
  exportChatMock: vi.fn(),
  exportSessionZipPackMock: vi.fn(),
  downloadAsHtmlMock: vi.fn(),
  downloadAsMarkdownMock: vi.fn(),
  downloadAsJsonMock: vi.fn(),
  copyAsMarkdownMock: vi.fn(),
}));

const stableT = (key: string, values?: Record<string, string | number | undefined>): string => {
  if (values?.defaultMessage) {
    return String(values.defaultMessage);
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

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

vi.mock('@/lib/utils/chatExport', () => ({
  downloadAsHtml: (...args: unknown[]) => downloadAsHtmlMock(...args),
  downloadAsMarkdown: (...args: unknown[]) => downloadAsMarkdownMock(...args),
  downloadAsJson: (...args: unknown[]) => downloadAsJsonMock(...args),
  copyAsMarkdown: (...args: unknown[]) => copyAsMarkdownMock(...args),
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

    expect(screen.getByText('复制 Markdown')).toBeInTheDocument();
    expect(screen.getByText('下载所选格式')).toBeInTheDocument();
  });

  it('exports HTML by default with redaction and options enabled', async () => {
    const onOpenChange = vi.fn();
    render(<SessionExportModal open onOpenChange={onOpenChange} chatId="c123" chatTitle="Test Session" />);

    const downloadBtn = screen.getByText('下载所选格式');
    fireEvent.click(downloadBtn);

    await waitFor(() => {
      expect(exportChatMock).toHaveBeenCalledWith('c123', { redactSecrets: true });
      expect(downloadAsHtmlMock).toHaveBeenCalledWith(mockExportData, 'light', expect.any(String), {
        includeReasoning: true,
        includeToolCalls: true,
      });
      expect(onOpenChange).toHaveBeenCalledWith(false);
      expect(toastMock).toHaveBeenCalledWith(expect.objectContaining({ title: '已安全脱敏导出', variant: 'default' }));
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
      expect(toastMock).toHaveBeenCalledWith(expect.objectContaining({ title: '导出会话成功', variant: 'default' }));
    });
  });

  it('copies Markdown with fine-grained options when clicking copy button', async () => {
    const onOpenChange = vi.fn();
    render(<SessionExportModal open onOpenChange={onOpenChange} chatId="c123" chatTitle="Test Session" />);

    const copyBtn = screen.getByText('复制 Markdown');
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(exportChatMock).toHaveBeenCalledWith('c123', { redactSecrets: true });
      expect(copyAsMarkdownMock).toHaveBeenCalledWith(mockExportData, {
        includeReasoning: true,
        includeToolCalls: true,
      });
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ title: '已复制脱敏 Markdown', variant: 'default' }),
      );
    });
  });

  it('handles empty messages gracefully with warning toast', async () => {
    exportChatMock.mockResolvedValueOnce({ chatId: 'c123', messages: [] });
    const onOpenChange = vi.fn();
    render(<SessionExportModal open onOpenChange={onOpenChange} chatId="c123" chatTitle="Test Session" />);

    fireEvent.click(screen.getByText('下载所选格式'));

    await waitFor(() => {
      expect(toastMock).toHaveBeenCalledWith(expect.objectContaining({ title: '没有可导出的消息' }));
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
});
