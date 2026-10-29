import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NewsletterRichStyler } from '../NewsletterRichStyler';
import { useArtifactSandboxStore } from '../useArtifactSandboxStore';

describe('NewsletterRichStyler', () => {
  beforeEach(() => {
    useArtifactSandboxStore.getState().resetAll();
    // mock navigator.clipboard
    Object.assign(navigator, {
      clipboard: {
        write: vi.fn().mockResolvedValue(undefined),
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });
  });

  it('正常渲染排版面板、4 大主题卡片与实时内联富文本预览区', () => {
    render(<NewsletterRichStyler />);
    expect(screen.getByTestId('newsletter-rich-styler')).toBeInTheDocument();
    expect(screen.getByTestId('theme-card-mint_breeze')).toBeInTheDocument();
    expect(screen.getByTestId('theme-card-executive_noir')).toBeInTheDocument();
    expect(screen.getByTestId('theme-card-cyber_blue')).toBeInTheDocument();
    expect(screen.getByTestId('theme-card-retro_amber')).toBeInTheDocument();
    expect(screen.getByTestId('copy-rich-html-btn')).toBeInTheDocument();
    expect(
      screen.getByTestId('rich-html-preview-container')
    ).toBeInTheDocument();
  });

  it('支持点击主题卡片切换排版主题', () => {
    render(<NewsletterRichStyler />);
    const noirCard = screen.getByTestId('theme-card-executive_noir');

    fireEvent.click(noirCard);
    expect(useArtifactSandboxStore.getState().activeTheme).toBe(
      'executive_noir'
    );
  });

  it('点击一键复制公众号富文本按钮，触发剪贴板写入并展示成功反馈', async () => {
    const handleCopySuccess = vi.fn();
    render(<NewsletterRichStyler onCopySuccess={handleCopySuccess} />);

    const copyBtn = screen.getByTestId('copy-rich-html-btn');
    fireEvent.click(copyBtn);

    await waitFor(() => {
      expect(handleCopySuccess).toHaveBeenCalledTimes(1);
    });

    expect(handleCopySuccess).toHaveBeenCalledWith(
      expect.objectContaining({
        success: true,
        themeUsed: 'mint_breeze',
      })
    );
    expect(
      screen.getByText('已复制公众号富文本!')
    ).toBeInTheDocument();
  });

  it('点击导出单文件 HTML 按钮触发回调', () => {
    const handleExport = vi.fn();
    render(<NewsletterRichStyler onExportOffline={handleExport} />);

    const exportBtn = screen.getByTestId('export-offline-html-btn');
    fireEvent.click(exportBtn);

    expect(handleExport).toHaveBeenCalledTimes(1);
    expect(handleExport).toHaveBeenCalledWith(
      expect.stringContaining('rich-newsletter-container')
    );
  });
});
