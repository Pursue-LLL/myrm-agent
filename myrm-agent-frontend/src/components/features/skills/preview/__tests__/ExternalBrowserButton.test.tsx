/** @vitest-environment jsdom */

import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ExternalBrowserButton } from '../ExternalBrowserButton';
import { ExternalPreviewService } from '../externalPreviewService';

const stableT = (key: string) => {
  const table: Record<string, string> = {
    openInBrowser: '用外部浏览器打开',
    openInBrowserDesc: '在系统原生真实浏览器中无阻断渲染',
    opening: '正在唤起外部浏览器...',
    opened: '已在外部浏览器中打开',
  };
  return table[key] ?? key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('ExternalBrowserButton', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('renders default button with title and description tooltip', () => {
    render(<ExternalBrowserButton content="<html><body>Hello</body></html>" />);

    const button = screen.getByRole('button', { name: /用外部浏览器打开/i });
    expect(button).toBeInTheDocument();
    expect(button).toHaveAttribute('title', '在系统原生真实浏览器中无阻断渲染');
  });

  it('triggers ExternalPreviewService.openInExternalBrowser on click and shows success status', async () => {
    const openSpy = vi
      .spyOn(ExternalPreviewService, 'openInExternalBrowser')
      .mockResolvedValue('/api/v1/skills/solidify/preview/prev-12345');

    render(<ExternalBrowserButton content="<html><body>Test Content</body></html>" title="测试预览" />);

    const button = screen.getByRole('button', { name: /用外部浏览器打开/i });
    fireEvent.click(button);

    expect(openSpy).toHaveBeenCalledTimes(1);
    expect(openSpy).toHaveBeenCalledWith({
      content: '<html><body>Test Content</body></html>',
      title: '测试预览',
    });

    await waitFor(() => {
      expect(screen.getByText('已在外部浏览器中打开')).toBeInTheDocument();
    });
  });

  it('renders compact mode with icon only', () => {
    render(<ExternalBrowserButton content="<div>Compact</div>" compact={true} />);

    const button = screen.getByRole('button', { name: /用外部浏览器打开/i });
    expect(button).toBeInTheDocument();
    // In compact mode, the text span is omitted
    expect(screen.queryByText('用外部浏览器打开')).toBeNull();
  });

  it('handles error state gracefully on failure', async () => {
    vi.spyOn(ExternalPreviewService, 'openInExternalBrowser').mockRejectedValue(new Error('Network failure'));

    render(<ExternalBrowserButton content="<div>Error case</div>" />);

    const button = screen.getByRole('button', { name: /用外部浏览器打开/i });
    fireEvent.click(button);

    await waitFor(() => {
      expect(button).toHaveClass('text-rose-400');
    });
  });
});
