/**
 * Unit tests for ProjectBoundaryBadge.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import ProjectBoundaryBadge from '../ProjectBoundaryBadge';
import useChatStore from '@/store/useChatStore';
import { useProjectStore } from '@/store/useProjectStore';
import type { Project } from '@/services/projects';

const MOCK_PROJECTS: Project[] = [
  {
    id: 'proj-alpha',
    name: 'Alpha Customer Portal',
    description: 'Finance sandbox for client Alpha',
    color: '#7cb9ff',
    sortOrder: 0,
    workspacePath: '/sandboxes/alpha',
    goalSummary: '',
    createdAt: '2026-09-01T00:00:00Z',
    updatedAt: '2026-09-01T00:00:00Z',
  },
  {
    id: 'proj-beta',
    name: 'Beta Cloud Infra',
    description: '',
    color: '#ffd97c',
    sortOrder: 1,
    workspacePath: '',
    goalSummary: '',
    createdAt: '2026-09-02T00:00:00Z',
    updatedAt: '2026-09-02T00:00:00Z',
  },
];

describe('ProjectBoundaryBadge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useChatStore.setState({
      chatId: 'chat-1',
      chatHistoryItems: [],
    });
    useProjectStore.setState({
      projects: MOCK_PROJECTS,
      activeFilter: undefined,
    });
  });

  it('renders nothing when active session is not assigned to any project', () => {
    const { container } = render(<ProjectBoundaryBadge />);
    expect(container.firstChild).toBeNull();
  });

  it('renders project boundary badge from active chat item', () => {
    useChatStore.setState({
      chatId: 'chat-1',
      chatHistoryItems: [
        {
          id: 'chat-1',
          title: 'Ledger Audit',
          firstMessage: 'Audit ledger please',
          lastMessage: 'All entries reconciled',
          actionMode: 'chat',
          source: 'web',
          createdAt: new Date('2026-09-01T00:00:00Z'),
          updatedAt: new Date('2026-09-01T00:00:00Z'),
          projectId: 'proj-alpha',
        },
      ],
    });

    render(<ProjectBoundaryBadge />);

    const badge = screen.getByTestId('project-boundary-badge');
    expect(badge).toBeInTheDocument();
    expect(screen.getByText('Alpha Customer Portal')).toBeInTheDocument();
    expect(screen.getByText('隔离保护')).toBeInTheDocument();
    expect(badge).toHaveAttribute('title', '项目隔离工作区: /sandboxes/alpha');
  });

  it('renders project boundary badge fallback from activeFilter in new session', () => {
    useChatStore.setState({
      chatId: undefined,
      chatHistoryItems: [],
    });
    useProjectStore.setState({
      projects: MOCK_PROJECTS,
      activeFilter: 'proj-beta',
    });

    render(<ProjectBoundaryBadge />);

    const badge = screen.getByTestId('project-boundary-badge');
    expect(badge).toBeInTheDocument();
    expect(screen.getByText('Beta Cloud Infra')).toBeInTheDocument();
    expect(screen.getByText('隔离保护')).toBeInTheDocument();
    expect(badge).toHaveAttribute('title', '项目沙箱与专属记忆隔离已激活');
  });
});
