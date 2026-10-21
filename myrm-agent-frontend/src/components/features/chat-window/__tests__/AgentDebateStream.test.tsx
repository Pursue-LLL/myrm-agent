'use client';

/**
 * [INPUT]: AgentDebateStream.tsx 与 mock 辩论室状态数据
 * [OUTPUT]: 验证多智能体协同辩论流展示、Leader 任务拆解、防无效车轮战指示、Kanban 状态同步与共识采纳交互
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/__tests__/AgentDebateStream.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  AgentDebateStream,
  DebateRoomStateData,
} from '../AgentDebateStream';

const mockRoom: DebateRoomStateData = {
  roomId: 'room-alpha-001',
  chatId: 'chat-workroom-100',
  topic: 'Decompose & Implement Zero-Trust Microsegmentation',
  leaderAgentId: 'agent-lead-01',
  phase: 'round_argument',
  roundIndex: 1,
  maxRounds: 3,
  kanbanBoardId: 'board-security-01',
  participants: [
    { agentId: 'agent-lead-01', name: 'Chief Architect', role: 'leader' },
    { agentId: 'agent-critic-02', name: 'Security Auditor', role: 'critic' },
    { agentId: 'agent-coder-03', name: 'Infra Engineer', role: 'implementer' },
  ],
  subtasks: [
    {
      taskId: 'st-01',
      title: 'mTLS Handshake Performance Tuning',
      description: 'Optimize session tickets and TLS 1.3 resumption',
      assignedAgentId: 'agent-coder-03',
      assignedRole: 'implementer',
      status: 'in_progress',
      kanbanTaskId: 'kb-task-501',
    },
    {
      taskId: 'st-02',
      title: 'EBPF Network Policy Enforcement',
      description: 'Validate Cilium network policy packet drops',
      assignedAgentId: 'agent-critic-02',
      assignedRole: 'critic',
      status: 'todo',
    },
  ],
  turns: [
    {
      turnId: 'turn-01',
      speakerId: 'agent-critic-02',
      speakerName: 'Security Auditor',
      role: 'critic',
      phase: 'round_argument',
      roundIndex: 1,
      thesis: 'EBPF TC filter drops packets without kernel context switch overhead',
      counterPoints: ['Requires Linux 5.10+ kernel support in customer VPCs'],
      evidence: ['Benchmark demonstrates 40% CPU drop compared to iptables'],
      confidence: 0.94,
      kanbanTaskId: 'kb-task-501',
    },
  ],
  consensusDecision: 'Adopt EBPF network policies with iptables fallback for legacy kernels.',
};

describe('AgentDebateStream', () => {
  it('renders header metadata including topic, phase, round, agents count, and kanban board', () => {
    render(<AgentDebateStream room={mockRoom} />);

    expect(screen.getByText('Decompose & Implement Zero-Trust Microsegmentation')).toBeInTheDocument();
    expect(screen.getByText('Specialist Argument')).toBeInTheDocument();
    expect(screen.getByText('Round 1/3')).toBeInTheDocument();
    expect(screen.getByText('Room: room-alpha-001')).toBeInTheDocument();
    expect(screen.getByText('3 Agents')).toBeInTheDocument();
    expect(screen.getByText('Board: board-security-01')).toBeInTheDocument();
  });

  it('renders debate turns tab by default with thesis, counter-points, evidence, and confidence score', () => {
    render(<AgentDebateStream room={mockRoom} />);

    expect(screen.getByText('Security Auditor')).toBeInTheDocument();
    expect(screen.getByText('Conf: 94%')).toBeInTheDocument();
    expect(screen.getByText('EBPF TC filter drops packets without kernel context switch overhead')).toBeInTheDocument();
    expect(screen.getByText('Requires Linux 5.10+ kernel support in customer VPCs')).toBeInTheDocument();
    expect(screen.getByText('Benchmark demonstrates 40% CPU drop compared to iptables')).toBeInTheDocument();
  });

  it('switches to subtasks tab and renders decomposed task cards with status and sync button', () => {
    const onSyncKanbanMock = vi.fn();
    render(<AgentDebateStream room={mockRoom} onSyncKanban={onSyncKanbanMock} />);

    const subtasksTabBtn = screen.getByRole('button', { name: /Decomposed Subtasks/i });
    fireEvent.click(subtasksTabBtn);

    expect(screen.getByText('mTLS Handshake Performance Tuning')).toBeInTheDocument();
    expect(screen.getByText('EBPF Network Policy Enforcement')).toBeInTheDocument();
    expect(screen.getByText('#task-501')).toBeInTheDocument();

    const syncBtn = screen.getByRole('button', { name: /Sync Kanban/i });
    expect(syncBtn).toBeInTheDocument();
    fireEvent.click(syncBtn);
    expect(onSyncKanbanMock).toHaveBeenCalledWith('room-alpha-001', 'st-02', 'kanban-st-02');
  });

  it('renders consensus decision and triggers confirmation callback', () => {
    const onAdoptConsensusMock = vi.fn();
    render(<AgentDebateStream room={mockRoom} onAdoptConsensus={onAdoptConsensusMock} />);

    expect(screen.getByText('Consensus Decision Adopted')).toBeInTheDocument();
    expect(
      screen.getByText('Adopt EBPF network policies with iptables fallback for legacy kernels.')
    ).toBeInTheDocument();

    const confirmBtn = screen.getByRole('button', { name: /Confirm & Sync Kanban Tasks/i });
    fireEvent.click(confirmBtn);
    expect(onAdoptConsensusMock).toHaveBeenCalledWith(
      'room-alpha-001',
      'Adopt EBPF network policies with iptables fallback for legacy kernels.'
    );
  });

  it('shows anti-wheel-war warning banner when roundIndex reaches maxRounds', () => {
    const cappedRoom: DebateRoomStateData = {
      ...mockRoom,
      roundIndex: 3,
      maxRounds: 3,
      phase: 'convergence',
    };
    render(<AgentDebateStream room={cappedRoom} />);

    expect(
      screen.getByText(/Anti-Wheel-War Limit Reached: Max 3 debate rounds consumed/i)
    ).toBeInTheDocument();
  });

  it('handles advance phase and dismiss actions', () => {
    const onAdvancePhaseMock = vi.fn();
    const onDismissMock = vi.fn();

    render(
      <AgentDebateStream
        room={mockRoom}
        onAdvancePhase={onAdvancePhaseMock}
        onDismiss={onDismissMock}
      />
    );

    const advanceBtn = screen.getByRole('button', { name: /Advance Phase/i });
    fireEvent.click(advanceBtn);
    expect(onAdvancePhaseMock).toHaveBeenCalledWith('room-alpha-001');

    const closeBtn = screen.getByRole('button', { name: 'Close Debate Panel' });
    fireEvent.click(closeBtn);
    expect(onDismissMock).toHaveBeenCalledTimes(1);
  });
});
