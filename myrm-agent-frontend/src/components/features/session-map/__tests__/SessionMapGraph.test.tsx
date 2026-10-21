/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SessionMapGraph } from '../SessionMapGraph';
import type { ProjectCluster, SessionNode } from '@/services/sessionMap';

describe('SessionMapGraph component', () => {
  const mockSession: SessionNode = {
    id: 'sess-01',
    title: 'Authentication Pipeline',
    agent_id: 'agent-01',
    agent_name: 'AuthAgent',
    state: 'working',
    current_task: 'Implementing OAuth provider flow',
    tokens_used: 15400,
    last_active_at: '2026-10-12T10:00:00Z',
    tags: ['security', 'auth'],
    workspace_dir: '/workspace/auth',
  };

  const mockCluster: ProjectCluster = {
    id: 'proj-01',
    name: 'Open Perplexity',
    description: 'Autonomous Search Platform',
    color: '#6366f1',
    workspace_path: '/workspace/open-perplexity',
    git_repo_url: 'https://github.com/myrm-agent/open-perplexity.git',
    sessions: [mockSession],
    active_agent_count: 1,
    total_tokens: 15400,
  };

  const defaultProps = {
    clusters: [mockCluster],
    onSelectSession: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders project container title and workspace path in SVG canvas', () => {
    render(<SessionMapGraph {...defaultProps} />);

    expect(screen.getByText('Open Perplexity')).toBeDefined();
    expect(screen.getByText('/workspace/open-perplexity')).toBeDefined();
  });

  it('renders session node title and agent name', () => {
    render(<SessionMapGraph {...defaultProps} />);

    expect(screen.getByText(/Authentication/)).toBeDefined();
    expect(screen.getByText('AuthAgent')).toBeDefined();
  });

  it('triggers onSelectSession when clicking a session node', () => {
    render(<SessionMapGraph {...defaultProps} />);

    const agentLabel = screen.getByText('AuthAgent');
    // Click parent g group
    const parentGroup = agentLabel.closest('g');
    expect(parentGroup).not.toBeNull();
    if (parentGroup) {
      fireEvent.click(parentGroup);
      expect(defaultProps.onSelectSession).toHaveBeenCalledWith(mockSession, mockCluster);
    }
  });

  it('handles zoom controls smoothly', () => {
    render(<SessionMapGraph {...defaultProps} />);

    const zoomInBtn = screen.getByRole('button', { name: 'Zoom in' });
    const zoomOutBtn = screen.getByRole('button', { name: 'Zoom out' });
    const resetBtn = screen.getByRole('button', { name: 'Reset zoom' });

    fireEvent.click(zoomInBtn);
    expect(screen.getByText('115%')).toBeDefined();

    fireEvent.click(zoomOutBtn);
    expect(screen.getByText('100%')).toBeDefined();

    fireEvent.click(resetBtn);
    expect(screen.getByText('100%')).toBeDefined();
  });

  it('filters sessions by runtime state when stateFilter is provided', () => {
    const idleSession: SessionNode = {
      ...mockSession,
      id: 'sess-02',
      title: 'Idle Worker',
      state: 'idle',
    };
    const multiSessionCluster: ProjectCluster = {
      ...mockCluster,
      sessions: [mockSession, idleSession],
    };

    const { rerender } = render(
      <SessionMapGraph {...defaultProps} clusters={[multiSessionCluster]} stateFilter="working" />,
    );

    expect(screen.getByText(/Authentication/)).toBeDefined();
    expect(screen.queryByText(/Idle Worker/)).toBeNull();

    // Rerender with idle filter
    rerender(
      <SessionMapGraph {...defaultProps} clusters={[multiSessionCluster]} stateFilter="idle" />,
    );
    expect(screen.getByText(/Idle Worker/)).toBeDefined();
    expect(screen.queryByText(/Authentication/)).toBeNull();
  });
});
