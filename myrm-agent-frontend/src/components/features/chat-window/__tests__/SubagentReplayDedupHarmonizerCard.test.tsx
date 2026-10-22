import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { SubagentReplayDedupHarmonizerCard } from '../SubagentReplayDedupHarmonizerCard';

describe('SubagentReplayDedupHarmonizerCard', () => {
  it('renders initial metrics banner and default merged batches', () => {
    const handleDismiss = vi.fn();
    render(
      <SubagentReplayDedupHarmonizerCard
        chatId="test-chat-replay-01"
        onDismiss={handleDismiss}
      />
    );

    expect(screen.getByTestId('replay-dedup-card')).toBeInTheDocument();
    expect(screen.getByTestId('metrics-banner')).toBeInTheDocument();
    expect(screen.getByText(/Saved/i)).toBeInTheDocument();
    expect(screen.getByText('-970 t')).toBeInTheDocument();
    expect(screen.getByTestId('batches-list')).toBeInTheDocument();

    // Verify batch items
    expect(screen.getByText('read_file x5 across 5 source files')).toBeInTheDocument();
    expect(screen.getByText('grep x3 across repository regex patterns')).toBeInTheDocument();

    // Test toggle calls expansion
    const expandBtn = screen.getByRole('button', { name: /View 5 Calls/i });
    fireEvent.click(expandBtn);
    expect(screen.getByText('• call-r1')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Hide Calls/i })).toBeInTheDocument();

    // Test dismiss
    const closeBtn = screen.getByTestId('btn-close');
    fireEvent.click(closeBtn);
    expect(handleDismiss).toHaveBeenCalledTimes(1);
  });

  it('switches to status machine harmonizer tab and displays subagents', () => {
    render(<SubagentReplayDedupHarmonizerCard chatId="test-chat-replay-02" />);

    const harmonizerTab = screen.getByTestId('tab-harmonizer');
    fireEvent.click(harmonizerTab);

    expect(screen.getByTestId('subagents-list')).toBeInTheDocument();
    expect(screen.getByText('agent-scout-01')).toBeInTheDocument();
    expect(screen.getByText('agent-worker-02')).toBeInTheDocument();
    expect(screen.getByText('agent-hung-reviewer')).toBeInTheDocument();
    expect(screen.getByText('Defused')).toBeInTheDocument();
  });

  it('switches to isolated mutating ops tab and displays immutable safety notices', () => {
    render(<SubagentReplayDedupHarmonizerCard chatId="test-chat-replay-03" />);

    const isolatedTab = screen.getByTestId('tab-isolated');
    fireEvent.click(isolatedTab);

    expect(screen.getByTestId('isolated-list')).toBeInTheDocument();
    expect(screen.getByText(/Immutable Audit Isolation/i)).toBeInTheDocument();
    expect(screen.getByText('write_to_file')).toBeInTheDocument();
    expect(screen.getByText('run_command')).toBeInTheDocument();
  });

  it('triggers history merge replay and fires onHarmonizeComplete callback', () => {
    const handleHarmonizeComplete = vi.fn();
    render(
      <SubagentReplayDedupHarmonizerCard
        chatId="test-chat-replay-04"
        onHarmonizeComplete={handleHarmonizeComplete}
      />
    );

    const replayBtn = screen.getByTestId('btn-merge-history');
    fireEvent.click(replayBtn);

    expect(handleHarmonizeComplete).toHaveBeenCalledTimes(1);
    expect(handleHarmonizeComplete).toHaveBeenCalledWith(970);
  });

  it('triggers watchdog scan to advance active leases and defuse deadlocks', () => {
    render(<SubagentReplayDedupHarmonizerCard chatId="test-chat-replay-05" />);

    // Switch to harmonizer tab to watch state change
    fireEvent.click(screen.getByTestId('tab-harmonizer'));
    expect(screen.getByText('RUNNING')).toBeInTheDocument();

    const watchdogBtn = screen.getByTestId('btn-watchdog-check');
    fireEvent.click(watchdogBtn);

    expect(screen.getByText('Lease Green')).toBeInTheDocument();
    // Running subagent advanced to completed
    expect(screen.queryByText('RUNNING')).not.toBeInTheDocument();
  });
});
