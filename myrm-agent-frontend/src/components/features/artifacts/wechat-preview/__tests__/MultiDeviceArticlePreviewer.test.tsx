import React, { act } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MultiDeviceArticlePreviewer } from '../MultiDeviceArticlePreviewer';
import { useWechatPreviewStore } from '../useWechatPreviewStore';

const mockTranslations = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslations,
}));

describe('MultiDeviceArticlePreviewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWechatPreviewStore.getState().reset();
  });

  it('renders previewer with header HUD, filename, and default mobile frame', async () => {
    await act(async () => {
      render(
        <MultiDeviceArticlePreviewer
          content="# 架构大纲&#10;&#10;这是正文第一段。"
          title="深度长文"
          filename="deep_article.md"
        />
      );
      await Promise.resolve();
    });

    expect(screen.getByTestId('wechat-previewer-root')).toBeInTheDocument();
    expect(screen.getByTestId('wechat-previewer-toolbar')).toBeInTheDocument();
    expect(screen.getByText('deep_article.md')).toBeInTheDocument();
    expect(screen.getByTestId('device-frame-mobile')).toBeInTheDocument();

    const renderedContent = screen.getByTestId('wechat-rendered-content');
    expect(renderedContent.innerHTML).toContain('架构大纲');
    expect(renderedContent.innerHTML).toContain('这是正文第一段。');
  });

  it('switches viewports correctly across mobile, tablet, and desktop', async () => {
    await act(async () => {
      render(
        <MultiDeviceArticlePreviewer
          content="## 关键技术点"
        />
      );
      await Promise.resolve();
    });

    // 默认 mobile
    expect(screen.getByTestId('device-frame-mobile')).toBeInTheDocument();

    // 切换至 tablet
    await act(async () => {
      fireEvent.click(screen.getByTestId('viewport-tablet'));
      await Promise.resolve();
    });
    expect(screen.getByTestId('device-frame-tablet')).toBeInTheDocument();
    expect(screen.queryByTestId('device-frame-mobile')).toBeNull();

    // 切换至 desktop
    await act(async () => {
      fireEvent.click(screen.getByTestId('viewport-desktop'));
      await Promise.resolve();
    });
    expect(screen.getByTestId('device-frame-desktop')).toBeInTheDocument();
    expect(screen.queryByTestId('device-frame-tablet')).toBeNull();

    // 切换回 mobile
    await act(async () => {
      fireEvent.click(screen.getByTestId('viewport-mobile'));
      await Promise.resolve();
    });
    expect(screen.getByTestId('device-frame-mobile')).toBeInTheDocument();
  });

  it('changes theme via theme select dropdown', async () => {
    await act(async () => {
      render(
        <MultiDeviceArticlePreviewer
          content="# 主题测试"
        />
      );
      await Promise.resolve();
    });

    const themeSelect = screen.getByTestId('theme-select');
    await act(async () => {
      fireEvent.change(themeSelect, { target: { value: 'tech' } });
      await Promise.resolve();
    });

    expect(useWechatPreviewStore.getState().themeId).toBe('tech');
    const content = screen.getByTestId('wechat-rendered-content');
    // Tech theme uses #2563eb as primaryColor / border
    expect(content.innerHTML).toContain('2563eb');
  });

  it('changes font size scale via scale select dropdown', async () => {
    await act(async () => {
      render(
        <MultiDeviceArticlePreviewer
          content="# 字号测试"
        />
      );
      await Promise.resolve();
    });

    const scaleSelect = screen.getByTestId('scale-select');
    await act(async () => {
      fireEvent.change(scaleSelect, { target: { value: 'spacious' } });
      await Promise.resolve();
    });

    expect(useWechatPreviewStore.getState().scale).toBe('spacious');
    const content = screen.getByTestId('wechat-rendered-content');
    // Spacious scale expands classic 22px to 24px
    expect(content.innerHTML).toContain('font-size: 24px');
  });

  it('copies compiled HTML to clipboard and triggers onCopySuccess callback', async () => {
    const onCopySuccessMock = vi.fn();
    const writeTextMock = vi.fn().mockResolvedValue(undefined);

    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    await act(async () => {
      render(
        <MultiDeviceArticlePreviewer
          content="# 待复制文章"
          onCopySuccess={onCopySuccessMock}
        />
      );
      await Promise.resolve();
    });

    const copyBtn = screen.getByTestId('copy-wechat-btn');
    await act(async () => {
      fireEvent.click(copyBtn);
      await Promise.resolve();
    });

    expect(writeTextMock).toHaveBeenCalledTimes(1);
    expect(onCopySuccessMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText('copied')).toBeInTheDocument();
  });
});
