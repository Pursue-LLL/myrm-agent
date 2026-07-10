'use client';

import { render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';

import { BuiltinToolsPanel } from '../agent-config-panel/BuiltinToolsPanel';

vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock('@/hooks/useFeatureEntitlements', () => ({
  useFeatureEntitlements: () => ({ canUseCron: true, canUseVnc: true, isLoading: false }),
}));

vi.mock('@/lib/deploy-mode', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/deploy-mode')>();
  return {
    ...actual,
    isSandbox: () => false,
    isLocalMode: () => true,
  };
});

vi.mock('../agent-config-panel/MediaCredentialInline', () => ({
  MediaCredentialInline: () => null,
}));

vi.mock('../agent-config-panel/CuPermissionInline', () => ({
  CuPermissionInline: () => null,
}));

const listBoards = vi.fn();

vi.mock('@/services/kanban', () => ({
  listBoards: (...args: unknown[]) => listBoards(...args),
}));

const tPanel = (key: string) => {
  const map: Record<string, string> = {
    kanbanNoBoardsHint: 'Create a task board in Settings before the agent can add tasks.',
    kanbanOpenSettings: 'Open Task Boards in Settings',
    kanbanBoardHint: 'Tasks from chat go to the selected board below.',
    kanbanActiveBoard: 'Active board',
    'builtinToolNames.kanban': 'Task Board',
    'builtinToolDescs.kanban': 'Manage kanban tasks',
  };
  return map[key] ?? key;
};

describe('BuiltinToolsPanel kanban config', () => {
  beforeEach(() => {
    listBoards.mockReset();
    localStorage.clear();
  });

  it('shows no-board hint when kanban enabled and no boards exist', async () => {
    listBoards.mockResolvedValue({ items: [], total: 0 });

    render(
      <BuiltinToolsPanel
        localBuiltinTools={['kanban']}
        setLocalBuiltinTools={() => undefined}
        localAutoRestoreDomains={[]}
        setLocalAutoRestoreDomains={() => undefined}
        setLocalBrowserSource={() => undefined}
        setLocalDialogPolicy={() => undefined}
        setLocalSessionRecording={() => undefined}
        t={(key) => key}
        tAgent={(key) => key}
        tPanel={tPanel}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/Create a task board in Settings/i)).toBeInTheDocument();
    });
    expect(screen.getByRole('link', { name: /Open Task Boards in Settings/i })).toHaveAttribute(
      'href',
      '/settings/kanban',
    );
  });

  it('shows active board name for single board', async () => {
    listBoards.mockResolvedValue({
      items: [{ board_id: 'b1', name: 'Product Pipeline' }],
      total: 1,
    });

    render(
      <BuiltinToolsPanel
        localBuiltinTools={['kanban']}
        setLocalBuiltinTools={() => undefined}
        localAutoRestoreDomains={[]}
        setLocalAutoRestoreDomains={() => undefined}
        setLocalBrowserSource={() => undefined}
        setLocalDialogPolicy={() => undefined}
        setLocalSessionRecording={() => undefined}
        t={(key) => key}
        tAgent={(key) => key}
        tPanel={tPanel}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/Product Pipeline/)).toBeInTheDocument();
    });
  });
});
