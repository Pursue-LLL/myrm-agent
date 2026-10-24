import { act, fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import ReasoningProcessAccordion from '../ReasoningProcessAccordion';
import type { Message } from '@/store/chat/types';

const translate = vi.hoisted(() => (key: string, params?: Record<string, unknown>) => {
  if (params) {
    return `${key}:${JSON.stringify(params)}`;
  }
  return key;
});

vi.mock('next-intl', () => ({
  useTranslations: () => translate,
}));

const markdownProps = vi.hoisted(() => ({ sources: [] as unknown[] }));

vi.mock('../MarkdownContent', () => ({
  default: ({ content, isStreaming, sources }: { content: string; isStreaming?: boolean; sources?: unknown[] }) => {
    markdownProps.sources.push(sources);
    return (
      <div data-testid="mock-markdown-content" data-streaming={isStreaming ? 'true' : 'false'}>
        {content}
      </div>
    );
  },
}));

function createMockMessage(overrides?: Partial<Message>): Message {
  return {
    messageId: 'msg-reasoning-1',
    chatId: 'chat-reasoning-1',
    createdAt: new Date(),
    role: 'assistant',
    content: 'Final response body',
    reasoning: 'First let us consider the axioms of algebra...',
    reasoningDurationMs: 14000,
    ...overrides,
  };
}

describe('ReasoningProcessAccordion', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders completed thinking with duration and token count in collapsed mode', () => {
    const onToggle = vi.fn();
    render(
      <ReasoningProcessAccordion
        message={createMockMessage()}
        isLast={true}
        loading={false}
        isExpanded={false}
        onToggle={onToggle}
        displayMode="collapsed"
      />,
    );

    expect(screen.getByTestId('reasoning-process-accordion')).toBeDefined();
    expect(screen.getByText('reasoningCompleted:{"seconds":14}')).toBeDefined();
    // 无真实 usage 时回落到字符估算，并显式标注 ≈
    expect(screen.getByText('reasoningTokensEstimated:{"count":12}')).toBeDefined();

    // Content should not be shown when collapsed
    expect(screen.queryByTestId('mock-markdown-content')).toBeNull();

    // Click to toggle
    fireEvent.click(screen.getByRole('button', { name: /reasoningCompleted/i }));
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it('renders reasoning markdown content when expanded', () => {
    render(
      <ReasoningProcessAccordion
        message={createMockMessage()}
        isLast={true}
        loading={false}
        isExpanded={true}
        onToggle={vi.fn()}
        displayMode="collapsed"
      />,
    );

    const markdown = screen.getByTestId('mock-markdown-content');
    expect(markdown).toBeDefined();
    expect(markdown.textContent).toContain('First let us consider the axioms of algebra...');
    expect(markdown.getAttribute('data-streaming')).toBe('false');
  });

  it('renders inline mode with content always visible', () => {
    render(
      <ReasoningProcessAccordion
        message={createMockMessage()}
        isLast={true}
        loading={false}
        isExpanded={false}
        onToggle={vi.fn()}
        displayMode="inline"
      />,
    );

    expect(screen.getByTestId('mock-markdown-content')).toBeDefined();
  });

  it('renders live thinking stream indicator when model is still reasoning', () => {
    const now = Date.now();
    const liveMessage = createMockMessage({
      content: '', // No final content yet
      reasoning: 'Analyzing hypotheses...',
      reasoningStartedAt: now - 5000,
      reasoningDurationMs: undefined,
    });

    render(
      <ReasoningProcessAccordion
        message={liveMessage}
        isLast={true}
        loading={true}
        isExpanded={true}
        onToggle={vi.fn()}
        displayMode="collapsed"
      />,
    );

    expect(screen.getByText('reasoningThinking:{"seconds":5}')).toBeDefined();
    const markdown = screen.getByTestId('mock-markdown-content');
    expect(markdown.getAttribute('data-streaming')).toBe('true');
  });

  it('copies reasoning text to clipboard on copy click', async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(
      <ReasoningProcessAccordion
        message={createMockMessage()}
        isLast={false}
        loading={false}
        isExpanded={false}
        onToggle={vi.fn()}
        displayMode="collapsed"
      />,
    );

    const copyBtn = screen.getByTitle('copyReasoning');
    await act(async () => {
      fireEvent.click(copyBtn);
    });

    expect(writeTextMock).toHaveBeenCalledWith('First let us consider the axioms of algebra...');
  });

  it('renders step telemetry and triggers onStopThinking callback', async () => {
    const onStopThinking = vi.fn().mockResolvedValue(undefined);
    const liveMessageWithSteps = createMockMessage({
      content: '',
      chatId: 'chat-456',
      reasoning: 'Analyzing query structure...',
      thinkingItems: ['Analyze query', 'Retrieve schemas'],
      reasoningStartedAt: Date.now() - 3000,
    });

    render(
      <ReasoningProcessAccordion
        message={liveMessageWithSteps}
        isLast={true}
        loading={true}
        isExpanded={false}
        onToggle={vi.fn()}
        displayMode="collapsed"
        onStopThinking={onStopThinking}
      />,
    );

    expect(screen.getByText(/reasoningSteps:\{"count":2\}/)).toBeDefined();

    const stopBtn = screen.getByTestId('stop-thinking-button');
    expect(stopBtn).toBeDefined();

    await act(async () => {
      fireEvent.click(stopBtn);
    });

    expect(onStopThinking).toHaveBeenCalledWith('chat-456');
  });

  it('falls back to default API fetch when onStopThinking is not passed', async () => {
    const globalFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ success: true }),
    });
    vi.stubGlobal('fetch', globalFetch);

    const liveMessage = createMockMessage({
      content: '',
      chatId: 'chat-789',
      reasoning: 'Synthesizing...',
      reasoningStartedAt: Date.now() - 2000,
    });

    render(
      <ReasoningProcessAccordion
        message={liveMessage}
        isLast={true}
        loading={true}
        isExpanded={false}
        onToggle={vi.fn()}
        displayMode="collapsed"
      />,
    );

    const stopBtn = screen.getByTestId('stop-thinking-button');
    await act(async () => {
      fireEvent.click(stopBtn);
    });

    expect(globalFetch).toHaveBeenCalledWith(
      '/api/v1/chats/chat-789/stop-thinking',
      expect.objectContaining({
        method: 'POST',
      }),
    );

    vi.unstubAllGlobals();
  });

  it('prefers the provider-reported reasoning tokens over the character estimate', () => {
    render(
      <ReasoningProcessAccordion
        message={createMockMessage({
          usage: {
            prompt_tokens: 10,
            completion_tokens: 5,
            total_tokens: 15,
            reasoning_tokens: 99,
          },
        })}
        isLast={false}
        loading={false}
        isExpanded={false}
        onToggle={vi.fn()}
        displayMode="collapsed"
      />,
    );

    expect(screen.getByText('reasoningTokens:{"count":99}')).toBeDefined();
    expect(screen.queryByText('reasoningTokensEstimated:{"count":12}')).toBeNull();
  });

  it('keeps the sources prop reference stable so the markdown memo is not defeated by the 1s timer', () => {
    vi.useFakeTimers();
    try {
      markdownProps.sources = [];
      const live = createMockMessage({
        content: '',
        reasoningStartedAt: Date.now() - 3000,
      });
      render(
        <ReasoningProcessAccordion
          message={live}
          isLast={true}
          loading={true}
          isExpanded={true}
          onToggle={vi.fn()}
          displayMode="collapsed"
        />,
      );

      const first = markdownProps.sources.at(-1);
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      const second = markdownProps.sources.at(-1);

      expect(markdownProps.sources.length).toBeGreaterThan(1);
      expect(second).toBe(first);
    } finally {
      vi.useRealTimers();
    }
  });

  it('aborts a hung stop-thinking request after 10s so the button cannot stay stuck', async () => {
    vi.useFakeTimers();
    const signals: AbortSignal[] = [];
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      const signal = init?.signal as AbortSignal | undefined;
      if (signal) signals.push(signal);
      return new Promise<Response>((_resolve, reject) => {
        signal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    try {
      const live = createMockMessage({ content: '', reasoningStartedAt: Date.now() - 3000 });
      render(
        <ReasoningProcessAccordion
          message={live}
          isLast={true}
          loading={true}
          isExpanded={false}
          onToggle={vi.fn()}
          displayMode="collapsed"
        />,
      );

      await act(async () => {
        fireEvent.click(screen.getByTestId('stop-thinking-button'));
      });
      expect(signals).toHaveLength(1);
      expect(signals[0].aborted).toBe(false);

      await act(async () => {
        vi.advanceTimersByTime(10_000);
      });

      expect(signals[0].aborted).toBe(true);
      expect(screen.getByTestId('stop-thinking-button')).not.toBeDisabled();
    } finally {
      vi.unstubAllGlobals();
      vi.useRealTimers();
    }
  });
});
