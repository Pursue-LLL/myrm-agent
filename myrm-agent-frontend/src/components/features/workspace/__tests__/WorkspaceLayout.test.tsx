/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import WorkspaceLayout from '../WorkspaceLayout';
import useWorkspaceStore from '@/store/useWorkspaceStore';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock('@/lib/utils/apiConfig', () => ({
  getBackendUrl: () => 'http://localhost:8080',
}));

vi.mock('@/lib/utils/authHeaders', () => ({
  getAuthHeaders: () => ({ Authorization: 'Bearer test' }),
}));

vi.mock('@/services/agent', () => ({
  getActiveSessions: vi.fn().mockResolvedValue({ activeSessions: [], maxConcurrent: 3, availableSlots: 3 }),
}));

vi.mock('@/services/chat', () => ({
  getMessages: vi.fn().mockResolvedValue({ messages: [] }),
  getChatHistory: vi.fn().mockResolvedValue({ items: [], pagination: { page: 1, total: 0 } }),
}));

describe('WorkspaceLayout mobile review drawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useWorkspaceStore.setState({
      panes: [
        {
          id: 'pane-1',
          chatId: 'session-123',
          title: 'pane-1',
          snapshot: null,
          abortController: null,
          currentSessionMessageId: null,
        },
      ],
      activePaneId: 'pane-1',
    });
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response);
  });

  it('renders empty state without panes', () => {
    useWorkspaceStore.setState({ panes: [], activePaneId: null });
    render(<WorkspaceLayout />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens and closes the mobile review drawer', () => {
    render(<WorkspaceLayout />);

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open review panel' }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Close review panel' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
