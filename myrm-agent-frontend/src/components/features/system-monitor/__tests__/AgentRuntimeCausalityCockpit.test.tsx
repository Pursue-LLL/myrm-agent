/**
 * [INPUT]: AgentRuntimeCausalityCockpit, mock RuntimeCausalitySnapshotItem.
 * [OUTPUT]: Vitest test suite verifying process tree rendering, orphan reap button action, tab switches, and failure archives.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/__tests__/AgentRuntimeCausalityCockpit.test.tsx
 */

import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { AgentRuntimeCausalityCockpit } from '../AgentRuntimeCausalityCockpit';
import { RuntimeCausalitySnapshotItem } from '../runtimeZombieReaperTypes';

describe('AgentRuntimeCausalityCockpit Component', () => {
  const mockSnapshot: RuntimeCausalitySnapshotItem = {
    nodes: [
      {
        node_id: 'agent-root-1',
        name: 'Master Orchestrator',
        role: 'primary_agent',
        pid: 3001,
        pgid: 3000,
        parent_id: null,
        profile_id: 'prod-orchestrator',
        state: 'running',
        cpu_percent: 18.2,
        memory_rss_mb: 220.5,
        tokens_consumed: 14200,
        last_heartbeat_ms: 1791800000000,
      },
      {
        node_id: 'subagent-coder-2',
        name: 'Python Compiler Worker',
        role: 'subagent',
        pid: 3002,
        pgid: 3000,
        parent_id: 'agent-root-1',
        profile_id: 'sandbox-worker',
        state: 'crashed',
        cpu_percent: 0.0,
        memory_rss_mb: 85.0,
        tokens_consumed: 8300,
        last_heartbeat_ms: 1791800000000,
        exit_code: 137,
        crash_reason: 'OOM Killed by kernel',
      },
    ],
    profile_summaries: [
      {
        profile_id: 'prod-orchestrator',
        active_processes: 1,
        total_cpu_percent: 18.2,
        total_memory_rss_mb: 220.5,
        total_tokens_consumed: 14200,
      },
      {
        profile_id: 'sandbox-worker',
        active_processes: 1,
        total_cpu_percent: 0.0,
        total_memory_rss_mb: 85.0,
        total_tokens_consumed: 8300,
      },
    ],
    recent_failed_tasks: [
      {
        task_id: 'fail-task-101',
        name: 'LLM Multi-Turn Synthesis',
        parent_task_id: 'agent-root-1',
        profile_id: 'sandbox-worker',
        exit_code: 137,
        crash_reason: 'Kernel Out Of Memory',
        duration_ms: 6540,
        terminated_at_ms: 1791800000000,
      },
    ],
    total_reaped_orphans: 5,
    total_deadlocks_broken: 2,
    timestamp_ms: 1791800000000,
  };

  it('renders top overview metrics and process tree nodes', () => {
    render(<AgentRuntimeCausalityCockpit snapshot={mockSnapshot} />);

    // Header & KPIs
    expect(screen.getByText(/Agent Runtime Causality Cockpit/)).toBeInTheDocument();
    expect(screen.getAllByText('5').length).toBeGreaterThanOrEqual(1); // total_reaped_orphans
    expect(screen.getAllByText('2').length).toBeGreaterThanOrEqual(1); // total_deadlocks_broken
    expect(screen.getAllByText('1').length).toBeGreaterThanOrEqual(1); // failures count

    // Process nodes
    expect(screen.getByText(/Master Orchestrator/)).toBeInTheDocument();
    expect(screen.getByText(/Python Compiler Worker/)).toBeInTheDocument();
    expect(screen.getByText('RUNNING')).toBeInTheDocument();
    expect(screen.getByText('CRASHED')).toBeInTheDocument();
  });

  it('triggers onReapOrphans callback when button clicked', async () => {
    const handleReap = vi.fn().mockResolvedValue(undefined);
    render(
      <AgentRuntimeCausalityCockpit
        snapshot={mockSnapshot}
        onReapOrphans={handleReap}
      />
    );

    const reapButton = screen.getByRole('button', { name: /Reap Orphans/i });
    expect(reapButton).toBeInTheDocument();

    await act(async () => {
      fireEvent.click(reapButton);
    });

    expect(handleReap).toHaveBeenCalledWith('agent-root-1');
  });

  it('switches between tabs: Profile Quotas and Failures Archive', async () => {
    render(<AgentRuntimeCausalityCockpit snapshot={mockSnapshot} />);

    // Switch to Profile Quotas
    const profileTabBtn = screen.getByRole('button', { name: /Profile Quotas/i });
    fireEvent.click(profileTabBtn);

    expect(screen.getByText(/prod-orchestrator/)).toBeInTheDocument();
    expect(screen.getByText(/sandbox-worker/)).toBeInTheDocument();
    expect(screen.getAllByText(/Aggregated CPU:/).length).toBe(2);

    // Switch to Failures Archive
    const failureTabBtn = screen.getByRole('button', { name: /Failures Archive/i });
    fireEvent.click(failureTabBtn);

    expect(screen.getByText('fail-task-101')).toBeInTheDocument();
    expect(screen.getByText('LLM Multi-Turn Synthesis')).toBeInTheDocument();
    expect(screen.getByText('Kernel Out Of Memory')).toBeInTheDocument();
  });
});
