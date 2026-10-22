import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ReconnectStatusPill } from '../ReconnectStatusPill';
import { useZeroReplayReconnectStore } from '../useZeroReplayReconnectStore';
import type { SessionAtomicSnapshot } from '../reconnectProtocolTypes';

describe('ReconnectStatusPill', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useZeroReplayReconnectStore.getState().reset();
  });

  const mockSnapshot: SessionAtomicSnapshot = {
    session_id: 'chat_session_001',
    epoch_id: 'ep_987654321',
    state_version: 5,
    snapshot_timestamp_ms: 1700000000000,
    status: 'running',
    leaf_entry_id: 'leaf_node_1',
    active_tool_calls: [{ id: 'tool_1', tool_name: 'git' }],
    message_count: 8,
    latest_turn_summary: 'Committing code changes',
    artifacts_summary: [],
    metadata: {},
  };

  it('renders status pill with version number and default status', () => {
    render(<ReconnectStatusPill sessionId="chat_session_001" />);

    expect(screen.getByText('v1')).toBeInTheDocument();
    const button = screen.getByRole('button');
    expect(button).toBeInTheDocument();
  });

  it('toggles detail popover dialog upon clicking status pill', () => {
    render(<ReconnectStatusPill sessionId="chat_session_001" />);

    expect(screen.queryByRole('dialog')).toBeNull();

    // Click to open
    const toggleBtn = screen.getByRole('button');
    fireEvent.click(toggleBtn);

    expect(screen.getByRole('dialog')).toBeInTheDocument();

    // Click close button inside popover
    const closeBtn = screen.getByLabelText(/close/i);
    fireEvent.click(closeBtn);

    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('displays snapshot details including version, epoch and message count in popover', () => {
    useZeroReplayReconnectStore.setState({
      status: 'connected',
      currentVersion: 5,
      currentEpoch: 'ep_987654321',
      snapshot: mockSnapshot,
    });

    render(<ReconnectStatusPill sessionId="chat_session_001" />);

    // Open popover
    fireEvent.click(screen.getByRole('button'));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('5')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument(); // messages count
    expect(screen.getByText('1')).toBeInTheDocument(); // active tools count
  });

  it('triggers forceResync when clicking manual resync button', async () => {
    const forceResyncSpy = vi.fn().mockResolvedValue(undefined);
    useZeroReplayReconnectStore.setState({
      status: 'connected',
      currentVersion: 5,
      forceResync: forceResyncSpy,
    });

    render(<ReconnectStatusPill sessionId="chat_session_001" />);

    // Open popover
    fireEvent.click(screen.getByRole('button'));

    const resyncBtn = screen.getByRole('button', { name: /forceResync|对齐/i });
    expect(resyncBtn).toBeInTheDocument();

    fireEvent.click(resyncBtn);

    await waitFor(() => {
      expect(forceResyncSpy).toHaveBeenCalledWith('chat_session_001');
    });
  });

  it('shows reconnecting status and count when network is re-aligning', () => {
    useZeroReplayReconnectStore.setState({
      status: 'reconnecting',
      reconnectCount: 3,
      currentVersion: 2,
    });

    render(<ReconnectStatusPill sessionId="chat_session_001" />);

    fireEvent.click(screen.getByRole('button'));
    expect(screen.getByText(/重连计数: 3/)).toBeInTheDocument();
  });
});
