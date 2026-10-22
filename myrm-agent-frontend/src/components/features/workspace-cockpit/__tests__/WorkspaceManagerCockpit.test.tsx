import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WorkspaceManagerCockpit } from '../WorkspaceManagerCockpit';
import type { WorkspaceTaskItem } from '../workspaceCockpitTypes';

describe('WorkspaceManagerCockpit', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  const mockTasks: WorkspaceTaskItem[] = [
    {
      id: 'task-1',
      title: 'Review pull request for login flow',
      swimlane: 'needs-you',
      status: 'waiting_approval',
      chatId: 'chat-pr-1',
      agentName: 'ReviewerBot',
      updatedAt: Date.now() - 3600 * 1000 * 2,
    },
    {
      id: 'task-2',
      title: 'Run end-to-end integration tests',
      swimlane: 'in-progress',
      status: 'running',
      chatId: 'chat-test-1',
      agentName: 'TestBot',
      latestOutputTail: 'PASS src/tests/e2e.test.ts',
      updatedAt: Date.now() - 10000,
    },
  ];

  it('renders top bar header, search input, and swimlanes', () => {
    const onNavigateToChat = vi.fn();

    render(
      <WorkspaceManagerCockpit
        tasks={mockTasks}
        onNavigateToChat={onNavigateToChat}
      />,
    );

    expect(screen.getByTestId('workspace-manager-cockpit')).toBeInTheDocument();
    expect(screen.getByText('Personal Workspace Cockpit')).toBeInTheDocument();
    expect(screen.getByTestId('cockpit-search-input')).toBeInTheDocument();
    expect(screen.getByTestId('global-four-swimlanes-deck')).toBeInTheDocument();
  });

  it('filters tasks based on search input query', () => {
    const onNavigateToChat = vi.fn();

    render(
      <WorkspaceManagerCockpit
        tasks={mockTasks}
        onNavigateToChat={onNavigateToChat}
      />,
    );

    const searchInput = screen.getByTestId('cockpit-search-input');
    fireEvent.change(searchInput, { target: { value: 'integration' } });

    expect(screen.getByText('Run end-to-end integration tests')).toBeInTheDocument();
    expect(screen.queryByText('Review pull request for login flow')).not.toBeInTheDocument();
  });

  it('triggers onRefresh when refresh button is clicked', () => {
    const onNavigateToChat = vi.fn();
    const onRefresh = vi.fn();

    render(
      <WorkspaceManagerCockpit
        tasks={mockTasks}
        onNavigateToChat={onNavigateToChat}
        onRefresh={onRefresh}
      />,
    );

    const refreshBtn = screen.getByTestId('cockpit-refresh-btn');
    fireEvent.click(refreshBtn);

    expect(onRefresh).toHaveBeenCalledTimes(1);
  });

  it('toggles manager companion tray drawer', () => {
    const onNavigateToChat = vi.fn();

    render(
      <WorkspaceManagerCockpit
        tasks={mockTasks}
        onNavigateToChat={onNavigateToChat}
      />,
    );

    const trayToggleBtn = screen.getByTestId('manager-tray-toggle');
    expect(screen.queryByTestId('manager-tray-expanded')).not.toBeInTheDocument();

    fireEvent.click(trayToggleBtn);
    expect(screen.getByTestId('manager-tray-expanded')).toBeInTheDocument();
    expect(screen.getByText('Workspace Manager')).toBeInTheDocument();
  });
});
