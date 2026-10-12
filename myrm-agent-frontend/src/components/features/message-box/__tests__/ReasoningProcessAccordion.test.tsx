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

vi.mock('../MarkdownContent', () => ({
  default: ({ content, isStreaming }: { content: string; isStreaming?: boolean }) => (
    <div data-testid="mock-markdown-content" data-streaming={isStreaming ? 'true' : 'false'}>
      {content}
    </div>
  ),
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
    // 46 chars / 4 ~= 12 tokens
    expect(screen.getByText('(~12 tokens)')).toBeDefined();

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
});
