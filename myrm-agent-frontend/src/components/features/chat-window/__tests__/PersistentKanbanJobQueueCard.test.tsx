import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PersistentKanbanJobQueueCard } from '../PersistentKanbanJobQueueCard';
import { DEFAULT_KANBAN_JOBS } from '../kanban-queue/types';

describe('PersistentKanbanJobQueueCard', () => {
  it('renders queue header, aggregate status, and default jobs', () => {
    render(
      <PersistentKanbanJobQueueCard
        chatId="chat-test-kq-fe"
      />,
    );

    expect(
      screen.getByRole('region', {
        name: /Persistent Kanban Job Queue & 12-Way Batch Runner/i,
      }),
    ).toBeInTheDocument();
    expect(screen.getByText('chat-test-kq-fe')).toBeInTheDocument();
    expect(screen.getByText('Circuit Breaker: ACTIVE')).toBeInTheDocument();

    // Verify aggregate counts
    expect(screen.getByText(/Done: 1\/3 \| Ready: 1 \| Running: 1/i)).toBeInTheDocument();

    // Verify 3 jobs
    expect(screen.getByText('Architecture Blueprint Formulation')).toBeInTheDocument();
    expect(screen.getByText('12-Way Batch Runner Implementation')).toBeInTheDocument();
    expect(screen.getByText('Verifier Gate Quality Audit')).toBeInTheDocument();
  });

  it('claims a ready job and transitions it to running', () => {
    render(<PersistentKanbanJobQueueCard />);

    const claimBtn = screen.getByRole('button', { name: /Claim & Run/i });
    fireEvent.click(claimBtn);

    expect(
      screen.getByText(/claimed by worker-slot-rr-1 and running in Git worktree/i),
    ).toBeInTheDocument();
  });

  it('completes a running job and unblocks downstream tasks', () => {
    render(<PersistentKanbanJobQueueCard />);

    const completeBtn = screen.getByRole('button', { name: /Complete/i });
    fireEvent.click(completeBtn);

    expect(
      screen.getByText(/Task verified & criteria satisfied/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Dependent downstream tasks unblocked/i),
    ).toBeInTheDocument();
  });

  it('toggles job blocking and unblocking', () => {
    render(<PersistentKanbanJobQueueCard />);

    const blockBtns = screen.getAllByRole('button', { name: /^Block$/i });
    expect(blockBtns.length).toBeGreaterThan(0);

    fireEvent.click(blockBtns[0]);
    expect(screen.getByText(/Manual operator pause requested/i)).toBeInTheDocument();

    const unblockBtn = screen.getByRole('button', { name: /^Unblock$/i });
    fireEvent.click(unblockBtn);
    expect(screen.queryByText(/Manual operator pause requested/i)).not.toBeInTheDocument();
  });

  it('sends heartbeat and renews watchdog timer', () => {
    render(<PersistentKanbanJobQueueCard />);

    const heartbeatBtn = screen.getByRole('button', { name: /Heartbeat/i });
    fireEvent.click(heartbeatBtn);

    expect(
      screen.getByText(/Heartbeat acknowledged.*4h watchdog timer renewed/i),
    ).toBeInTheDocument();
  });

  it('dispatches 12-way parallel wave and exports HuggingFace JSONL trajectories', () => {
    const handleDispatch = vi.fn();
    const handleExport = vi.fn();

    render(
      <PersistentKanbanJobQueueCard
        onDispatchWave={handleDispatch}
        onExportTrajectories={handleExport}
      />,
    );

    const dispatchBtn = screen.getByRole('button', { name: /Dispatch 12-Way Wave/i });
    fireEvent.click(dispatchBtn);
    expect(handleDispatch).toHaveBeenCalledWith(1);
    expect(screen.getByText(/12-Way parallel wave dispatched/i)).toBeInTheDocument();

    const exportBtn = screen.getByRole('button', { name: /Export HF JSONL Trajectories/i });
    fireEvent.click(exportBtn);
    expect(handleExport).toHaveBeenCalledWith(1);
    expect(screen.getByText(/Exported 1 HuggingFace JSONL trajectories with zero loss/i)).toBeInTheDocument();
  });

  it('toggles hot safety circuit breaker and inspects single job', () => {
    render(<PersistentKanbanJobQueueCard />);

    const cbBtn = screen.getByRole('button', { name: /Circuit Breaker: ACTIVE/i });
    fireEvent.click(cbBtn);
    expect(screen.getByText('Circuit Breaker: OFF')).toBeInTheDocument();
    expect(screen.getByText(/Hot circuit breaker DISABLED \(Fan-out locked\)/i)).toBeInTheDocument();

    const inspectBtns = screen.getAllByRole('button', { name: /Inspect/i });
    fireEvent.click(inspectBtns[0]);
    expect(screen.getByRole('button', { name: /Collapse/i })).toBeInTheDocument();
  });
});
