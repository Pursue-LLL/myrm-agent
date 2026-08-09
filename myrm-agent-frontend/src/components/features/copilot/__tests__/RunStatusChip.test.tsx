'use client';

import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import RunStatusChip from '../RunStatusChip';
import type { RunDigest } from '@/services/copilot';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const digestMock = vi.hoisted(() => ({ current: null as RunDigest | null }));

vi.mock('@/hooks/copilot/useRunDigest', () => ({
  useRunDigest: () => ({ digest: digestMock.current, refresh: vi.fn() }),
}));

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: { loading: boolean }) => unknown) =>
    selector({ loading: false }),
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, ...props }: { children?: React.ReactNode }) => <button {...props}>{children}</button>,
}));

function runningDigest(): RunDigest {
  return {
    chat_id: 'chat-1',
    phase: 'running',
    step_count: 3,
    current_tool: 'browser_navigate',
    current_step_key: 'browser_navigate',
    pending_approval_count: 0,
    elapsed_seconds: 5,
    headline: 'Running browser',
    recent_steps: [],
    updated_at: '2026-08-08T00:00:00Z',
  };
}

describe('RunStatusChip', () => {
  beforeEach(() => {
    digestMock.current = null;
  });

  it('renders nothing when digest is null', () => {
    render(<RunStatusChip chatId="chat-1" />);
    expect(screen.queryByTestId('copilot-run-status-chip')).not.toBeInTheDocument();
  });

  it('renders nothing when digest phase is idle', () => {
    digestMock.current = { chat_id: 'chat-1', phase: 'idle' } as RunDigest;
    render(<RunStatusChip chatId="chat-1" />);
    expect(screen.queryByTestId('copilot-run-status-chip')).not.toBeInTheDocument();
  });

  it('renders chip when digest phase is running', () => {
    digestMock.current = runningDigest();
    render(<RunStatusChip chatId="chat-1" />);
    expect(screen.getByTestId('copilot-run-status-chip')).toBeInTheDocument();
    expect(screen.getByTestId('copilot-run-headline')).toHaveTextContent('headlineRunning');
  });

  it('does not crash when digest transitions from null to running (hooks parity)', () => {
    // Regression: useMemo used to sit after an early `return null`, so the
    // first render registered 3 hooks and the second registered 4, making
    // React throw "Rendered more hooks than during the previous render".
    const { rerender } = render(<RunStatusChip chatId="chat-1" />);
    expect(screen.queryByTestId('copilot-run-status-chip')).not.toBeInTheDocument();

    digestMock.current = runningDigest();
    expect(() => rerender(<RunStatusChip chatId="chat-1" />)).not.toThrow();
    expect(screen.getByTestId('copilot-run-status-chip')).toBeInTheDocument();
  });
});
