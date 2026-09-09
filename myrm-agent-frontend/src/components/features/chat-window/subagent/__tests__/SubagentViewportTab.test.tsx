// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import SubagentViewportTab from '../SubagentViewportTab';
import useBrowserInspectorStore from '@/store/useBrowserInspectorStore';
import useChatStore from '@/store/useChatStore';
import type { SubagentNode } from '@/store/chat/useSubagentStore';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => {
  const dummy = vi.fn();
  return {
    toast: Object.assign(dummy, {
      info: vi.fn(),
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      promise: vi.fn(),
      loading: vi.fn(),
      dismiss: vi.fn(),
      message: vi.fn(),
    }),
  };
});

function makeNode(partial: Partial<SubagentNode>): SubagentNode {
  return {
    task_id: 'subtask-12345678',
    parent_task_id: '',
    agent_type: 'researcher',
    description: 'Researching web',
    status: 'running',
    progress: 50,
    stream: [],
    ...partial,
  };
}

describe('SubagentViewportTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useBrowserInspectorStore.getState().reset();
    useChatStore.setState({ chatId: 'chat-42' });
  });

  it('renders placeholder card when subagent is text/code only without browser snapshots', () => {
    const node = makeNode({
      agent_type: 'coder',
      description: 'Writing python code',
      stream: [
        {
          kind: 'tool',
          text: 'Running bash command `ls`',
          timestamp: Date.now(),
        },
      ],
    });

    render(<SubagentViewportTab node={node} chatId="chat-42" />);

    expect(screen.getByTestId('subagent-viewport-empty')).toBeDefined();
    expect(screen.getByText('纯文本/代码任务视口')).toBeDefined();
  });

  it('dispatches open_visual_desktop event when clicking open desktop button in placeholder card', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const node = makeNode({});

    render(<SubagentViewportTab node={node} chatId="chat-42" />);

    const openBtn = screen.getByTestId('subagent-viewport-open-desktop-btn');
    fireEvent.click(openBtn);

    expect(dispatchSpy).toHaveBeenCalledTimes(1);
    const event = dispatchSpy.mock.calls[0][0] as CustomEvent;
    expect(event.type).toBe('open_visual_desktop');
  });

  it('renders active viewport when subagent stream contains screenshot base64 json', () => {
    const node = makeNode({
      stream: [
        {
          kind: 'tool',
          text: JSON.stringify({
            url: 'https://news.ycombinator.com',
            title: 'Hacker News',
            screenshot_base64: 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
          }),
          timestamp: Date.now(),
        },
      ],
    });

    render(<SubagentViewportTab node={node} chatId="chat-42" />);

    expect(screen.getByTestId('subagent-viewport-active')).toBeDefined();
    expect(screen.getByText('https://news.ycombinator.com')).toBeDefined();
    expect(screen.getByText('Snapshot')).toBeDefined();

    const img = screen.getByAltText('Hacker News') as HTMLImageElement;
    expect(img.src).toContain('data:image/png;base64');
  });

  it('dispatches open_visual_desktop when takeover button is clicked in active viewport', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const node = makeNode({
      stream: [
        {
          kind: 'tool',
          text: JSON.stringify({
            url: 'https://example.com',
            screenshot: 'test_base64_data_12345678901234567890',
          }),
          timestamp: Date.now(),
        },
      ],
    });

    render(<SubagentViewportTab node={node} chatId="chat-42" />);

    const takeoverBtn = screen.getByTestId('subagent-viewport-takeover-btn');
    fireEvent.click(takeoverBtn);

    expect(dispatchSpy).toHaveBeenCalledTimes(1);
    const event = dispatchSpy.mock.calls[0][0] as CustomEvent;
    expect(event.type).toBe('open_visual_desktop');
  });

  it('falls back to scoped browser inspector view when subagent is running browser tools', () => {
    useBrowserInspectorStore.setState({
      isBrowserActive: true,
      viewData: {
        screenshotBase64: 'scoped_live_screen',
        mimeType: 'image/png',
        refs: {},
        pageUrl: 'https://sandbox.internal/dashboard',
        pageTitle: 'Sandbox Live App',
        chatId: 'chat-42',
        viewportWidth: 1280,
        viewportHeight: 720,
        sourceChatId: 'chat-42',
        isTurnView: true,
        updatedAt: Date.now(),
      },
    });

    const node = makeNode({
      agent_type: 'browser-navigator',
      last_tool: 'browser_click',
    });

    render(<SubagentViewportTab node={node} chatId="chat-42" />);

    expect(screen.getByTestId('subagent-viewport-active')).toBeDefined();
    expect(screen.getByText('Live')).toBeDefined();
    expect(screen.getByText('https://sandbox.internal/dashboard')).toBeDefined();
  });

  it('enters zoom mode on click and exits zoom mode when Escape key is pressed', () => {
    const node = makeNode({
      stream: [
        {
          kind: 'tool',
          text: JSON.stringify({
            url: 'https://example.com',
            screenshot: 'test_base64_data_12345678901234567890',
          }),
          timestamp: Date.now(),
        },
      ],
    });

    render(<SubagentViewportTab node={node} chatId="chat-42" />);

    const zoomBtn = screen.getByTitle('全屏缩放');
    fireEvent.click(zoomBtn);

    expect(screen.getByText('退出放大')).toBeDefined();

    // Press Escape key
    fireEvent.keyDown(window, { key: 'Escape' });

    expect(screen.queryByText('退出放大')).toBeNull();
  });

  it('exits zoom mode when clicking the backdrop, but keeps zoom when clicking the image', () => {
    const node = makeNode({
      stream: [
        {
          kind: 'tool',
          text: JSON.stringify({
            url: 'https://example.com',
            screenshot: 'test_base64_data_12345678901234567890',
          }),
          timestamp: Date.now(),
        },
      ],
    });

    render(<SubagentViewportTab node={node} chatId="chat-42" />);

    const zoomBtn = screen.getByTitle('全屏缩放');
    fireEvent.click(zoomBtn);

    expect(screen.getByText('退出放大')).toBeDefined();

    // Clicking the image directly does NOT exit zoom
    const img = screen.getByAltText('Subagent Viewport Preview');
    fireEvent.click(img);
    expect(screen.getByText('退出放大')).toBeDefined();

    // Clicking the backdrop exits zoom
    const backdrop = screen.getByTestId('subagent-viewport-backdrop');
    fireEvent.click(backdrop);
    expect(screen.queryByText('退出放大')).toBeNull();
  });
});
