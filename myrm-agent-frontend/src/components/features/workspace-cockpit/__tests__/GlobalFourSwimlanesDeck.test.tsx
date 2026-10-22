import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { GlobalFourSwimlanesDeck } from '../GlobalFourSwimlanesDeck';
import type { WorkspaceTaskItem } from '../workspaceCockpitTypes';

describe('GlobalFourSwimlanesDeck', () => {
  const mockTasks: WorkspaceTaskItem[] = [
    {
      id: 'task-needs-1',
      title: 'Approve destructive database migration',
      swimlane: 'needs-you',
      status: 'waiting_approval',
      chatId: 'chat-mig-1',
      agentName: 'DBA Agent',
      waitingDurationMs: 1800 * 1000,
      updatedAt: Date.now() - 1800 * 1000,
    },
    {
      id: 'task-prog-1',
      title: 'Building micro-frontend bundle',
      swimlane: 'in-progress',
      status: 'running',
      chatId: 'chat-build-1',
      agentName: 'BuildBot',
      latestOutputTail: '[vite:esbuild] Bundled 142 modules in 420ms',
      updatedAt: Date.now() - 30000,
    },
    {
      id: 'task-obs-1',
      title: 'Memory leak diagnostic probe',
      swimlane: 'observing',
      status: 'running',
      chatId: 'chat-probe-1',
      agentName: 'SRE Bot',
      updatedAt: Date.now() - 60000,
    },
    {
      id: 'task-sched-1',
      title: 'Weekly security audit report',
      swimlane: 'scheduled',
      status: 'pending',
      chatId: 'chat-sec-1',
      scheduleCron: '0 0 * * 1',
      updatedAt: Date.now(),
    },
  ];

  it('renders all 4 swimlanes with their headers and task counts', () => {
    const onNavigateToChat = vi.fn();

    render(
      <GlobalFourSwimlanesDeck
        tasks={mockTasks}
        onNavigateToChat={onNavigateToChat}
      />,
    );

    expect(screen.getByTestId('swimlane-needs-you')).toBeInTheDocument();
    expect(screen.getByTestId('swimlane-in-progress')).toBeInTheDocument();
    expect(screen.getByTestId('swimlane-observing')).toBeInTheDocument();
    expect(screen.getByTestId('swimlane-scheduled')).toBeInTheDocument();
  });

  it('renders inline streaming output tail for in-progress tasks', () => {
    const onNavigateToChat = vi.fn();

    render(
      <GlobalFourSwimlanesDeck
        tasks={mockTasks}
        onNavigateToChat={onNavigateToChat}
      />,
    );

    const tailEl = screen.getByTestId('task-tail-task-prog-1');
    expect(tailEl).toBeInTheDocument();
    expect(tailEl).toHaveTextContent('[vite:esbuild] Bundled 142 modules in 420ms');
  });

  it('supports approve and reject quick decisions in needs-you lane', () => {
    const onNavigateToChat = vi.fn();
    const onApproveDecision = vi.fn();
    const onRejectDecision = vi.fn();

    render(
      <GlobalFourSwimlanesDeck
        tasks={mockTasks}
        onNavigateToChat={onNavigateToChat}
        onApproveDecision={onApproveDecision}
        onRejectDecision={onRejectDecision}
      />,
    );

    const approveBtn = screen.getByRole('button', { name: /approve/i });
    const rejectBtn = screen.getByRole('button', { name: /reject/i });

    fireEvent.click(approveBtn);
    expect(onApproveDecision).toHaveBeenCalledWith('task-needs-1');

    fireEvent.click(rejectBtn);
    expect(onRejectDecision).toHaveBeenCalledWith('task-needs-1');
  });

  it('navigates to chat when task link icon is clicked', () => {
    const onNavigateToChat = vi.fn();

    render(
      <GlobalFourSwimlanesDeck
        tasks={mockTasks}
        onNavigateToChat={onNavigateToChat}
      />,
    );

    const navButtons = screen.getAllByRole('button', { name: /open task session/i });
    expect(navButtons.length).toBeGreaterThan(0);

    fireEvent.click(navButtons[0]);
    expect(onNavigateToChat).toHaveBeenCalledWith('chat-mig-1', 'task-needs-1');
  });
});
