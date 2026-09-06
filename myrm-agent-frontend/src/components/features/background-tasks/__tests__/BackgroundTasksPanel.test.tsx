// @vitest-environment jsdom
'use client';

import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import React from 'react';

vi.mock('date-fns', () => ({
  formatDistanceToNow: () => '5 minutes ago',
}));

const mockPush = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn(), prefetch: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
  usePathname: () => '/',
}));

const translations: Record<string, string> = {
  title: 'Background Tasks',
  empty: 'No active tasks or goals',
  searchPlaceholder: 'Filter tasks or goals...',
  clearSearch: 'Clear search',
  noSearchResults: 'No matching tasks or goals found',
  ephemeralRegistryNotice: 'Long-running tasks are in-memory only',
  durableRegistryNotice: 'Long-running task history is saved',
  shellSection: 'Long-running tasks',
  agentSection: 'Agent tasks',
  goalsSection: 'Goals',
  'media.section': 'Media Generation',
  'media.recentSection': 'Recent Terminal Media',
  'media.showRecent': 'Show recent',
  'media.hideRecent': 'Hide recent',
};

const stableT = (namespace?: string) => (key: string) => {
  const fullKey = namespace ? `${namespace}.${key}` : key;
  return translations[fullKey] || translations[key] || key;
};

vi.mock('next-intl', () => ({
  useTranslations: (namespace?: string) => stableT(namespace),
}));

vi.mock('@/components/primitives/popover', () => ({
  Popover: ({ children, open }: { children: React.ReactNode; open?: boolean }) => (
    <div data-testid="popover" data-open={open}>
      {children}
    </div>
  ),
  PopoverTrigger: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="popover-trigger">{children}</div>
  ),
  PopoverContent: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="popover-content">{children}</div>
  ),
}));

vi.mock('@/components/primitives/tooltip', () => ({
  Tooltip: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  TooltipContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/primitives/button', () => ({
  Button: ({ children, onClick, ...props }: React.ButtonHTMLAttributes<HTMLButtonElement>) => (
    <button onClick={onClick} {...props}>
      {children}
    </button>
  ),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const mockListBackgroundTasks = vi.fn();
const mockCancelBackgroundTask = vi.fn();
const mockSteerBackgroundTask = vi.fn();
const mockSendShellBackgroundStdin = vi.fn();

vi.mock('@/services/background-tasks', () => ({
  listBackgroundTasks: () => mockListBackgroundTasks(),
  cancelBackgroundTask: (id: string) => mockCancelBackgroundTask(id),
  steerBackgroundTask: (id: string, text: string) => mockSteerBackgroundTask(id, text),
  sendShellBackgroundStdin: (id: string, text: string, opts?: unknown) =>
    mockSendShellBackgroundStdin(id, text, opts),
  evictedFilenameFromVaultRef: (ref: string) => ref,
}));

vi.mock('@/services/backgroundTasksRefresh', () => ({
  subscribeBackgroundTasksChanged: vi.fn(() => () => {}),
}));

vi.mock('@/services/mediaTasks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/mediaTasks')>();
  return {
    ...actual,
    cancelMediaTask: vi.fn(),
  };
});

const mockMediaTasks = [
  {
    task_id: 'media-1',
    task_type: 'image_generate',
    status: 'running',
    progress: 50,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    payload: { prompt: 'A futuristic city skyline', chat_id: 'chat-m1' },
  },
];
const mockRecentTerminalMediaTasks: unknown[] = [];
const mockRefetchMediaTasks = vi.fn();

vi.mock('@/hooks/tasks/useMediaBackgroundTasks', () => ({
  useMediaBackgroundTasks: () => ({
    mediaTasks: mockMediaTasks,
    recentTerminalMediaTasks: mockRecentTerminalMediaTasks,
    refetchMediaTasks: mockRefetchMediaTasks,
  }),
}));

vi.mock('@/hooks/tasks/useGlobalMediaTaskNotifications', () => ({
  useGlobalMediaTaskNotifications: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: vi.fn(async (url: string) => {
    if (url === '/goals/active') {
      return {
        ok: true,
        json: async () => ({
          goals: [
            {
              goal_id: 'goal-1',
              objective: 'Refactor database models',
              status: 'active',
              session_id: 'chat-g1',
              created_at: new Date().toISOString(),
              tokens_used: 1200,
            },
          ],
        }),
      };
    }
    return { ok: true, json: async () => ({}) };
  }),
}));

import BackgroundTasksPanel from '../BackgroundTasksPanel';

describe('BackgroundTasksPanel with Search and Filter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListBackgroundTasks.mockResolvedValue({
      tasks: [
        {
          task_id: 'shell-task-101',
          kind: 'shell',
          command: 'npm run build',
          prompt: 'Execute project frontend build',
          status: 'running',
          result_preview: 'Compiling typescript files...',
          job_id: 'job-shell-1',
          created_at: Math.floor(Date.now() / 1000) - 60,
        },
        {
          task_id: 'agent-task-202',
          kind: 'agent',
          prompt: 'Analyze competitor product pricing',
          status: 'running',
          result_preview: 'Extracting pricing table data',
          created_at: Math.floor(Date.now() / 1000) - 120,
        },
      ],
      registry_ephemeral: false,
    });
  });

  it('renders search input when tasks or goals exist', async () => {
    render(
      <BackgroundTasksPanel
        trigger={<button data-testid="panel-trigger">Open</button>}
      />,
    );

    // Open popover by clicking trigger
    const trigger = screen.getByTestId('panel-trigger');
    fireEvent.click(trigger);

    const searchInput = await screen.findByTestId('background-tasks-search-input');
    expect(searchInput).toBeDefined();
    expect(searchInput.getAttribute('placeholder')).toBe('Filter tasks or goals...');
  });

  it('filters task rows dynamically as user types query', async () => {
    render(
      <BackgroundTasksPanel
        trigger={<button data-testid="panel-trigger">Open</button>}
      />,
    );

    const trigger = screen.getByTestId('panel-trigger');
    fireEvent.click(trigger);

    // Wait for content to load
    expect(await screen.findByText('Execute project frontend build')).toBeDefined();
    expect(screen.getByText('Analyze competitor product pricing')).toBeDefined();
    expect(screen.getByText('Refactor database models')).toBeDefined();

    const searchInput = screen.getByTestId('background-tasks-search-input');

    // Type query matching only the shell task
    fireEvent.change(searchInput, { target: { value: 'frontend build' } });

    await waitFor(() => {
      expect(screen.getByText('Execute project frontend build')).toBeDefined();
      expect(screen.queryByText('Analyze competitor product pricing')).toBeNull();
      expect(screen.queryByText('Refactor database models')).toBeNull();
    });

    // Clear search using the clear button
    const clearButton = screen.getByRole('button', { name: 'Clear search' });
    fireEvent.click(clearButton);

    await waitFor(() => {
      expect(screen.getByText('Execute project frontend build')).toBeDefined();
      expect(screen.getByText('Analyze competitor product pricing')).toBeDefined();
      expect(screen.getByText('Refactor database models')).toBeDefined();
    });
  });

  it('shows no-results state when search query matches nothing', async () => {
    render(
      <BackgroundTasksPanel
        trigger={<button data-testid="panel-trigger">Open</button>}
      />,
    );

    const trigger = screen.getByTestId('panel-trigger');
    fireEvent.click(trigger);

    await screen.findByText('Execute project frontend build');

    const searchInput = screen.getByTestId('background-tasks-search-input');
    fireEvent.change(searchInput, { target: { value: 'nonexistent-query-xyz' } });

    await waitFor(() => {
      expect(screen.getByText('No matching tasks or goals found')).toBeDefined();
      expect(screen.queryByText('Execute project frontend build')).toBeNull();
    });
  });
});
