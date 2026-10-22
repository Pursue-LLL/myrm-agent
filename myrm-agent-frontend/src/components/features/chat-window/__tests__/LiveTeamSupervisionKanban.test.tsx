'use client';

/**
 * [INPUT]: LiveTeamSupervisionKanban.tsx 与 mock 团队投影数据
 * [OUTPUT]: 验证团队看板头部渲染、状态指标、4 列 CAS 任务看板、认领与完成回调、名册与对等发信交互
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/chat-window/__tests__/LiveTeamSupervisionKanban.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  LiveTeamSupervisionKanban,
  TeamProjectionData,
} from '../LiveTeamSupervisionKanban';

const mockProjection: TeamProjectionData = {
  team_id: 'session-supervision-101',
  members: [
    {
      id: 'session-supervision-101-lead',
      name: 'lead',
      description: 'Implicit Root Session Team Lead',
      provider: 'host',
      context: 'fork',
      role: 'lead',
      phase: 'active',
    },
    {
      id: 'session-supervision-101-worker-alpha',
      name: 'worker-alpha',
      description: 'Backend execution specialist',
      provider: 'anthropic',
      context: 'fresh',
      role: 'teammate',
      phase: 'active',
    },
    {
      id: 'session-supervision-101-worker-beta',
      name: 'worker-beta',
      description: 'QA and verification auditor',
      provider: 'openai',
      context: 'fresh',
      role: 'teammate',
      phase: 'failed',
      error: 'Container memory limit exceeded (1024MB)',
    },
  ],
  tasks: [
    {
      id: 'task-1',
      revision: 1,
      subject: 'Scrape documentation',
      description: 'Download API reference',
      status: 'pending',
      blocked_by: [],
      write_scopes: ['docs/raw'],
      ready: true,
      write_scope_warnings: [],
    },
    {
      id: 'task-2',
      revision: 2,
      subject: 'Synthesize embeddings',
      description: 'Generate vector embeddings',
      status: 'in_progress',
      owner_id: 'session-supervision-101-worker-alpha',
      owner_name: 'worker-alpha',
      blocked_by: ['task-1'],
      write_scopes: ['data/vectors'],
      ready: false,
      write_scope_warnings: ['Write scope conflict with task-3'],
    },
    {
      id: 'task-3',
      revision: 1,
      subject: 'Deploy indexing worker',
      description: 'Launch daemon service',
      status: 'pending',
      blocked_by: ['task-2'],
      write_scopes: ['data/vectors/deploy'],
      ready: false,
      write_scope_warnings: [],
    },
    {
      id: 'task-4',
      revision: 3,
      subject: 'Initialize workspace',
      description: 'Setup git repo',
      status: 'completed',
      owner_name: 'lead',
      blocked_by: [],
      write_scopes: [],
      ready: true,
      write_scope_warnings: [],
    },
  ],
  failure: 'Teammate worker-beta failed: Container memory limit exceeded (1024MB)',
};

describe('LiveTeamSupervisionKanban', () => {
  it('renders header, team ID badge, metrics, and failure banner', () => {
    const handleDismiss = vi.fn();
    render(
      <LiveTeamSupervisionKanban
        projection={mockProjection}
        onDismiss={handleDismiss}
      />
    );

    expect(screen.getByText('Durable Agent Teams 看板')).toBeInTheDocument();
    expect(screen.getByText('Team: session-supervision-101')).toBeInTheDocument();
    expect(screen.getByText('2 成员活跃')).toBeInTheDocument();
    expect(screen.getByText('1 任务就绪')).toBeInTheDocument();
    expect(
      screen.getByText(/Container memory limit exceeded/)
    ).toBeInTheDocument();
  });

  it('renders tasks grouped into 4 CAS Kanban columns with correct details', () => {
    render(
      <LiveTeamSupervisionKanban
        projection={mockProjection}
        onDismiss={vi.fn()}
      />
    );

    // Ready task
    expect(screen.getByText('Scrape documentation')).toBeInTheDocument();
    expect(screen.getAllByText('rev:1')).toHaveLength(2);

    // In Progress task with owner
    expect(screen.getByText('Synthesize embeddings')).toBeInTheDocument();
    expect(screen.getByText('负责人: @worker-alpha')).toBeInTheDocument();
    expect(screen.getByText('范围重叠')).toBeInTheDocument();

    // Blocked task
    expect(screen.getByText('Deploy indexing worker')).toBeInTheDocument();
    expect(screen.getByText('等待: task-2')).toBeInTheDocument();

    // Completed task
    expect(screen.getByText('Initialize workspace')).toBeInTheDocument();
  });

  it('triggers onClaimTask when clicking Claim button on a ready task', () => {
    const handleClaim = vi.fn();
    render(
      <LiveTeamSupervisionKanban
        projection={mockProjection}
        onDismiss={vi.fn()}
        onClaimTask={handleClaim}
      />
    );

    const claimButton = screen.getByRole('button', { name: '认领 (Claim)' });
    fireEvent.click(claimButton);

    expect(handleClaim).toHaveBeenCalledWith('task-1', 1, 'worker-alpha');
  });

  it('triggers onCompleteTask when clicking Complete button on an in-progress task', () => {
    const handleComplete = vi.fn();
    render(
      <LiveTeamSupervisionKanban
        projection={mockProjection}
        onDismiss={vi.fn()}
        onCompleteTask={handleComplete}
      />
    );

    const completeButton = screen.getByRole('button', { name: /完成 \(Complete\)/ });
    fireEvent.click(completeButton);

    expect(handleComplete).toHaveBeenCalledWith('task-2', 2);
  });

  it('switches to Roster tab and displays member cards with phases', () => {
    render(
      <LiveTeamSupervisionKanban
        projection={mockProjection}
        onDismiss={vi.fn()}
      />
    );

    const rosterTab = screen.getByRole('button', { name: /成员名册/ });
    fireEvent.click(rosterTab);

    expect(screen.getByText('worker-alpha')).toBeInTheDocument();
    expect(screen.getByText('Backend execution specialist')).toBeInTheDocument();
    expect(screen.getByText('worker-beta')).toBeInTheDocument();
    expect(screen.getByText('failed')).toBeInTheDocument();
    expect(screen.getAllByText(/Container memory limit exceeded \(1024MB\)/)).toHaveLength(2);
  });

  it('switches to Messages tab and triggers onSendMessage callback', () => {
    const handleSend = vi.fn();
    render(
      <LiveTeamSupervisionKanban
        projection={mockProjection}
        onDismiss={vi.fn()}
        onSendMessage={handleSend}
      />
    );

    const messagesTab = screen.getByRole('button', { name: /对等邮箱消息流/ });
    fireEvent.click(messagesTab);

    const targetSelect = screen.getByRole('combobox');
    fireEvent.change(targetSelect, { target: { value: 'worker-alpha' } });

    const input = screen.getByPlaceholderText('输入给队员的对等消息...');
    fireEvent.change(input, { target: { value: 'Please update task-2 progress' } });

    const sendButton = screen.getByRole('button', { name: /发送/ });
    fireEvent.click(sendButton);

    expect(handleSend).toHaveBeenCalledWith(
      'lead',
      'worker-alpha',
      'Please update task-2 progress'
    );
  });

  it('triggers onDismiss when clicking close button', () => {
    const handleDismiss = vi.fn();
    render(
      <LiveTeamSupervisionKanban
        projection={mockProjection}
        onDismiss={handleDismiss}
      />
    );

    const closeButton = screen.getByLabelText('关闭面板');
    fireEvent.click(closeButton);

    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });
});
