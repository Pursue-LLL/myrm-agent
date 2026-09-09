/** @vitest-environment jsdom */
'use client';

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import BrowserInspectorToggle from '../BrowserInspectorToggle';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useChatStore from '@/store/useChatStore';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

describe('BrowserInspectorToggle', () => {
  beforeEach(() => {
    useBrowserInspectorStore.getState().reset();
    useChatStore.setState({ chatId: 'chat-1' });
  });

  it('renders nothing when browser is inactive and no viewData/terminalViewData exists', () => {
    const { container } = render(<BrowserInspectorToggle />);
    expect(container.firstChild).toBeNull();
  });

  it('renders toggle button when browser is active with live view', () => {
    useBrowserInspectorStore.setState({
      isBrowserActive: true,
      viewData: {
        screenshotBase64: 'live_base64_data',
        mimeType: 'image/png',
        refs: {},
        chatId: 'chat-1',
        viewportWidth: 1280,
        viewportHeight: 720,
        sourceChatId: 'chat-1',
        isTurnView: true,
        updatedAt: Date.now(),
      },
    });

    render(<BrowserInspectorToggle />);
    const button = screen.getByTestId('browser-inspector-toggle-button');
    expect(button).toBeDefined();
  });

  it('renders toggle button when browser turn ends but terminalViewData is retained', () => {
    useBrowserInspectorStore.setState({
      isBrowserActive: false,
      viewData: null,
      terminalViewData: {
        screenshotBase64: 'terminal_snapshot_base64',
        mimeType: 'image/png',
        refs: {},
        pageUrl: 'https://example.com/done',
        pageTitle: 'Turn Completed Page',
        chatId: 'chat-1',
        viewportWidth: 1280,
        viewportHeight: 720,
        sourceChatId: 'chat-1',
        isTurnView: true,
        updatedAt: Date.now(),
      },
    });

    render(<BrowserInspectorToggle />);
    const button = screen.getByTestId('browser-inspector-toggle-button');
    expect(button).toBeDefined();
  });

  it('displays hover micro peek thumbnail on mouse enter and hides on mouse leave', () => {
    useBrowserInspectorStore.setState({
      isBrowserActive: true,
      viewData: {
        screenshotBase64: 'hover_peek_shot',
        mimeType: 'image/png',
        refs: {},
        pageUrl: 'https://example.com/hover',
        pageTitle: 'Peek Preview',
        chatId: 'chat-1',
        viewportWidth: 1280,
        viewportHeight: 720,
        sourceChatId: 'chat-1',
        isTurnView: true,
        updatedAt: Date.now(),
      },
    });

    render(<BrowserInspectorToggle />);
    const toggleButton = screen.getByTestId('browser-inspector-toggle-button');
    const container = toggleButton.parentElement;
    expect(container).not.toBeNull();
    if (!container) {
      return;
    }

    // Initial state: not hovered
    expect(screen.queryByTestId('browser-inspector-peek-thumbnail')).toBeNull();

    // Hover container
    fireEvent.mouseEnter(container);
    expect(screen.getByTestId('browser-inspector-peek-thumbnail')).toBeDefined();
    expect(screen.getByText('Peek Preview')).toBeDefined();
    expect(screen.getByText('https://example.com/hover')).toBeDefined();

    // Leave container
    fireEvent.mouseLeave(container);
    expect(screen.queryByTestId('browser-inspector-peek-thumbnail')).toBeNull();
  });

  it('calls togglePanel on click', () => {
    useBrowserInspectorStore.setState({
      isBrowserActive: true,
      viewData: {
        screenshotBase64: 'shot',
        mimeType: 'image/png',
        refs: {},
        chatId: 'chat-1',
        viewportWidth: 800,
        viewportHeight: 600,
        sourceChatId: 'chat-1',
        isTurnView: true,
        updatedAt: Date.now(),
      },
    });

    render(<BrowserInspectorToggle />);
    const button = screen.getByTestId('browser-inspector-toggle-button');

    expect(useBrowserInspectorStore.getState().isOpen).toBe(false);
    fireEvent.click(button);
    expect(useBrowserInspectorStore.getState().isOpen).toBe(true);
  });
});
