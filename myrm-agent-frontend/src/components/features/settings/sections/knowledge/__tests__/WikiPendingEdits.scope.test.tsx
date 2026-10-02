/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { toastErrorSpy } = vi.hoisted(() => ({ toastErrorSpy: vi.fn() }));
const getPendingEditsMock = vi.fn();
const approveEditMock = vi.fn();
const rejectEditMock = vi.fn();

const stableT = (key: string, values?: Record<string, string>) => (values?.scope ? `${key}:${values.scope}` : key);

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: toastErrorSpy,
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
    rejectEdit: (...args: unknown[]) => rejectEditMock(...args),
  },
}));

import { WikiPendingEdits } from '../WikiPendingEdits';
import { ApiError } from '@/lib/api';

describe('WikiPendingEdits agent scope reload', () => {
  beforeEach(() => {
    getPendingEditsMock.mockReset();
    approveEditMock.mockReset();
    rejectEditMock.mockReset();
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
          proposed_content: '---\nsource_chat: chat-123\nsource_message: msg-456\n---\n# Alpha\ndraft',
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

  it('loads the next page when drafts exist beyond the first page', async () => {
    getPendingEditsMock.mockImplementation((...args: unknown[]) => {
      const offset = args[2] as number | undefined;
      const draft =
        offset === undefined
          ? { id: 1, concept_name: 'First-Page Draft' }
          : { id: 2, concept_name: 'Second-Page Draft' };
      return Promise.resolve({
        stats: { pending: 51 },
        pending_edits: [
          {
            ...draft,
            proposed_content: 'draft',
            status: 'pending',
            created_at: '2026-07-29T00:00:00.000Z',
            updated_at: '2026-07-29T00:00:00.000Z',
          },
        ],
      });
    });

    render(<WikiPendingEdits agentScopeId="agent-a" scopeLabel="Agent A" />);

    await waitFor(() => {
      expect(screen.getByText('First-Page Draft')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('pendingEdits.loadMore'));

    await waitFor(() => {
      expect(screen.getByText('Second-Page Draft')).toBeTruthy();
    });
    expect(getPendingEditsMock).toHaveBeenCalledWith('agent-a', 50, 1);
  });

  it('restarts from page 1 when the queue drifts between pages', async () => {
    let calls = 0;
    const draft = (id: number, conceptName: string) => ({
      id,
      concept_name: conceptName,
      proposed_content: 'draft',
      status: 'pending',
      created_at: '2026-07-29T00:00:00.000Z',
      updated_at: '2026-07-29T00:00:00.000Z',
    });
    getPendingEditsMock.mockImplementation((...args: unknown[]) => {
      calls += 1;
      if (calls === 1) {
        return Promise.resolve({ stats: { pending: 51, approved: 0 }, pending_edits: [draft(1, 'First-Page Draft')] });
      }
      if (calls === 2) {
        // Mixed same-pending mutation: another device approved one draft while
        // cron staged a fresh one — pending stays 51, approved still moves.
        return Promise.resolve({ stats: { pending: 51, approved: 1 }, pending_edits: [draft(2, 'Shifted-Page Draft')] });
      }
      return Promise.resolve({ stats: { pending: 51, approved: 1 }, pending_edits: [draft(3, 'Fresh-Page Draft')] });
    });

    render(<WikiPendingEdits agentScopeId="agent-a" scopeLabel="Agent A" />);

    await waitFor(() => {
      expect(screen.getByText('First-Page Draft')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('pendingEdits.loadMore'));

    await waitFor(() => {
      expect(screen.getByText('Fresh-Page Draft')).toBeTruthy();
    });
    expect(getPendingEditsMock).toHaveBeenNthCalledWith(3, 'agent-a');
    expect(screen.queryByText('Shifted-Page Draft')).toBeNull();
  });

  it('replaces the first page in place when stats change at offset 0', async () => {
    let calls = 0;
    const draft = (id: number, conceptName: string) => ({
      id,
      concept_name: conceptName,
      proposed_content: 'draft',
      status: 'pending',
      created_at: '2026-07-29T00:00:00.000Z',
      updated_at: '2026-07-29T00:00:00.000Z',
    });
    getPendingEditsMock.mockImplementation(() => {
      calls += 1;
      if (calls === 1) {
        return Promise.resolve({ stats: { pending: 2, approved: 0 }, pending_edits: [draft(1, 'Pre-Approval Draft')] });
      }
      return Promise.resolve({
        stats: { pending: 1, approved: 1, synthesis_pending: 2 },
        pending_edits: [draft(2, 'Post-Approval Draft')],
      });
    });

    render(<WikiPendingEdits agentScopeId="agent-a" scopeLabel="Agent A" />);

    await waitFor(() => {
      expect(screen.getByText('Pre-Approval Draft')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('pendingEdits.approve'));

    await waitFor(() => {
      expect(screen.getByText('Post-Approval Draft')).toBeTruthy();
    });
    expect(screen.queryByText('Pre-Approval Draft')).toBeNull();
    // Synthesis queue growth surfaces on its own badge next to the pending badge.
    expect(screen.getByText('2 pendingEdits.status.synthesisPending')).toBeTruthy();
    // offset-0 refresh never detours through the restart-from-page-1 branch.
    expect(calls).toBe(2);
  });

  it('refreshes the first page after a UI reject action', async () => {
    const calls: number[] = [];
    const draft = (id: number, conceptName: string) => ({
      id,
      concept_name: conceptName,
      proposed_content: 'draft',
      status: 'pending',
      created_at: '2026-07-29T00:00:00.000Z',
      updated_at: '2026-07-29T00:00:00.000Z',
    });
    getPendingEditsMock.mockImplementation(() => {
      calls.push(1);
      if (calls.length === 1) {
        return Promise.resolve({ stats: { pending: 1 }, pending_edits: [draft(1, 'Pre-Reject Draft')] });
      }
      return Promise.resolve({ stats: { pending: 0 }, pending_edits: [] });
    });
    rejectEditMock.mockResolvedValue({ success: true, message: 'ok' });

    render(<WikiPendingEdits agentScopeId="agent-a" scopeLabel="Agent A" />);

    await waitFor(() => {
      expect(screen.getByText('Pre-Reject Draft')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('pendingEdits.reject'));

    await waitFor(() => {
      expect(screen.queryByText('Pre-Reject Draft')).toBeNull();
    });
    expect(rejectEditMock).toHaveBeenCalledWith(1, 'agent-a');
    expect(calls.length).toBe(2);
  });

  it('shows a stale toast and skips refresh when approve hits stale_pending', async () => {
    getPendingEditsMock.mockImplementation(() =>
      Promise.resolve({
        stats: { pending: 1 },
        pending_edits: [
          {
            id: 1,
            concept_name: 'Stale Target Draft',
            proposed_content: 'draft',
            status: 'pending',
            created_at: '2026-07-29T00:00:00.000Z',
            updated_at: '2026-07-29T00:00:00.000Z',
          },
        ],
      })
    );
    const staleError = new ApiError('stale pending edit');
    (staleError as { businessCode?: string }).businessCode = 'stale_pending';
    approveEditMock.mockRejectedValue(staleError);

    render(<WikiPendingEdits agentScopeId="agent-a" scopeLabel="Agent A" />);

    await waitFor(() => {
      expect(screen.getByText('Stale Target Draft')).toBeTruthy();
    });

    fireEvent.click(screen.getByText('pendingEdits.approve'));

    await waitFor(() => {
      expect(toastErrorSpy).toHaveBeenCalledWith('errors.approveStaleSources');
    });
    // Stale approval must not trigger an offset-0 refresh.
    expect(getPendingEditsMock).toHaveBeenCalledTimes(1);
  });
});
