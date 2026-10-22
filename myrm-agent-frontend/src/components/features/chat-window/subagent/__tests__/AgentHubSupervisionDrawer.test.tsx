'use client';

/**
 * [INPUT]: AgentHubSupervisionDrawer.tsx 与 mock roster/transcript 数据
 * [OUTPUT]: 验证 Agent Hub 监管抽屉渲染、Roster 指标条、Worker 切换、Live Transcript 折叠展开与 Steer/Kill/Revive 控制操作
 * [POS]: myrm-agent-frontend/src/components/features/chat-window/subagent/__tests__/AgentHubSupervisionDrawer.test.tsx
 */

import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import {
  AgentHubSupervisionDrawer,
  SupervisionRosterOverview,
  SupervisionTranscriptEntry,
} from '../AgentHubSupervisionDrawer';

const mockRoster: SupervisionRosterOverview = {
  sessionId: 'sess-supervision-01',
  totalWorkers: 3,
  activeWorkers: 1,
  parkedWorkers: 1,
  stuckWorkers: 1,
  totalTokens: 5200,
  totalDurationSeconds: 42.5,
  workers: [
    {
      taskId: 'worker-coder-01',
      agentType: 'Code Architect',
      status: 'running',
      currentActivity: 'Refactoring auth handler',
      model: 'gpt-4o',
      tokensUsed: 2600,
      elapsedSeconds: 24.0,
      lastTool: 'write_file',
      canSteer: true,
      canKill: true,
      canRevive: false,
    },
    {
      taskId: 'worker-tester-02',
      agentType: 'QA Tester',
      status: 'stuck',
      currentActivity: 'Infinite loop on flaky integration test',
      model: 'claude-3-5',
      tokensUsed: 1800,
      elapsedSeconds: 42.5,
      lastTool: 'run_tests',
      canSteer: true,
      canKill: true,
      canRevive: false,
    },
    {
      taskId: 'worker-scout-03',
      agentType: 'Repo Scout',
      status: 'parked',
      currentActivity: 'Parked waiting for dependency sync',
      model: 'deepseek-r1',
      tokensUsed: 800,
      elapsedSeconds: 10.0,
      lastTool: 'list_dir',
      canSteer: false,
      canKill: false,
      canRevive: true,
    },
  ],
};

const mockTranscripts: SupervisionTranscriptEntry[] = [
  {
    entryId: 'tr-01',
    timestamp: '2026-08-19T10:00:00Z',
    toolName: 'read_file',
    inputSummary: 'path="src/auth.py"',
    outputSummary: 'def login(): pass',
    level: 'info',
    durationMs: 32,
  },
  {
    entryId: 'tr-02',
    timestamp: '2026-08-19T10:00:05Z',
    toolName: 'write_file',
    inputSummary: 'path="src/auth.py", content="..."',
    outputSummary: 'Wrote 120 lines successfully',
    level: 'info',
    durationMs: 88,
  },
];

describe('AgentHubSupervisionDrawer', () => {
  it('returns null when isOpen is false', () => {
    const { container } = render(
      <AgentHubSupervisionDrawer
        isOpen={false}
        onClose={vi.fn()}
        roster={mockRoster}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders drawer header, Alt+A badge, and calls onClose on close click', () => {
    const onClose = vi.fn();
    render(
      <AgentHubSupervisionDrawer
        isOpen={true}
        onClose={onClose}
        roster={mockRoster}
      />
    );

    expect(screen.getByTestId('agent-hub-drawer')).toBeInTheDocument();
    expect(screen.getByText('Agent Hub 子代理监管抽屉')).toBeInTheDocument();
    expect(screen.getByText('Alt+A')).toBeInTheDocument();

    const closeBtn = screen.getByTestId('close-drawer-btn');
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('renders roster metrics strip with total workers, tokens, and duration', () => {
    render(
      <AgentHubSupervisionDrawer
        isOpen={true}
        onClose={vi.fn()}
        roster={mockRoster}
      />
    );

    expect(screen.getByTestId('roster-metrics-strip')).toBeInTheDocument();
    expect(screen.getByText('共 3 个 Worker')).toBeInTheDocument();
    expect(screen.getByText('运行中 1')).toBeInTheDocument();
    expect(screen.getByText('挂死 1')).toBeInTheDocument();
    expect(screen.getByText('停靠 1')).toBeInTheDocument();
    expect(screen.getByText(/5,200 tokens/)).toBeInTheDocument();
    expect(screen.getByText(/42.5s/)).toBeInTheDocument();
  });

  it('renders worker cards and triggers onSelectWorker when clicked', () => {
    const onSelect = vi.fn();
    render(
      <AgentHubSupervisionDrawer
        isOpen={true}
        onClose={vi.fn()}
        roster={mockRoster}
        onSelectWorker={onSelect}
      />
    );

    expect(screen.getAllByText('Code Architect').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('QA Tester')).toBeInTheDocument();
    expect(screen.getByText('Repo Scout')).toBeInTheDocument();

    const testerCard = screen.getByTestId('worker-card-worker-tester-02');
    fireEvent.click(testerCard);
    expect(onSelect).toHaveBeenCalledWith('worker-tester-02');
  });

  it('renders live transcript stream entries and toggles expanded output', () => {
    render(
      <AgentHubSupervisionDrawer
        isOpen={true}
        onClose={vi.fn()}
        roster={mockRoster}
        transcriptEntries={mockTranscripts}
        selectedTaskId="worker-coder-01"
      />
    );

    expect(screen.getByTestId('live-transcript-stream')).toBeInTheDocument();
    expect(screen.getByText('read_file')).toBeInTheDocument();
    expect(screen.getByText('write_file')).toBeInTheDocument();
    expect(screen.getAllByText(/path="src\/auth.py"/).length).toBeGreaterThanOrEqual(1);

    // Toggle expansion on trace item
    const toggleBtn = screen.getByText('read_file').closest('button');
    expect(toggleBtn).toBeInTheDocument();
    if (toggleBtn) {
      fireEvent.click(toggleBtn);
    }
    expect(screen.getByText('def login(): pass')).toBeInTheDocument();
  });

  it('triggers steering, kill, revive and refresh actions', () => {
    const onSteer = vi.fn();
    const onKill = vi.fn();
    const onRevive = vi.fn();
    const onRefresh = vi.fn();

    const { rerender } = render(
      <AgentHubSupervisionDrawer
        isOpen={true}
        onClose={vi.fn()}
        roster={mockRoster}
        selectedTaskId="worker-coder-01"
        onSteerWorker={onSteer}
        onKillWorker={onKill}
        onReviveWorker={onRevive}
        onRefresh={onRefresh}
      />
    );

    // Refresh action
    const refreshBtn = screen.getByTestId('refresh-btn');
    fireEvent.click(refreshBtn);
    expect(onRefresh).toHaveBeenCalledTimes(1);

    // Steer action
    const steerInput = screen.getByTestId('steer-input');
    fireEvent.change(steerInput, { target: { value: 'Switch to mock DB instead' } });
    const sendBtn = screen.getByTestId('send-steer-btn');
    fireEvent.click(sendBtn);
    expect(onSteer).toHaveBeenCalledWith('worker-coder-01', 'Switch to mock DB instead');

    // Kill action
    const killBtn = screen.getByTestId('kill-worker-btn');
    fireEvent.click(killBtn);
    expect(onKill).toHaveBeenCalledWith('worker-coder-01');

    // Re-render with parked worker selected for Revive action
    rerender(
      <AgentHubSupervisionDrawer
        isOpen={true}
        onClose={vi.fn()}
        roster={mockRoster}
        selectedTaskId="worker-scout-03"
        onSteerWorker={onSteer}
        onKillWorker={onKill}
        onReviveWorker={onRevive}
      />
    );

    const reviveBtn = screen.getByTestId('revive-worker-btn');
    fireEvent.click(reviveBtn);
    expect(onRevive).toHaveBeenCalledWith('worker-scout-03');
  });
});
