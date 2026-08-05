import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import MemoryInsightPanel from '@/components/features/message-box/MemoryInsightPanel';
import { retryChatMemoryExtract } from '@/services/chat';
import { getSessionExecutionTrace, type ExecutionTrace } from '@/services/statistics';

const toastMocks = vi.hoisted(() => ({
  info: vi.fn(),
  warning: vi.fn(),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: toastMocks,
}));

vi.mock('@/services/chat', () => ({
  retryChatMemoryExtract: vi.fn(),
}));

vi.mock('@/services/statistics', () => ({
  getSessionExecutionTrace: vi.fn(),
}));

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

const CHAT_ID = 'chat-retry-test';
const MESSAGE_MS = 1_700_000_000_000;

function traceWithExtractError(): ExecutionTrace {
  return {
    session_id: CHAT_ID,
    metadata: {
      user_id: null,
      agent_id: 'agent-1',
      task_type: null,
      trace_id: null,
    },
    outcome: 'success',
    start_time: MESSAGE_MS / 1000,
    end_time: MESSAGE_MS / 1000 + 10,
    duration_ms: 10_000,
    task_input: 'remember',
    output: 'ok',
    tool_calls: [],
    llm_calls: [],
    errors: [],
    human_feedback: [],
    total_events: 2,
    total_tokens: 100,
    memory_events: [
      {
        id: 'evt-write',
        kind: 'write',
        phase: 'write',
        status: 'success',
        title: 'Write',
        summary: 'Memory write ok',
        target_kind: null,
        target_id: null,
        influence_count: 0,
        timestamp: MESSAGE_MS / 1000 + 1,
      },
      {
        id: 'evt-extract',
        kind: 'extract',
        phase: 'observe',
        status: 'error',
        title: 'Extract',
        summary: '429 rate limit',
        target_kind: null,
        target_id: null,
        influence_count: 0,
        timestamp: MESSAGE_MS / 1000 + 2,
      },
    ],
  };
}

let originalResizeObserver: typeof globalThis.ResizeObserver | undefined;

describe('MemoryInsightPanel extract retry', () => {
  beforeAll(() => {
    originalResizeObserver = globalThis.ResizeObserver;
    class ResizeObserverMock {
      observe(): void {}
      unobserve(): void {}
      disconnect(): void {}
    }
    vi.stubGlobal('ResizeObserver', ResizeObserverMock);
  });

  afterAll(() => {
    if (originalResizeObserver) {
      globalThis.ResizeObserver = originalResizeObserver;
      return;
    }
    Reflect.deleteProperty(globalThis, 'ResizeObserver');
  });

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getSessionExecutionTrace).mockResolvedValue(traceWithExtractError());
  });

  it('marks extract pending when retry API returns scheduled', async () => {
    vi.mocked(retryChatMemoryExtract).mockResolvedValue({
      status: 'scheduled',
      chat_id: CHAT_ID,
    });

    render(
      <MemoryInsightPanel
        chatId={CHAT_ID}
        isLast
        isStreaming={false}
        messageCreatedAtMs={MESSAGE_MS}
      />,
    );

    const retryButton = await screen.findByRole('button', { name: 'lifecycleRetryExtract' });
    await userEvent.click(retryButton);

    await waitFor(() => {
      expect(retryChatMemoryExtract).toHaveBeenCalledWith(CHAT_ID);
    });

    expect(await screen.findByText('lifecycleExtractPending')).toBeInTheDocument();
    expect(toastMocks.info).not.toHaveBeenCalled();
  });

  it('shows info toast when retry API returns already_in_flight', async () => {
    vi.mocked(retryChatMemoryExtract).mockResolvedValue({
      status: 'already_in_flight',
      chat_id: CHAT_ID,
    });

    render(
      <MemoryInsightPanel
        chatId={CHAT_ID}
        isLast
        isStreaming={false}
        messageCreatedAtMs={MESSAGE_MS}
      />,
    );

    const retryButton = await screen.findByRole('button', { name: 'lifecycleRetryExtract' });
    await userEvent.click(retryButton);

    await waitFor(() => {
      expect(toastMocks.info).toHaveBeenCalledWith('lifecycleRetryAlreadyInFlight');
    });

    expect(screen.getByText('lifecycleError')).toBeInTheDocument();
    expect(screen.queryByText('lifecycleExtractPending')).not.toBeInTheDocument();
  });
});
