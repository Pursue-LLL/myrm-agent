/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const getPendingEditsMock = vi.fn();
const approveEditMock = vi.fn();

const stableT = (key: string, values?: Record<string, string>) =>
  values?.scope ? `${key}:${values.scope}` : key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    promise: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
    message: vi.fn(),
  },
}));

vi.mock('@/lib/api', () => ({
  ApiError: class ApiError extends Error {},
}));

vi.mock('next/link', () => ({
  default: ({ href, children, ...rest }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

vi.mock('../WikiScopeChip', () => ({
  WikiScopeChip: ({ scopeLabel }: { scopeLabel: string }) => <div data-testid="wiki-scope-chip">{scopeLabel}</div>,
}));

vi.mock('@/services/wikiService', () => ({
  wikiService: {
    getPendingEdits: (...args: unknown[]) => getPendingEditsMock(...args),
    approveEdit: (...args: unknown[]) => approveEditMock(...args),
    rejectEdit: vi.fn(),
  },
}));

import { WikiPendingEdits } from '../WikiPendingEdits';

describe('WikiPendingEdits agent scope reload', () => {
  beforeEach(() => {
    getPendingEditsMock.mockReset();
    approveEditMock.mockReset();
    getPendingEditsMock.mockResolvedValue({
      stats: { pending: 1 },
      pending_edits: [
        {
          id: 1,
          concept_name: 'Alpha',
          proposed_content: 'draft',
          status: 'pending',
          created_at: '2026-07-29T00:00:00.000Z',
          updated_at: '2026-07-29T00:00:00.000Z',
        },
      ],
    });
    approveEditMock.mockResolvedValue({ success: true, message: 'ok' });
  });

  it('reloads pending edits when agent scope changes', async () => {
    const { rerender } = render(<WikiPendingEdits agentScopeId="agent-a" scopeLabel="Agent A" />);

    await waitFor(() => {
      expect(getPendingEditsMock).toHaveBeenCalledWith('agent-a');
    });

    rerender(<WikiPendingEdits agentScopeId="agent-b" scopeLabel="Agent B" />);

    await waitFor(() => {
      expect(getPendingEditsMock).toHaveBeenCalledWith('agent-b');
    });
  });

  it('approves edits against the active agent scope', async () => {
    render(<WikiPendingEdits agentScopeId="agent-a" scopeLabel="Agent A" />);

    await waitFor(() => {
      expect(screen.getByText('Alpha')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('pendingEdits.approve'));

    await waitFor(() => {
      expect(approveEditMock).toHaveBeenCalledWith(1, undefined, 'agent-a');
    });
  });

  it('renders message-level source jump when source_message is present', async () => {
    getPendingEditsMock.mockResolvedValue({
      stats: { pending: 1 },
      pending_edits: [
        {
          id: 1,
          concept_name: 'Alpha',
          provenance: 'chat-compound',
          proposed_content:
            '---\nsource_chat: chat-123\nsource_message: msg-456\n---\n# Alpha\ndraft',
          status: 'pending',
          created_at: '2026-07-29T00:00:00.000Z',
          updated_at: '2026-07-29T00:00:00.000Z',
        },
      ],
    });

    render(<WikiPendingEdits agentScopeId="agent-a" scopeLabel="Agent A" />);

    await waitFor(() => {
      expect(screen.getByText('Alpha')).toBeTruthy();
    });

    const link = screen.getByText('pendingEdits.openSourceChat') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('/chat-123?highlight=msg-456');
  });

  it('falls back to chat-level link when source_message is absent', async () => {
    getPendingEditsMock.mockResolvedValue({
      stats: { pending: 1 },
      pending_edits: [
        {
          id: 1,
          concept_name: 'Alpha',
          provenance: 'chat-compound',
          proposed_content: '---\nsource_chat: chat-123\n---\n# Alpha\ndraft',
          status: 'pending',
          created_at: '2026-07-29T00:00:00.000Z',
          updated_at: '2026-07-29T00:00:00.000Z',
        },
      ],
    });

    render(<WikiPendingEdits agentScopeId="agent-a" scopeLabel="Agent A" />);

    await waitFor(() => {
      expect(screen.getByText('Alpha')).toBeTruthy();
    });

    const link = screen.getByText('pendingEdits.openSourceChat') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toBe('/chat-123');
  });

  it('omits source jump for non-chat provenance', async () => {
    getPendingEditsMock.mockResolvedValue({
      stats: { pending: 1 },
      pending_edits: [
        {
          id: 1,
          concept_name: 'Alpha',
          provenance: 'extension',
          proposed_content: '---\nsource_chat: chat-123\n---\n# Alpha\ndraft',
          status: 'pending',
          created_at: '2026-07-29T00:00:00.000Z',
          updated_at: '2026-07-29T00:00:00.000Z',
        },
      ],
    });

    render(<WikiPendingEdits agentScopeId="agent-a" scopeLabel="Agent A" />);

    await waitFor(() => {
      expect(screen.getByText('Alpha')).toBeTruthy();
    });

    expect(screen.queryByText('pendingEdits.openSourceChat')).toBeNull();
  });
});
