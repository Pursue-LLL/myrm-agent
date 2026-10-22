import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import {
  MultiLaneParallelExecutionCard,
  MultiLaneSnapshotData,
} from '../MultiLaneParallelExecutionCard';

describe('MultiLaneParallelExecutionCard', () => {
  it('renders initial fallback snapshot and handles dismiss', () => {
    const handleDismiss = vi.fn();
    render(
      <MultiLaneParallelExecutionCard
        chatId="test-chat-01"
        onDismiss={handleDismiss}
      />
    );

    expect(screen.getByTestId('multi-lane-execution-card')).toBeInTheDocument();
    expect(screen.getByTestId('stat-active-lanes')).toHaveTextContent('0');
    expect(screen.getByTestId('stat-total-nodes')).toHaveTextContent('1');
    expect(screen.getByTestId('stat-total-lanes')).toHaveTextContent('1');

    const dismissBtn = screen.getByRole('button', { name: /Dismiss dialog/i });
    fireEvent.click(dismissBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('renders custom snapshot with multiple lanes and stats', () => {
    const customSnapshot: MultiLaneSnapshotData = {
      session_id: 'test-chat-02',
      lanes: {
        main: {
          lane_id: 'main',
          display_name: 'Main Channel Lane',
          state: 'idle',
          current_leaf_id: 'root',
          active_op_id: null,
          total_ops: 3,
          created_at: 1000,
        },
        'slack:thread-101': {
          lane_id: 'slack:thread-101',
          display_name: 'Discussion Thread #101',
          state: 'running',
          current_leaf_id: 'node-abc',
          active_op_id: 'op-xyz',
          total_ops: 1,
          created_at: 1010,
        },
      },
      total_nodes: 5,
      active_lanes_count: 1,
      recent_op_logs: [
        {
          op_id: 'op-xyz',
          lane_id: 'slack:thread-101',
          name: 'parallel_investigation',
          status: 'running',
          created_at: 1010,
        },
      ],
    };

    render(
      <MultiLaneParallelExecutionCard
        chatId="test-chat-02"
        initialSnapshot={customSnapshot}
      />
    );

    expect(screen.getByTestId('stat-active-lanes')).toHaveTextContent('1');
    expect(screen.getByTestId('stat-total-nodes')).toHaveTextContent('5');
    expect(screen.getByTestId('stat-total-lanes')).toHaveTextContent('2');
    expect(screen.getByTestId('lane-item-main')).toBeInTheDocument();
    expect(screen.getByTestId('lane-item-slack:thread-101')).toBeInTheDocument();
  });

  it('handles creating new thread lane', () => {
    render(<MultiLaneParallelExecutionCard chatId="test-chat-03" />);

    expect(screen.getByTestId('stat-total-lanes')).toHaveTextContent('1');
    const createBtn = screen.getByTestId('btn-create-lane');
    fireEvent.click(createBtn);

    expect(screen.getByTestId('stat-total-lanes')).toHaveTextContent('2');
    expect(screen.getByTestId('status-message')).toHaveTextContent("Created thread lane 'slack:thread-101'");
  });

  it('handles dispatching parallel operations and completes them', () => {
    render(<MultiLaneParallelExecutionCard chatId="test-chat-04" />);

    // Create an extra lane first
    fireEvent.click(screen.getByTestId('btn-create-lane'));
    expect(screen.getByTestId('stat-total-lanes')).toHaveTextContent('2');

    // Dispatch parallel operations
    const dispatchBtn = screen.getByTestId('btn-dispatch-parallel');
    fireEvent.click(dispatchBtn);

    expect(screen.getByTestId('stat-active-lanes')).toHaveTextContent('2');
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      'Dispatched parallel operations across 2 lanes.'
    );

    // Complete them
    const completeBtn = screen.getByTestId('btn-complete-ops');
    fireEvent.click(completeBtn);

    expect(screen.getByTestId('stat-active-lanes')).toHaveTextContent('0');
    expect(screen.getByTestId('stat-total-nodes')).toHaveTextContent('3'); // 1 root + 2 results
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      'Completed 2 operations and advanced shared tree leaves.'
    );
  });

  it('handles simulate conflict and reset', () => {
    render(<MultiLaneParallelExecutionCard chatId="test-chat-05" />);

    // Simulate conflict
    const conflictBtn = screen.getByTestId('btn-simulate-conflict');
    fireEvent.click(conflictBtn);

    expect(screen.getByTestId('status-message')).toHaveTextContent(
      '409 Conflict: Lane concurrency constraint violated'
    );

    // Reset session
    const resetBtn = screen.getByTestId('btn-reset');
    fireEvent.click(resetBtn);

    expect(screen.getByTestId('stat-active-lanes')).toHaveTextContent('0');
    expect(screen.getByTestId('stat-total-nodes')).toHaveTextContent('1');
    expect(screen.getByTestId('stat-total-lanes')).toHaveTextContent('1');
    expect(screen.getByTestId('status-message')).toHaveTextContent(
      'Multi-lane session coordinator reset.'
    );
  });
});
